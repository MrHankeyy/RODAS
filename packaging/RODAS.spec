# Windows x64, directory bundle. Windowed release build with a bootloader splash.
from pathlib import Path

root = Path(SPECPATH).resolve().parent
datas = [(str(root / 'assets'), 'assets')]
for folder in sorted((root.parent / 'demos').glob('demo_*')):
    for item in sorted(folder.iterdir()):
        if item.is_file() and item.suffix.lower() in ('.csv', '.rodas', '.md'):
            datas.append((str(item), f'demos/{folder.name}'))

a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    datas=datas,
    hiddenimports=['PyQt6.QtSvg'],
    hooksconfig={'matplotlib': {'backends': ['QtAgg']}},
    excludes=['PyQt5', 'PySide2', 'PySide6'],
)
# Bootloader splash: shown from process start (before Python is even ready) and
# dismissed by main.py once the main window is painted. In onedir mode the
# splash target belongs to EXE while splash.binaries belongs to COLLECT.
splash = Splash(
    str(root / 'packaging' / 'RODAS-splash.png'),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(40, 298),
    text_size=-13,
    # PyInstaller writes this verbatim into `font create -family ...`; a family
    # containing spaces (e.g. "Microsoft YaHei") breaks the Tcl parser and the
    # whole splash script aborts, leaving a bare Tk window. SimHei has no space
    # and ships with Windows.
    text_font='SimHei',
    text_color='#365D80',
    text_default='正在启动 RODAS…',
    max_img_size=(760, 480),
    always_on_top=True,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    splash,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RODAS',
    console=False,
    icon=str(root / 'icon.png'),
    upx=False,
)
COLLECT(exe, a.binaries, a.datas, splash.binaries, name='RODAS', upx=False)
