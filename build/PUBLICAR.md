# Publicar una versión

Manual del que mantiene el proyecto. El manual del médico es [`../README.md`](../README.md).

Repositorio público: **`Kalabrant/recipes-espacio-corporal`**
El médico instala desde el `Setup.exe` de la última Release y no ve nada de esto.

---

## 1. Requisitos de la máquina de compilación

| Qué | Versión | Nota |
|---|---|---|
| Python | 3.11 o más nuevo (acá se usa 3.14, se invoca `py -3`) | El instalador resultante **no** necesita Python en la máquina del médico |
| Dependencias Python | ver abajo | |
| Inno Setup | 6.x | `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` |
| GitHub CLI (`gh`) | cualquiera reciente | solo para publicar la Release |

```powershell
py -3 -m pip install flask pywebview fpdf2 openpyxl Pillow PyMuPDF pyinstaller
```

Qué es cada una:

- **De la app** (van adentro del `.exe`): `flask`, `pywebview`, `fpdf2`, `openpyxl` y —desde la 2.0— `Pillow`, que es lo que arma las miniaturas de la bandeja de mediciones, lee las medidas y la orientación EXIF de los anexos y prepara la imagen de la página de anexo del informe.
- **De herramientas** (no se empaquetan): `numpy` para `build/preparar_recursos.py`, `PyMuPDF` para las comparaciones del PDF contra el modelo, `pyinstaller` para el empaquetado.

**No agregues dependencias.** Cada paquete extra es riesgo de empaquetado, y §2 prohíbe red, CDN y npm: si algo pide bajar una fuente, un ícono o un script de internet, no entra.

---

## 2. Correr en desarrollo

Desde la raíz del proyecto:

```powershell
# Normal: ventana pywebview, igual que el acceso directo del médico
py -3 -m app.main

# Sin ventana: imprime la URL local y se queda escuchando (Ctrl+C para cortar)
py -3 -m app.main --solo-servidor

# Puerto fijo, para volver siempre a la misma URL en el navegador
py -3 -m app.main --solo-servidor --puerto 5000

# No abrir el PDF en el visor al guardar (pruebas repetidas, sin ventanas encima)
py -3 -m app.main --solo-servidor --puerto 5000 --no-abrir-pdf
```

Sin `--puerto`, el sistema operativo elige uno libre. Flask escucha **siempre** en `127.0.0.1`, nunca en `0.0.0.0`.

### Carpeta de datos

Por defecto `%USERPROFILE%\Documents\Recipes`. Para no ensuciar tus datos reales mientras probás, apuntala a otro lado con `RECIPES_DIR`:

```powershell
$env:RECIPES_DIR = "C:\temp\Recipes-prueba"
py -3 -m app.main --solo-servidor --no-abrir-pdf
```

La carpeta se crea sola en el primer arranque, con `datos\`, `pdf\`, `registro\`, `respaldos\` y `recursos\`.

### Recursos gráficos

`recursos\logo.png`, `recursos\logo_completo.png` y `build\icono.ico` ya están en el repo. Se regeneran desde `referencias/Logo.jpg` con:

```powershell
py -3 build/preparar_recursos.py
```

Es un paso de una sola vez. No hace falta antes de cada release, y no es código de la app.

---

## 3. Tests

```powershell
py -3 -m unittest discover -s tests -p "test_*.py"
```

**768 tests, todos en verde.** No se publica nada con un test roto. Si agregaste código, agregá tests: `codigos.py` es la pieza que no puede fallar (reinicio de año, concurrencia, relleno de ceros, desborde a cinco dígitos, no reutilización tras anulación).

Un módulo suelto, mientras iterás:

```powershell
py -3 -m unittest tests.test_codigos -v
```

---

## 4. Construir el `.exe`

PyInstaller en modo `--onedir` (nunca `--onefile`: arranca más rápido y Windows Defender lo marca como falso positivo mucho menos seguido). Todo está fijado en el spec, así que se invoca sin flags sueltos:

```powershell
py -3 -m PyInstaller --noconfirm --clean build/recipe.spec --distpath build/dist --workpath build/tmp
```

**Las dos banderas no son opcionales.** Sin ellas PyInstaller escribe en `dist\` y `build\` de la raíz, y el `.iss` busca en `build\dist\RecipesMedicos` (su `MiCarpetaDist` es relativo a la carpeta del propio `.iss`): la compilación del instalador falla, o peor, empaqueta una copia vieja que quedó ahí de antes.

Queda una carpeta con el ejecutable y todo lo suyo al lado (`web/`, `recursos/`, las fuentes `.ttf`).

Probá el resultado **antes** de empaquetarlo: abrí el `.exe` a mano, emití un récipe de prueba contra una `RECIPES_DIR` descartable y fijate que el PDF salga con el logo y las fuentes correctas. Un `--add-data` que falta no rompe el build: rompe el PDF del médico.

---

## 5. Compilar el instalador

Inno Setup, con el `.iss` del repo:

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "build\instalador.iss"
```

