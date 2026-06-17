[Setup]
AppName=Simple Suite
AppVersion=2.5.0
VersionInfoVersion=2.5.0
AppPublisher=Simple Suite
DefaultDirName={localappdata}\SimpleSuite
DefaultGroupName=Simple Suite
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=SimpleSetup
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\SimpleHub.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce

[Files]
Source: "dist\SimpleHub.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SimpleResolver.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SimpleDownloader.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\update_helper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\hashes.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Simple Suite"; Filename: "{app}\SimpleHub.exe"
Name: "{userdesktop}\Simple Suite"; Filename: "{app}\SimpleHub.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SimpleHub.exe"; Description: "Abrir Simple Suite"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
