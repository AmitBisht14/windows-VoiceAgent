; Inno Setup script. Build the PyInstaller bundle first, then compile this file
; with Inno Setup 6 (iscc packaging\installer.iss).

#define AppName "Voice Agent"
#define AppVersion "0.1.0"
#define AppExe "VoiceAgent.exe"

[Setup]
AppId={{6F0C3B4E-8E2A-4C61-9B7A-5D2F1E0A9C11}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\VoiceAgent
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=VoiceAgentSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "startup"; Description: "Start Voice Agent when I sign in"; GroupDescription: "Options:"

[Files]
Source: "..\dist\VoiceAgent\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