Para pasarle la versión sin editar el archivo, si el `.iss` define `MiVersion`:

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" /DMiVersion=2.0.0 "build\instalador.iss"
```

Lo que el instalador tiene que cumplir (§11) y conviene releer si lo tocás:

- Instala en `%LOCALAPPDATA%\Programs\RecipesMedicos`.
- **No pide permisos de administrador** (`PrivilegesRequired=lowest`).
- Crea acceso directo en el escritorio y en el menú Inicio, y se puede desinstalar.
- **Nunca toca `Documents\Recipes`**: ni al instalar encima, ni al desinstalar. Sin entradas de `[UninstallDelete]` que apunten a la carpeta de datos.
- El archivo de salida **termina en `Setup.exe`** (`OutputBaseFilename`), porque el README le dice al médico exactamente eso: "descargá el archivo que termina en `Setup.exe`". Si le cambiás el nombre, cambiá el README.

La carpeta y el nombre exactos de salida los fija el `.iss` en `OutputDir` / `OutputBaseFilename`.

---

## 6. Antes de cada release: la lista de §12

**No es opcional y no se hace de memoria.** Es la lista de criterios de aceptación de las instrucciones, verificada una por una sobre el instalador que vas a publicar —no sobre el código corriendo desde el fuente—:

- [ ] Con Wi-Fi apagado, la app abre, emite un récipe y genera el PDF.
- [ ] *(2.0 — código por paciente.)* Dar de alta tres pacientes seguidos da `EC-0001`, `EC-0002`, `EC-0003`.
- [ ] *(2.0.)* Todos los récipes de un paciente llevan su código; el segundo del mismo día sale `_v2` sin sobrescribir.
- [ ] En los tests, el secuencial 9999 pasa a `EC-2026-10000` sin romper el formato.
- [ ] Anular un récipe no libera su número.
- [ ] El PDF generado, impreso a color, coincide con el modelo de `referencias/`.
- [ ] El segundo récipe del mismo paciente autocompleta nombre, cédula y edad.
- [ ] Un medicamento usado antes propone su dosis más frecuente, editable.
- [ ] Con el Excel abierto, el récipe se guarda igual y el mensaje es comprensible.
- [ ] Corregir el nombre de un medicamento en el catálogo no altera récipes ya emitidos.
- [ ] Reimprimir desde Historial entrega el PDF original, byte por byte.
- [ ] **Instalar sobre una instalación previa conserva todos los datos.**
- [ ] **La app corre en una máquina limpia sin Python instalado.**

Las dos últimas son las que solo se pueden probar con el instalador en la mano, y son justo las que arruinan al médico si fallan. La de "instalar encima" se prueba así: instalá la versión vieja, emití dos récipes, instalá la nueva encima, abrí y verificá que los dos récipes sigan en el Historial y que el PDF se abra.

Actualizá también `VERSION_APP` en `app/rutas.py` (hoy `2.1.0`) y que coincida con la versión del `.iss` y con el tag de la Release. El médico ve ese número al pie de Configuración: si dice una cosa y el instalador otra, no hay forma de saber qué tiene instalado.

---

## 7. Publicar en GitHub Releases

Una sola vez, si la copia local todavía no está conectada al repo:

```powershell
git init
git branch -M main
git add -A
git commit -m "Récipes Espacio Corporal 1.0.0"
git remote add origin https://github.com/Kalabrant/recipes-espacio-corporal.git
git push -u origin main
gh auth login   # si nunca te autenticaste con gh en esta máquina
```

Para cada versión nueva:

```powershell
# 1. Tests en verde
py -3 -m unittest discover -s tests -p "test_*.py"

