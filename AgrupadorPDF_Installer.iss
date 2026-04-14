; ============================================================
;  AgrupadorPDF_Installer.iss  -  Inno Setup 6.x
;  Gera: AgrupadorPDF_v1.6.4_Installer.exe
; ============================================================

#define AppName      "AgrupadorPDF"
#define AppVersion   "1.6.4"
#define AppPublisher "Brian Marques"
#define AppExeName   "AgrupadorPDF.exe"
#define AppDocName   "AgrupadorPDF_Documentacao.docx"
#define AppIcon      "AgrupadorPDF.ico"
#define AppURL       ""

[Setup]
AppId={{A3F2C1D4-8B5E-4F7A-9C2D-1E6B3A5D8F2C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir=dist_installer
OutputBaseFilename=AgrupadorPDF_v{#AppVersion}_Installer
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} v{#AppVersion}

Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no

VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} - Agrupador de PDFs Fiscais
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

CreateUninstallRegKey=yes
Uninstallable=yes


; -- Idioma Portugues Brasil ---------------------------------------------------
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"


; -- Arquivos a instalar ------------------------------------------------------
[Files]
Source: "dist\{#AppExeName}";  DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#AppDocName}";  DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist


; -- Atalhos ------------------------------------------------------------------
[Icons]
Name: "{userdesktop}\{#AppName}";       Filename: "{app}\{#AppExeName}"; \
      IconFilename: "{app}\{#AppExeName}"; Comment: "Agrupador de PDFs Fiscais"

Name: "{group}\{#AppName}";             Filename: "{app}\{#AppExeName}"; \
      IconFilename: "{app}\{#AppExeName}"; Comment: "Agrupador de PDFs Fiscais"

Name: "{group}\Documentacao";           Filename: "{app}\{#AppDocName}"; \
      Comment: "Manual do AgrupadorPDF"

Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"


; -- Execucao pos-instalacao --------------------------------------------------
[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "Abrir {#AppName} agora"; \
  Flags: nowait postinstall skipifsilent


; -- Registro -----------------------------------------------------------------
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}"; \
  ValueType: string; ValueName: "DisplayName";     ValueData: "{#AppName}";    Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}"; \
  ValueType: string; ValueName: "DisplayVersion";  ValueData: "{#AppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}"; \
  ValueType: string; ValueName: "Publisher";       ValueData: "{#AppPublisher}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}"; \
  ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}"; \
  ValueType: dword;  ValueName: "NoModify";        ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}"; \
  ValueType: dword;  ValueName: "NoRepair";         ValueData: 1


; -- Textos do wizard ---------------------------------------------------------
[Messages]
WelcomeLabel1=Bem-vindo ao instalador do [name]
WelcomeLabel2=Este assistente vai instalar o [name/ver] no seu computador.%n%nFeche outros programas antes de continuar.
SelectDirLabel3=O [name] sera instalado na seguinte pasta:
SelectDirBrowseLabel=Para escolher outra pasta, clique em Procurar.
ReadyLabel1=Pronto para instalar o [name/ver].
ReadyLabel2a=Clique em Instalar para continuar.
ButtonInstall=Instalar
ButtonNext=Proximo >
ButtonBack=< Voltar
ButtonCancel=Cancelar
ButtonFinish=Concluir
FinishedHeadingLabel=Instalacao concluida!
FinishedLabel=O [name] foi instalado com sucesso no seu computador.%n%nClique em Concluir para sair.
ClickFinish=Concluir
StatusExtractFiles=Extraindo arquivos...
StatusCreateIcons=Criando atalhos...
StatusRegisterFiles=Registrando arquivos...
UninstallAppFullTitle=Desinstalar {#AppName}
ConfirmUninstall=Tem certeza que deseja desinstalar o %1 e todos os seus componentes?
UninstallStatusLabel=Removendo o [name] do seu computador...


; -- Limpeza ao desinstalar ---------------------------------------------------
[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigFile: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    ConfigFile := ExpandConstant('{%USERPROFILE}\.agrupadorpdf.json');
    if FileExists(ConfigFile) then
      DeleteFile(ConfigFile);
  end;
end;
