$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Create .venv and install requirements-build.txt first." }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed." }
$buildWork = Join-Path ([System.IO.Path]::GetTempPath()) "structure-design-build"
& $python -m PyInstaller --noconfirm --workpath $buildWork 软件打包.spec
if ($LASTEXITCODE -ne 0) { throw "Build failed." }
