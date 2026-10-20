[Setup]
AppName=KeyNote
AppVersion=1.0.0
AppPublisher=KeyNote Project
DefaultDirName={localappdata}\KeyNote
DisableDirPage=no
UsePreviousAppDir=no
DefaultGroupName=KeyNote
OutputDir=installer
OutputBaseFilename=KeyNote_Setup
Compression=lzma2/max
SolidCompression=yes
UninstallDisplayIcon={app}\KeyNote.App.exe
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动 KeyNote"; GroupDescription: "启动选项："; Flags: checkedonce

[Files]
; .NET self-contained 发布产物(含 WindowsAppSDK 运行时)
Source: "dist\*"; DestDir: "{app}"; Excludes: "KeyNote_Setup.exe"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\KeyNote"; Filename: "{app}\KeyNote.App.exe"
Name: "{commondesktop}\KeyNote"; Filename: "{app}\KeyNote.App.exe"; Tasks: desktopicon
Name: "{group}\说明 (README)"; Filename: "{app}\README.md"
Name: "{group}\卸载 KeyNote"; Filename: "{uninstallexe}"

[Registry]
; 开机自启（也可在应用内设置面板开关）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KeyNote"; ValueData: """{app}\KeyNote.App.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\KeyNote.App.exe"; Description: "启动 KeyNote"; Flags: postinstall nowait skipifsilent shellexec
