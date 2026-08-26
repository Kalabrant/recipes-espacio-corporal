; =============================================================================
; Instalador de «Récipes — Espacio Corporal» (§11.2)
;
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" build/instalador.iss
;
; Sale en:  build\salida\RecipesMedicos-Setup-2.0.0.exe
;
; Tres reglas que este archivo hace cumplir:
;
;  1. **Sin administrador** (§11.2). PrivilegesRequired=lowest: instala en la
;     carpeta del usuario, así que Windows no pide elevación y el médico puede
;     instalarlo en una máquina donde no es administrador.
;  2. **Nunca toca la carpeta de datos** (§11.3). No hay ni una línea que
;     nombre Documents\Recipes: no la crea, no la copia, no la borra. La crea
;     la app sola al abrirse por primera vez. Por eso [UninstallDelete] está
;     vacío a propósito: desinstalar saca el programa, jamás los récipes.
;     Instalar encima tampoco pisa nada del médico.
;  3. **Cero red** (§2.1): todo lo que hace falta ya está adentro del .exe;
;     el instalador no descarga nada, ni siquiera un runtime.
;
; El GUID de AppId se generó una sola vez y **no se cambia nunca**: es lo que
; le permite a Windows reconocer una versión anterior y actualizarla encima en
; lugar de dejar dos instalaciones y dos entradas en «Agregar o quitar
; programas».
; =============================================================================

#define MiNombre       "Récipes Espacio Corporal"
#define MiVersion      "2.1.0"
#define MiEditor       "Espacio Corporal"
#define MiEjecutable   "RecipesMedicos.exe"
#define MiCarpetaDist  "dist\RecipesMedicos"

[Setup]
AppId={{50AAC252-976B-479F-8804-2757948B74B8}
AppName={#MiNombre}
AppVersion={#MiVersion}
AppVerName={#MiNombre} {#MiVersion}
VersionInfoVersion={#MiVersion}
AppPublisher={#MiEditor}

; --- sin administrador (§11.2) -----------------------------------------------
PrivilegesRequired=lowest
; Habilita el /CURRENTUSER de la línea de comandos para las pruebas y para una
; instalación desatendida; el modo por omisión sigue siendo el del usuario.
PrivilegesRequiredOverridesAllowed=commandline

; --- dónde ------------------------------------------------------------------
DefaultDirName={localappdata}\Programs\RecipesMedicos
DefaultGroupName={#MiNombre}
DisableProgramGroupPage=yes
; El médico no elige carpeta: una decisión menos y una ruta que siempre sabemos.
DisableDirPage=yes
DisableReadyPage=no
AllowNoIcons=yes

; --- salida -----------------------------------------------------------------
OutputDir=salida
OutputBaseFilename=RecipesMedicos-Setup-{#MiVersion}
SetupIconFile=icono.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible

; --- «Agregar o quitar programas» -------------------------------------------
; Con estas tres, la entrada aparece con nombre, ícono y editor, y el
; desinstalador queda a un clic (§11.2: "permite desinstalar").
UninstallDisplayName={#MiNombre}
UninstallDisplayIcon={app}\{#MiEjecutable}
CreateUninstallRegKey=yes

; Si la app quedó abierta, se cierra antes de reemplazar los archivos en vez de
; fallar a mitad de camino.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Todo el --onedir de PyInstaller: el .exe y su carpeta _internal.
Source: "{#MiCarpetaDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menú Inicio y escritorio (§11.2).
Name: "{autoprograms}\{#MiNombre}"; Filename: "{app}\{#MiEjecutable}"
Name: "{autodesktop}\{#MiNombre}"; Filename: "{app}\{#MiEjecutable}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MiEjecutable}"; Description: "{cm:LaunchProgram,{#MiNombre}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; A PROPÓSITO VACÍO (§11.3). Acá solo podrían ir rastros del programa, y no
; queda ninguno: los archivos instalados los borra Inno Setup solo. La carpeta
; de datos del médico (Documents\Recipes: récipes, PDF, Excel y respaldos) no
; se nombra en ningún lado de este instalador, ni para crearla ni para
; borrarla. Desinstalar deja todos los récipes intactos.
