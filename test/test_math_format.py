"""Math is presentation-only: preserve numbers, labels and exportable table data."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtGui import QFont, QTextCharFormat, QTextDocument
from PyQt6.QtWidgets import QComboBox, QStyleOptionViewItem

from backend.reporting.math_format import Math, NOTATION, formula_html, polynomial, rich_text, symbol
from backend.reporting import report_engine
from backend.infrastructure.file_io import export_pdf
from backend.services import analysis_service
from frontend.math_widgets import MATH_ROLE, decorate_combo
from frontend.pages.result_overview import SummaryTable
from frontend.theme import install_theme
from test_workbench_analysis import APP, make_context


class MathFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_theme(APP)

    def test_polynomial_uses_encoded_subscripts_powers_and_fraction(self):
        _, context = make_context()
        model = context['models']['Y']
        coefficients = model['coef'].copy()
        terms, pieces, coding = polynomial('Y', model, context['names'])
        self.assertEqual(str(terms[1]), 'z_A')
        self.assertEqual(terms[1].latex, 'z_{A}')
        self.assertIn('^2', terms[2].latex)
        self.assertIn(r'\frac', coding[0].latex)
        for latex in pieces + [item.latex for item in coding]:
            content = formula_html(latex)
            self.assertIn('Microsoft YaHei', content)
            self.assertNotIn('<img', content)
            self.assertNotIn('\\', content)
        self.assertTrue((coefficients == model['coef']).all())

    def test_formula_is_copyable_text_and_scales_with_surrounding_font(self):
        content = formula_html(r'z_b=\frac{b-50}{10}+6.47248\times 10^{-59}')
        doc = QTextDocument()
        widths = []
        for size in (13, 26):
            font = QFont('Microsoft YaHei')
            font.setPixelSize(size)
            doc.setDefaultFont(font)
            doc.setHtml(content)
            widths.append(doc.idealWidth())
        self.assertIn('zb=(b−50) / 10+6.47248 × 10−59', doc.toPlainText())
        self.assertGreater(widths[1], widths[0] * 1.8)
        formats = []
        it = doc.begin().begin()
        while not it.atEnd():
            formats.append(it.fragment().charFormat().verticalAlignment())
            self.assertFalse(it.fragment().charFormat().isImageFormat())
            it += 1
        self.assertIn(QTextCharFormat.VerticalAlignment.AlignSuperScript, formats)
        self.assertIn(QTextCharFormat.VerticalAlignment.AlignSubScript, formats)

    def test_literal_names_and_prose_are_escaped(self):
        self.assertEqual(rich_text('<script>x</script>'), '&lt;script&gt;x&lt;/script&gt;')
        self.assertEqual(rich_text('path_name.csv'), 'path_name.csv')
        for name in ['b_1', '长度', 'a$b', 'Q{a}', r'a\b', '<img src=x>', 'a&b^c~d#1%']:
            with self.subTest(name=name):
                doc = QTextDocument()
                doc.setHtml(formula_html(symbol(name), name))
                self.assertEqual(doc.toPlainText(), name)
        for text in ['R²', 'x1²', 'x1·x2', 'σ=区间宽度/(2k)', 'μ±kσ', 'σ ≤ 2', '2^k', 'L12 (2^11)']:
            self.assertIn('<span ', rich_text(text))
            self.assertNotIn('<img', rich_text(text))
        self.assertIn('<sup>11</sup>', rich_text('L12 (2^11)'))

    def test_all_known_formulas_and_snapshot_notation_render_without_tex_or_images(self):
        for latex in [*NOTATION.values(), r'\sigma / \sigma_{\mathrm{max}}',
                      r'\theta+\gamma+\epsilon', r'10^{60}+10^{-90}',
                      r'e_i=y_i-\widehat{y}_i']:
            with self.subTest(latex=latex):
                content = formula_html(latex)
                self.assertNotIn('\\', content)
                self.assertNotIn('<img', content)
        self.assertIn('ŷ<sub>i</sub>', formula_html(NOTATION['残差 = 观测值 − 预测值']))
        self.assertIn('&lt;bad&gt;', formula_html(r'\unknown{a}', '<bad>'))
        self.assertIn('&lt;bad&gt;', formula_html('x_{', '<bad>'))

    def test_table_preserves_raw_data_and_fits_inline_fraction(self):
        value = Math('z_b = (b - 50) / 10', r'z_b=\frac{b-50}{10}')
        table = SummaryTable(['换算关系'], [[value]])
        self.addCleanup(table.deleteLater)
        self.assertEqual(table.item(0, 0).text(), str(value))
        self.assertIn('z<sub>b</sub>=(b−50) / 10', table.item(0, 0).data(MATH_ROLE))
        self.assertNotIn('<img', table.item(0, 0).data(MATH_ROLE))
        option = QStyleOptionViewItem()
        option.initFrom(table)
        height = table.itemDelegate().sizeHint(option, table.model().index(0, 0)).height()
        self.assertGreaterEqual(table.rowHeight(0), height)

    def test_combo_keeps_configuration_keys(self):
        combo = QComboBox()
        self.addCleanup(combo.deleteLater)
        choices = ['全因子 2^k（小因子数）', '部分析因 1/2 分数']
        combo.addItems(choices)
        decorate_combo(combo)
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], choices)
        self.assertIn('2<sup>k</sup>', combo.itemData(0, MATH_ROLE))
        self.assertNotIn('<img', combo.itemData(1, MATH_ROLE))

    def test_report_uses_the_same_serializable_formulas(self):
        project, context = make_context()
        project.workbench_result = analysis_service.analyze(project, context, {})['snapshot']
        # Report export consumes a serializable snapshot, never a fitted callable.
        project.workbench_result = report_engine.serializable(project.workbench_result)
        report = report_engine.build_current_report(report_engine.bundle(project))
        formulas = [b for s in report['sections'] for b in s['blocks'] if b['type'] == 'formula']
        self.assertEqual(len(formulas), 3)
        html = report_engine.render_html(report)
        self.assertIn('z<sub>A</sub>', html)
        self.assertNotIn('\\frac', html)
        for block in formulas:
            for part in block['parts']:
                content = formula_html(part)
                self.assertNotIn('<img', content)
                self.assertNotIn('\\', content)

    def test_formula_pdf_contains_fonts_without_formula_image_objects(self):
        content = formula_html(r'Y=2+z_A^2+6.47248\times 10^{-5}')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'formula.pdf'
            export_pdf(content, path)
            data = path.read_bytes()
        self.assertTrue(data.startswith(b'%PDF-'))
        self.assertIn(b'/Font', data)
        self.assertNotIn(b'/Subtype /Image', data)


if __name__ == '__main__':
    unittest.main()
