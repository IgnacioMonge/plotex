; Plotex Installer Script for Inno Setup 6
; Compile with: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" plotex_installer.iss

#define MyAppName "Plotex"
#define MyAppVersion "1.4"
#define MyAppPublisher "M. Ignacio Monge García"
#define MyAppURL "https://github.com/imongegar/plotex"
#define MyAppExeName "plotex.exe"
#define BuildDir "C:\veusz_build\dist\plotex_main"
#define IconFile "..\icons\plotex.ico"

[Setup]
AppId={{E8B3F2A1-7C5D-4D8E-9F1A-2B3C4D5E6F7A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile={#BuildDir}\COPYING
OutputDir=C:\veusz_build\installer
OutputBaseFilename=Plotex-{#MyAppVersion}-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\plotex.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc_vsz"; Description: "Associate .vsz files with {#MyAppName}"; GroupDescription: "File associations:"
Name: "fileassoc_vszh5"; Description: "Associate .vszh5 files with {#MyAppName}"; GroupDescription: "File associations:"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; .vsz file association
Root: HKA; Subkey: "Software\Classes\.vsz"; ValueType: string; ValueName: ""; ValueData: "PlotexDocument"; Flags: uninsdeletevalue; Tasks: fileassoc_vsz
Root: HKA; Subkey: "Software\Classes\PlotexDocument"; ValueType: string; ValueName: ""; ValueData: "Plotex Document"; Flags: uninsdeletekey; Tasks: fileassoc_vsz
Root: HKA; Subkey: "Software\Classes\PlotexDocument\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: fileassoc_vsz
Root: HKA; Subkey: "Software\Classes\PlotexDocument\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc_vsz

; .vszh5 file association
Root: HKA; Subkey: "Software\Classes\.vszh5"; ValueType: string; ValueName: ""; ValueData: "PlotexHDF5Document"; Flags: uninsdeletevalue; Tasks: fileassoc_vszh5
Root: HKA; Subkey: "Software\Classes\PlotexHDF5Document"; ValueType: string; ValueName: ""; ValueData: "Plotex HDF5 Document"; Flags: uninsdeletekey; Tasks: fileassoc_vszh5
Root: HKA; Subkey: "Software\Classes\PlotexHDF5Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: fileassoc_vszh5
Root: HKA; Subkey: "Software\Classes\PlotexHDF5Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc_vszh5

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
