; RODAS Windows installer script for Inno Setup 6
; Build:  ISCC.exe packaging\RODAS.iss
;     or: powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1
;
; NOTE: All UI strings are ASCII on purpose. ISCC reads .iss files as ANSI unless
; the file carries a UTF-8 BOM, so Chinese literals here could be garbled on a
; clean machine. See packaging\README.md for the Chinese UI option.

#define MyAppName "RODAS"
#define MyAppVersion "0.2"
#define MyAppPublisher "RODAS"
#define MyAppExeName "RODAS.exe"

[Setup]
AppId={{2472AF40-89E1-4664-861D-41FE37029080}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={commonpf64}\RODAS
DefaultGroupName=RODAS
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=RODAS-Setup-{#MyAppVersion}
SetupIconFile={#SourcePath}\RODAS.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Chinese UI: place ChineseSimplified.isl next to this script, then uncomment:
; Name: "chinesesimplified"; MessagesFile: "{#SourcePath}\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional tasks:"; Flags: unchecked

[Files]
Source: "..\dist\RODAS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RODAS"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall RODAS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\RODAS"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch RODAS"; Flags: nowait postinstall skipifsilent

; ---------------------------------------------------------------------------
; OPTIONAL: .rodas file association. Do NOT enable until main.py reads the path
; passed as sys.argv[1] (currently it does not). Then uncomment this section:
;
; [Registry]
; Root: HKA; Subkey: "Software\Classes\.rodas"; ValueType: string; ValueName: ""; ValueData: "RODAS.TaskFile"; Flags: uninsdeletevalue
; Root: HKA; Subkey: "Software\Classes\RODAS.TaskFile"; ValueType: string; ValueName: ""; ValueData: "RODAS task file"; Flags: uninsdeletekey
; Root: HKA; Subkey: "Software\Classes\RODAS.TaskFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
; Root: HKA; Subkey: "Software\Classes\RODAS.TaskFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
; ---------------------------------------------------------------------------
