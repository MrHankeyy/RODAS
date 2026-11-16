; 基于不确定性量化的复杂工程结构鲁棒优化设计平台 Windows 安装脚本（Inno Setup 6）
; Build:  ISCC.exe packaging\RODAS.iss
;     or: powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1
;
; 本文件必须保存为 UTF-8 BOM 编码（ISCC 依靠 BOM 识别中文文案）。
; 简体中文界面由同目录 ChineseSimplified.isl 提供（Inno Setup 6.3+ 官方语言文件）。
;
; 软件本体不做改动：exe 仍为 RODAS.exe，窗口标题、启动画面维持原样。

#ifndef MyAppName
#define MyAppName "基于不确定性量化的复杂工程结构鲁棒优化设计平台"
#endif
#ifndef MyAppVersion
#define MyAppVersion "1.0"
#endif
#define MyAppPublisher MyAppName
#define MyAppExeName "RODAS.exe"

[Setup]
AppId={{2472AF40-89E1-4664-861D-41FE37029080}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} V{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={commonpf64}\RODAS
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=RODAS-Setup-V{#MyAppVersion}
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
Source: "..\dist\RODAS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载{#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

; ---------------------------------------------------------------------------
; 可选：.rodas 文件关联。启用前必须先让 main.py 读取 sys.argv[1]（目前未实现），
; 否则双击任务文件只会打开空界面。需要时取消以下注释：
;
; [Registry]
; Root: HKA; Subkey: "Software\Classes\.rodas"; ValueType: string; ValueName: ""; ValueData: "RODAS.TaskFile"; Flags: uninsdeletevalue
; Root: HKA; Subkey: "Software\Classes\RODAS.TaskFile"; ValueType: string; ValueName: ""; ValueData: "基于不确定性量化的复杂工程结构鲁棒优化设计平台任务文件"; Flags: uninsdeletekey
; Root: HKA; Subkey: "Software\Classes\RODAS.TaskFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
; Root: HKA; Subkey: "Software\Classes\RODAS.TaskFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
; ---------------------------------------------------------------------------
