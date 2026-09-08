#define AppVersion "0.3.0-alpha.2"
[Setup]
AppId={{BF44D1E4-0583-4201-8966-C19733FC8EE2}
AppName=CaliSift
AppVersion={#AppVersion}
AppPublisher=CaliSift contributors
AppPublisherURL=https://github.com/StellarYige/CaliSift
DefaultDirName={localappdata}\Programs\CaliSift
DefaultGroupName=CaliSift
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
OutputDir=..\artifacts\release
OutputBaseFilename=CaliSift-{#AppVersion}-windows-x64-setup
SetupIconFile=..\resources\calisift.ico
UninstallDisplayIcon={app}\CaliSift.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupMutex=CaliSiftSetup

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\CaliSift\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\artifacts\toolchain\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Flags: dontcopy

[Icons]
Name: "{group}\CaliSift"; Filename: "{app}\CaliSift.exe"
Name: "{autodesktop}\CaliSift"; Filename: "{app}\CaliSift.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CaliSift.exe"; Description: "Open CaliSift"; Flags: nowait postinstall skipifsilent

[Code]
function HasWebView2(): Boolean;
var Version: String;
begin
  Result := (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer; Previous: String;
begin
  Result := '';
  Previous := ExpandConstant('{app}\calisift-cli.exe');
  if FileExists(Previous) then begin
    if not Exec(Previous, 'checkpoint', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then begin
      Result := 'Close CaliSift and retry. A data recovery point could not be created; existing data has been retained.';
      exit;
    end;
  end;
  if not HasWebView2() then begin
    ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code) or not HasWebView2() then
      Result := 'WebView2 could not be installed. Install the official Microsoft WebView2 Runtime, then run this setup again.';
  end;
end;

// User data is outside {app}. Uninstall intentionally has no data-deletion entry.