# 2. Build limpio
py -3 -m PyInstaller --noconfirm --clean build/recipe.spec
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "build\instalador.iss"

# 3. Lista de §12 verificada sobre ESE Setup.exe

# 4. Commit y tag
git add -A
git commit -m "Version 2.0.0"
git tag -a v2.0.0 -m "Version 2.0.0"
git push origin main --follow-tags

# 5. El adjunto se sube SIN la versión en el nombre (ver el aviso de abajo)
Copy-Item "build\salida\RecipesMedicos-Setup-2.0.0.exe" "build\salida\RecipesMedicos-Setup.exe"

# 6. Release con el instalador adjunto
gh release create v2.0.0 "build\salida\RecipesMedicos-Setup.exe" `
  --repo Kalabrant/recipes-espacio-corporal `
  --title "Récipes — Espacio Corporal 2.0.0" `
  --notes "Qué cambió en esta versión, en dos o tres renglones, en criollo."
```

> ### ⚠ El adjunto se llama `RecipesMedicos-Setup.exe`, a secas
>
> ISCC produce `RecipesMedicos-Setup-2.1.0.exe`, con la versión adentro del nombre. **Ese no es el nombre con el que se sube.** El `README.md` le da al médico un enlace fijo que no cambia entre versiones:
>
> ```
> https://github.com/Kalabrant/recipes-espacio-corporal/releases/latest/download/RecipesMedicos-Setup.exe
> ```
>
> GitHub arma esa URL con **el nombre exacto del archivo adjunto**. Si subís el `.exe` con la versión en el nombre, ese enlace devuelve **404** y el médico se queda mirando una página de error, aunque la Release esté perfecta y el instalador ande. Por eso se copia con el nombre canónico antes de subirlo, como se hizo en la 2.0.0, la 2.0.1 y la 2.1.0.
>
> Comprobalo **después** de publicar, que es lo único que vale (dale unos segundos: el CDN de GitHub tarda un momento en servir un adjunto recién subido):
>
> ```powershell
> curl.exe -sIL -o NUL -w "%{http_code}`n" "https://github.com/Kalabrant/recipes-espacio-corporal/releases/latest/download/RecipesMedicos-Setup.exe"
> ```
>
> Tiene que decir `200`.

Después de publicar:

```powershell
gh release view v2.0.0 --repo Kalabrant/recipes-espacio-corporal --web
```

y **copiá el enlace de esa página**: es el que reemplaza el marcador `{{ENLACE_DESCARGA}}` del `README.md`. Conviene usar la URL que siempre apunta a la última:

```
https://github.com/Kalabrant/recipes-espacio-corporal/releases/latest
```

Así el README no hay que tocarlo en cada versión.

### Notas de la release

Escribilas pensando en el médico, que es quien las va a leer si entra a la página: qué cambió y qué tiene que hacer él (casi siempre: nada más que instalar encima). Nada de nombres de funciones ni de números de commit.

### SmartScreen

El instalador no está firmado, así que Windows va a mostrar la pantalla azul de *"Windows protegió tu PC"* la primera vez. Está explicado en el README paso a paso. La advertencia se va sola a medida que el archivo acumula descargas, y vuelve a aparecer con cada versión nueva. La única forma de eliminarla es un certificado de firma de código pagado; mientras no lo haya, **avisale al médico por mensaje que va a ver esa pantalla y que es normal**, antes de que la vea solo.

---

## 8. Recordatorios que se olvidan entre release y release

- **Cero red.** Ni un `fetch` a internet, ni una fuente de Google, ni un CDN, ni verificación de actualizaciones, ni telemetría. La app tiene que funcionar con el cable desconectado, siempre. Si dudás, probala con el Wi-Fi apagado.
- **No hay autoactualizador.** Las versiones nuevas se instalan a mano, desde la Release.
- **Ningún récipe se borra.** Se anula. Los códigos no se reciclan.
- **El Excel es salida, nunca fuente.** Se regenera entero desde SQLite; la base es la única verdad.
- **`recipe_items` guarda texto copiado**, no referencias al catálogo. Un récipe emitido es un documento histórico y no cambia nunca.
- **Sin validación clínica automática** (ni interacciones, ni dosis máximas, ni alergias) y el PDF no debe insinuar que la haya.
