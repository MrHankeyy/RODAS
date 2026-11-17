
#ifndef MyAppName
#define MyAppName "基于不确定性量化的复杂工程结构鲁棒优化设计平台"
#endif
#ifndef MyAppVersion
#define MyAppVersion "1.0"
#endif
#define MyAppPublisher MyAppName
#define MyAppExeName "ROD.exe"

[Setup]
AppId={{2472AF40-89E1-4664-861D-41FE37029080}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} V{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={commonpf64}\ROD
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=ROD-Setup-V{#MyAppVersion}
SetupIconFile={#SourcePath}\RODAS.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#SourcePath}\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "..\dist\ROD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载{#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
