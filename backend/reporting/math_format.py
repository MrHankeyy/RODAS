"""Offline mathematical typesetting shared by Qt views and exported reports."""
import base64
from functools import lru_cache
from html import escape
from io import BytesIO
import re

from matplotlib import mathtext
from matplotlib import rc_context
from matplotlib.font_manager import FontProperties
from PIL import Image


class Math(str):
    """Keep a copyable plain value alongside its presentation-only math source."""
    def __new__(cls, plain, latex):
        value = super().__new__(cls, plain)
        value.latex = latex
        return value


def symbol(name):
    # Names are literal identifiers, never user-supplied TeX commands.
    if len(str(name)) == 1 and str(name).isascii() and str(name).isalpha():
        return str(name)
    escaped = ''.join({'\\': r'\backslash ', '_': r'\_', '{': r'\{', '}': r'\}',
                       '$': r'\$', '%': r'\%', '&': r'\&', '#': r'\#',
                       '^': r'\wedge ', '~': r'\sim '}.get(c, c) for c in str(name))
    return r'\mathrm{' + escaped.replace(' ', r'\ ') + '}'


def number(value):
    text = f'{float(value):.6g}'
    if 'e' in text:
        mantissa, exponent = text.split('e')
        return mantissa + r'\times 10^{' + str(int(exponent)) + '}'
    return text


@lru_cache(maxsize=1024)
def _image(latex):
    output = BytesIO()
    settings = {'savefig.transparent': True}
    if any('\u2e80' <= char <= '\u9fff' for char in latex):
        settings.update({'mathtext.fontset': 'custom', 'mathtext.rm': 'Microsoft YaHei',
                         'mathtext.it': 'DejaVu Sans:italic'})
    with rc_context(settings):
        mathtext.math_to_image('$' + latex + '$', output, dpi=180,
                              prop=FontProperties(family=['DejaVu Sans', 'Microsoft YaHei'], size=12),
                              color='#26364a', format='png')
    png = output.getvalue()
    with Image.open(BytesIO(png)) as image:
        width, height = image.size
    return base64.b64encode(png).decode('ascii'), round(width * 96 / 180), round(height * 96 / 180)


def formula_html(latex, plain=''):
    encoded, width, height = _image(latex)
    return (f'<img src="data:image/png;base64,{encoded}" width="{width}" height="{height}" '
            f'alt="{escape(plain or latex, quote=True)}" style="vertical-align:middle;"/>')


# Only known mathematical notation is recognised in prose. Ordinary identifiers,
# file names and user text are escaped and are never interpreted as HTML/TeX.
NOTATION = {
    'σ=区间宽度/(2k)': r'\sigma=\frac{\mathrm{区间宽度}}{2k}',
    '标准差=(上限−下限)/(2k)': r'\sigma=\frac{\mathrm{上限}-\mathrm{下限}}{2k}',
    'z=(x−中心)/半跨度': r'z=\frac{x-\mathrm{中心}}{\mathrm{半跨度}}',
    '编码值=(实际值−中心)/半跨度': r'z=\frac{x-\mathrm{中心}}{\mathrm{半跨度}}',
    '均值 + k×标准差 ≤ 上限': r'\mu+k\sigma\leq\mathrm{上限}',
    'μ±kσ': r'\mu\pm k\sigma', '均值−kσ': r'\mu-k\sigma',
    '均值+kσ': r'\mu+k\sigma', 'R²': r'R^2', '2^k': r'2^k',
    '1/2 分数': r'\frac{1}{2}', '1/4 分数': r'\frac{1}{4}',
    '残差 = 观测值 − 预测值': r'e_i=y_i-\widehat{y}_i',
}
PATTERN = re.compile('|'.join(re.escape(key) for key in NOTATION) +
                     r'|(?<![\w])x\d+(?:²)?(?:·x\d+(?:²)?)?(?![\w])' +
                     r'|(?<![\w.])[-+]?\d+(?:\.\d*)?[eE][-+]\d+(?![\w.])' +
                     r'|[σμλα]\s*(?:≤|≥|=|>|<)\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?')


def rich_text(value):
    if isinstance(value, Math):
        return formula_html(value.latex, value)
    text = str(value)
    parts, start = [], 0
    for match in PATTERN.finditer(text):
        parts.append(escape(text[start:match.start()]))
        token = match.group()
        latex = NOTATION.get(token)
        if latex is None:
            if re.fullmatch(r'[-+]?\d+(?:\.\d*)?[eE][-+]\d+', token):
                latex = number(float(token))
            elif token[0] in 'σμλα':
                variable, operator, value = re.fullmatch(r'([σμλα])\s*(≤|≥|=|>|<)\s*(.*)', token).groups()
                latex = {'σ': r'\sigma', 'μ': r'\mu', 'λ': r'\lambda', 'α': r'\alpha'}[variable]
                latex += {'≤': r'\leq ', '≥': r'\geq '}.get(operator, operator) + number(float(value))
            else:
                latex = re.sub(r'x(\d+)', r'x_{\1}', token).replace('²', '^2').replace('·', r'\,')
        parts.append(formula_html(latex, token))
        if token.endswith(' 分数'):
            parts.append(' 分数')
        start = match.end()
    parts.append(escape(text[start:]))
    return ''.join(parts).replace('\n', '<br/>')


def polynomial(name, model, names):
    """Format actual model terms; no fitting, evaluation or rounding of stored data."""
    terms, pieces = [], []
    for index, ((kind, i, j), coefficient) in enumerate(zip(model['terms'], model['coef'])):
        z = lambda n: 'z_{' + symbol(names[n]) + '}'
        plain = '常数' if kind == 'const' else f'z_{names[i]}' if kind == 'linear' else (
            f'z_{names[i]}²' if kind == 'quad' else f'z_{names[i]} · z_{names[j]}')
        latex = '1' if kind == 'const' else z(i) if kind == 'linear' else (
            z(i) + '^2' if kind == 'quad' else z(i) + r'\,' + z(j))
        terms.append(plain if kind == 'const' else Math(plain, latex))
        sign = ('-' if coefficient < 0 else '') if index == 0 else ('-' if coefficient < 0 else '+')
        body = sign + number(abs(coefficient)) + ('' if kind == 'const' else r'\,' + latex)
        pieces.append((symbol(name) + '=' if index == 0 else '') + body)
    coding = [Math(f'z_{factor} = ({factor} − ({center:.6g})) / {half:.6g}',
                   'z_{' + symbol(factor) + '}=\\frac{' + symbol(factor) + '-(' + number(center) + ')}{' + number(half) + '}')
              for factor, center, half in zip(names, model['center'], model['half'])]
    return terms, pieces, coding
