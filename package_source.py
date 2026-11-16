"""生成源代码提交包，不包含本地测试、缓存和开发记录。"""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    "main.py",
    "requirements.txt",
    "requirements.lock.txt",
    "requirements-build.txt",
    "软件打包.spec",
    "build.ps1",
    "package_source.py",
    "ruff.toml",
]
DIRECTORIES = ["backend", "frontend", "assets", "packaging"]


def main():
    paths = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    paths = sorted(set(paths))
    manifest = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }
    target = ROOT.parent / "RODAS_v1.0_源代码提交包.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ROOT))
        archive.writestr("文件校验.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for name, digest in manifest.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    print(f"{target}: {len(paths)} files")


if __name__ == "__main__":
    main()
