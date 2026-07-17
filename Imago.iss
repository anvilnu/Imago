; Inno Setup: instalador de Imago. Requiere Inno Setup 6.3 o superior.
; Compilar abriendo este archivo en Inno Setup y pulsando Build, o por consola:
;   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" Imago.iss
; Resultado: installer\ImagoSetup.exe
;
; IMPORTANTE: antes de compilar el instalador hay que haber construido el .exe
; (dist\Imago\ con PyInstaller). Este script empaqueta esa carpeta.

[Setup]
AppName=Imago
AppVersion=1.0
AppPublisher=AVNSoft
DefaultDirName={autopf}\Imago
DefaultGroupName=Imago
UninstallDisplayIcon={app}\Imago.exe
OutputBaseFilename=ImagoSetup
OutputDir=installer
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icons\imago.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Imago\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Imago"; Filename: "{app}\Imago.exe"; WorkingDir: "{app}"
Name: "{group}\Desinstalar Imago"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Imago"; Filename: "{app}\Imago.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Imago.exe"; Description: "{cm:LaunchProgram,Imago}"; Flags: nowait postinstall skipifsilent
