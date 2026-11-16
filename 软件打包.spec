# Shared directory bundle configuration, including splash and DLL isolation.
from pathlib import Path

SPECPATH = str(Path(SPECPATH) / "packaging")
shared_spec = Path(SPECPATH) / "RODAS.spec"
exec(compile(shared_spec.read_text(encoding="utf-8"), str(shared_spec), "exec"))
