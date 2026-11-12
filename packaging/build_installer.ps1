<#
Build the RODAS Windows installer from the PyInstaller directory bundle.

Usage (from the RODAS project root):
  powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1
  powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1 -Rebuild
  powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1 -IsccPath 'D:\Software\Inno Setup 6\ISCC.exe'

-Rebuild regenerates the splash PNG if missing, clears Anaconda from PATH,
re-runs PyInstaller with --clean -y, then compiles the installer.
Omit it to reuse the already verified dist\RODAS.
-IsccPath / $env:RODAS_ISCC override compiler discovery when Inno Setup is in a
non-default location.
#>
param(
    [switch]$Rebuild,
    [string]$IsccPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path (Split-Path -Parent $root) 'RODAS-build-env\Scripts\python.exe'

if ($Rebuild) {
    if (-not (Test-Path $py)) { throw "Build Python not found: $py" }

    # Regenerate the splash artwork if it is missing (e.g. fresh checkout).
    $splashPng = Join-Path $PSScriptRoot 'RODAS-splash.png'
    if (-not (Test-Path $splashPng)) {
        & $py (Join-Path $PSScriptRoot 'make_splash.py')
        if ($LASTEXITCODE -ne 0) { throw 'Splash image generation failed' }
    }

    $env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notlike '*Anaconda*' }) -join ';'
    Push-Location $root
    try {
        # -y removes the previous dist\RODAS; --clean alone does NOT clear it.
        & $py -m PyInstaller --clean -y --distpath .\dist --workpath .\build .\packaging\RODAS.spec
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    }
    finally { Pop-Location }
}

$bundle = Join-Path $root 'dist\RODAS'
if (-not (Test-Path (Join-Path $bundle 'RODAS.exe'))) {
    throw "Bundle not found: $bundle. Run PyInstaller first, or use -Rebuild."
}

function Find-Iscc {
    if ($IsccPath) {
        if (Test-Path $IsccPath) { return (Resolve-Path $IsccPath).Path }
        throw "-IsccPath does not exist: $IsccPath"
    }
    if ($env:RODAS_ISCC -and (Test-Path $env:RODAS_ISCC)) { return $env:RODAS_ISCC }

    $fromPath = Get-Command iscc -ErrorAction SilentlyContinue
    if ($fromPath) { return $fromPath.Source }

    # Registry InstallLocation covers custom install folders (e.g. D:\Software\Inno Setup 6).
    $roots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($r in $roots) {
        foreach ($item in @(Get-ItemProperty $r -ErrorAction SilentlyContinue)) {
            if ($item.DisplayName -match 'Inno Setup' -and $item.InstallLocation) {
                $c = Join-Path $item.InstallLocation 'ISCC.exe'
                if (Test-Path $c) { return $c }
            }
        }
    }

    $common = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 7\ISCC.exe'),
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe',
        'C:\Program Files (x86)\Inno Setup 7\ISCC.exe',
        'C:\Program Files\Inno Setup 7\ISCC.exe',
        'D:\Software\Inno Setup 6\ISCC.exe'
    )
    foreach ($c in $common) { if (Test-Path $c) { return $c } }
    return $null
}

$iscc = Find-Iscc
if (-not $iscc) {
    $msg = "ISCC.exe (Inno Setup 6/7) not found. Searched: -IsccPath, RODAS_ISCC, PATH, registry InstallLocation, common install folders.`n" +
           "Install: winget install --id JRSoftware.InnoSetup -e -s winget -i`n" +
           "Or pass the compiler: -IsccPath 'D:\Software\Inno Setup 6\ISCC.exe'"
    throw $msg
}
Write-Host "ISCC: $iscc"

$iss = Join-Path $PSScriptRoot 'RODAS.iss'
& $iscc $iss
if ($LASTEXITCODE -ne 0) { throw 'ISCC compile failed' }

$out = Join-Path $root 'dist\RODAS-Setup-0.2.exe'
if (Test-Path $out) {
    $size = [math]::Round((Get-Item $out).Length / 1MB, 1)
    Write-Host "Installer ready: $out ($size MB)"
} else {
    Write-Host 'ISCC finished; check dist\ for the generated setup executable.'
}
