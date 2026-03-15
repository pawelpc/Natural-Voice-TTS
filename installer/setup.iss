; Inno Setup script for Natural Voice TTS
; Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
; Usage: ISCC.exe installer\setup.iss
; Expects PyInstaller output in dist\NaturalVoiceTTS\

#define MyAppName "Natural Voice TTS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Paul Pawelski"
#define MyAppExeName "NaturalVoiceTTS.exe"

[Setup]
AppId={{E8A1F4C2-9B3D-4E5F-A6C7-8D9E0F1A2B3C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright 2025 {#MyAppPublisher}
DefaultDirName={autopf}\NaturalVoiceTTS
DefaultGroupName={#MyAppName}
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=NaturalVoiceTTS_Setup_{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Install everything from the PyInstaller dist folder
Source: "..\dist\NaturalVoiceTTS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any runtime-generated files in the install directory
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Do you want to keep your settings in' + #13#10 +
              ExpandConstant('{userappdata}\NaturalVoiceTTS') + '?',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      DelTree(ExpandConstant('{userappdata}\NaturalVoiceTTS'), True, True, True);
    end;
  end;
end;
