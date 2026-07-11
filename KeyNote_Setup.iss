[Setup]
AppName=KeyNote
AppVersion=1.0.0
AppPublisher=KeyNote Project
DefaultDirName={autopf}\KeyNote
DefaultGroupName=KeyNote
OutputDir=installer
OutputBaseFilename=KeyNote_Setup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\KeyNote.exe
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动 KeyNote"; GroupDescription: "启动选项："; Flags: checkedonce

[Files]
Source: "dist\KeyNote.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\KeyNote"; Filename: "{app}\KeyNote.exe"
Name: "{commondesktop}\KeyNote"; Filename: "{app}\KeyNote.exe"; Tasks: desktopicon
Name: "{group}\说明 (README)"; Filename: "{app}\README.md"
Name: "{group}\卸载 KeyNote"; Filename: "{uninstallexe}"

[Registry]
; 开机自启（由用户通过安装任务或设置面板控制）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KeyNote"; ValueData: """{app}\KeyNote.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\KeyNote.exe"; Description: "启动 KeyNote"; Flags: postinstall nowait skipifsilent shellexec

[UninstallRun]
Filename: "{app}\KeyNote.exe"; Parameters: "--uninstall"; Flags: runhidden
