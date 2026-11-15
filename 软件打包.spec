# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys
import PyQt6
from PyInstaller.utils.hooks import collect_submodules
sys.path.insert(0, SPECPATH)
from backend.domain.application import APPLICATION_NAME

hidden = collect_submodules("sklearn", filter=lambda name: ".tests" not in name and ".torch" not in name)
qt_bin = Path(PyQt6.__file__).parent / "Qt6" / "bin"
runtimes = [(str(p), ".") for p in qt_bin.glob("*140*.dll")]
a = Analysis(["main.py"], pathex=[], binaries=runtimes,
             datas=[("assets", "assets")], hiddenimports=hidden,
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["pandas", "pyqtgraph"])
# Qt uses the Windows ICU API; unrelated tools on PATH may provide incompatible DLLs.
library_roots = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
                 Path(os.environ["SystemRoot"]).resolve(), Path(SPECPATH).resolve()]
a.binaries = [entry for entry in a.binaries
              if any(Path(entry[1]).resolve().is_relative_to(root) for root in library_roots)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APPLICATION_NAME,
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APPLICATION_NAME)
