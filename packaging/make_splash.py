r"""Generate the compact RODAS splash image used by PyInstaller's Splash target.

Kept in packaging/ so the artwork can be regenerated whenever the brand or
version changes. All geometry mirrors frontend/pages/welcome_page.py.

Usage (from the project root):
    ..\RODAS-build-env\Scripts\python.exe packaging\make_splash.py
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.domain.application import APPLICATION_NAME, APPLICATION_VERSION

OUT = ROOT / 'packaging' / 'RODAS-splash.png'
LOGO = ROOT / 'assets' / 'branding' / 'brand-wordmark.png'

W, H = 720, 340          # final png size (Splash max_img_size is 760x480)
S = 2                    # supersampling factor for smooth lines/text

NAVY = '#21354D'
DEEP = '#173B64'
TEAL = '#168CB4'
MUTED = '#65768A'
FAINT = '#8A99AA'
LINE = '#E2E8F0'
TRACK = '#EDF3F9'
WHITE = '#FFFFFF'

FONTS = Path('C:/Windows/Fonts')


def font(name, size):
    """Load a TTF/TTC font at supersampled pixel size."""
    for candidate in (FONTS / name, FONTS / 'msyh.ttc', FONTS / 'simhei.ttf'):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), int(size * S))
    return ImageFont.load_default()


def surface_point(x, y):
    """Same response-surface parametrisation as WelcomePage.ResponseSurface."""
    z = .84 * math.exp(-2.3 * ((x - .15) ** 2 + (y + .1) ** 2))
    z -= .35 * math.exp(-3 * ((x + .5) ** 2 + (y - .5) ** 2))
    z += .08 * x
    return 190 + (x - y) * 82, 155 + (x + y) * 39 - z * 81


def blend(color, alpha):
    """Blend a hex colour onto white, mimicking QColor.setAlphaF."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(round(255 * (1 - alpha) + c * alpha) for c in (r, g, b))


def draw_surface(draw, box):
    """Draw the wireframe surface + sample points inside a target box."""
    x0, y0, x1, y1 = box
    scale = min((x1 - x0) / 380, (y1 - y0) / 280)
    off_x = x0 + ((x1 - x0) - 380 * scale) / 2
    off_y = y0 + ((y1 - y0) - 280 * scale) / 2

    def t(px, py):
        return ((off_x + px * scale) * S, (off_y + py * scale) * S)

    for axis in range(2):
        for j in range(18):
            fixed = -1 + 2 * j / 17
            color = blend(TEAL, .58 if j % 3 == 0 else .22)
            path = []
            for k in range(35):
                v = -1 + 2 * k / 34
                path.append(t(*surface_point(v, fixed) if axis else surface_point(fixed, v)))
            draw.line(path, fill=color, width=max(1, S), joint='curve')

    radius = 3.2 * scale * S
    for x, y in [(-.7, -.3), (.1, -.1), (.7, .2), (-.2, .6), (.4, -.7)]:
        cx, cy = t(*surface_point(x, y))
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=TEAL)


def main():
    img = Image.new('RGB', (W * S, H * S), WHITE)
    d = ImageDraw.Draw(img)

    # Top accent rule: a short brand-coloured segment on a faint baseline.
    d.rectangle((0, 0, 180 * S, 3 * S), fill=TEAL)
    d.rectangle((180 * S, 0, W * S, 3 * S), fill='#E8EEF3')

    # Welcome line.
    d.text((40 * S, 34 * S), f'欢迎使用 ROD   /   V{APPLICATION_VERSION}',
           font=font('msyh.ttc', 12), fill=FAINT)

    # Use the complete wordmark; the current asset is already cropped.
    artwork = Image.open(LOGO).convert('RGBA')
    logo_w = 360
    logo_h = round(logo_w * artwork.height / artwork.width)
    artwork = artwork.resize((logo_w * S, logo_h * S), Image.LANCZOS)
    img.paste(artwork, (40 * S, 60 * S), artwork)

    # Chinese title + tagline.
    d.text((40 * S, 160 * S), APPLICATION_NAME,
           font=font('msyhbd.ttc', 16), fill=NAVY)
    d.text((40 * S, 198 * S), '从试验与数据出发，探索更稳健的结构设计。',
           font=font('msyh.ttc', 12), fill=MUTED)

    # Wireframe response surface on the right.
    draw_surface(d, (452, 52, 690, 252))

    # Divider.
    d.rectangle((40 * S, 262 * S, 680 * S, 263 * S), fill=LINE)

    # The left half of the status row is intentionally left blank: the live
    # status text is drawn at runtime by pyi_splash.update_text() with
    # text_pos=(40, 298) in RODAS.spec. The right half carries the version.
    version = f'ROD  ·  V{APPLICATION_VERSION}'
    vf = font('segoeui.ttf', 11)
    tw = d.textlength(version, font=vf)
    d.text((680 * S - tw, 278 * S), version, font=vf, fill=FAINT)

    # Progress track (decorative; the live status text carries the real state).
    d.rounded_rectangle((40 * S, 308 * S, 680 * S, 311 * S), radius=2 * S, fill=TRACK)
    d.rounded_rectangle((40 * S, 308 * S, 296 * S, 311 * S), radius=2 * S, fill=TEAL)

    img = img.resize((W, H), Image.LANCZOS)
    img.save(OUT, format='PNG', optimize=True)
    print(f'{OUT}  {img.size[0]}x{img.size[1]}  {OUT.stat().st_size} bytes')

    icon = Image.open(ROOT / 'assets' / 'branding' / 'brand-icon.png').convert('RGBA')
    icon.thumbnail((256, 256), Image.LANCZOS)
    square = Image.new('RGBA', (256, 256), (255, 255, 255, 0))
    square.alpha_composite(icon, ((256 - icon.width) // 2, (256 - icon.height) // 2))
    square.save(ROOT / 'packaging' / 'RODAS.ico', format='ICO',
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (128, 128), (256, 256)])


if __name__ == '__main__':
    main()
