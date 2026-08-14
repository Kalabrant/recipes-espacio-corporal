# Récipes — Espacio Corporal

Programa para emitir récipes médicos de Espacio Corporal. Funciona sin internet y tus datos quedan solo en tu computadora.

---

## Cómo instalar

1. Tocá este enlace de descarga directa: **[Descargar Récipes Espacio Corporal](https://github.com/Kalabrant/recipes-espacio-corporal/releases/latest/download/RecipesMedicos-Setup.exe)** (si preferís ver la página de descargas, está [acá](https://github.com/Kalabrant/recipes-espacio-corporal/releases/latest): buscá el archivo que termina en `Setup.exe`).
2. La descarga es un solo archivo, `RecipesMedicos-Setup.exe`. Es lo único que necesitás.
3. Cuando termine la descarga, hacé **doble clic** en ese archivo (si no lo encontrás, suele quedar en la carpeta `Descargas`).
4. **Puede aparecer una pantalla azul de Windows** que dice algo como *"Windows protegió tu PC"*. No es un virus ni un error: aparece porque el programa es nuevo y Windows todavía no lo conoce. Windows avisa así con cualquier programa que no haya visto muchas veces antes.

   Hacé clic en **"Más información"** (el texto chiquito) y después en el botón **"Ejecutar de todas formas"**, que aparece recién ahí abajo.
5. Seguí el instalador con **Siguiente** hasta el final. **No te va a pedir contraseña de administrador**: el programa se instala solo para tu usuario.
6. Al terminar vas a tener el acceso directo **Récipes — Espacio Corporal** en el escritorio y en el menú Inicio. Con eso lo abrís siempre.

> Si más adelante sale una versión nueva, se instala igual: bajás el `Setup.exe` nuevo y lo instalás encima. No hace falta desinstalar nada primero.

---

## La primera vez

- **El tutorial se abre solo** la primera vez que arranca el programa y te muestra, paso a paso, cómo emitir un récipe. Se cierra cuando querés y no vuelve a aparecer.
- Antes de emitir el primer récipe, andá a **Configuración** y completá tus datos: nombre, especialidad, MPPS, colegio de médicos, RIF, dirección y teléfonos. Eso es lo que sale impreso en el encabezado de cada récipe.
- **El PIN es opcional.** El programa arranca sin PIN: abre directo. Si querés que pida una clave de 4 a 6 números al abrir, la activás en **Configuración → PIN al abrir**. Como dice la propia pantalla:

  > El PIN es una barrera contra quien pase frente a la computadora, no una caja fuerte: los archivos siguen estando en tu carpeta de datos.

- Emitir un récipe es siempre lo mismo: escribís el paciente, elegís los medicamentos y apretás **Guardar e imprimir**. Ese botón hace todo: le pone el código, lo guarda, genera el PDF, actualiza el registro y lo abre listo para imprimir.

---

## Dónde quedan tus datos

Todo vive en una sola carpeta de tu computadora:

```
Documentos\Recipes\
```

Adentro hay cinco carpetas:

| Carpeta | Qué hay adentro |
|---|---|
| `datos\` | El archivo con **toda la información**: pacientes, medicamentos, récipes emitidos. Es el corazón del programa. |
| `pdf\` | Un PDF por cada récipe que emitiste, ordenados por año. Los podés abrir e imprimir cuando quieras, aunque el programa esté cerrado. |
| `registro\` | La planilla de Excel con la lista de todos los récipes y todos los medicamentos recetados. Sirve para mirar, buscar y sacar cuentas. |
| `respaldos\` | Las copias de seguridad automáticas, en archivos `.zip`. |
| `recursos\` | El logo que se imprime en el récipe. |

**Instalar una versión nueva encima o desinstalar el programa NUNCA toca tus récipes.** El instalador no entra en `Documentos\Recipes`. Podés desinstalar, volver a instalar, o instalar una versión más nueva, y al abrirla vas a encontrar todos tus récipes, tus pacientes y tus medicamentos tal cual los dejaste.

Para ir directo a esa carpeta: **Configuración → Datos y respaldo → Abrir carpeta**.

---

## Respaldo

- **Automático:** la primera vez que abrís el programa cada semana, hace solo una copia de seguridad y la guarda en `respaldos\` con la fecha del día (por ejemplo `respaldo-2026-08-14.zip`). Se conservan las **últimas 8**; las más viejas se van borrando solas. No tenés que hacer nada.
- **A pedido:** cuando quieras, **Configuración → Datos y respaldo → Respaldar ahora**. Hace la copia en el momento. Si respaldás dos veces el mismo día, la segunda se guarda aparte: nunca pisa una copia anterior.

**Lo que sí conviene que hagas vos:** cada tanto —una vez al mes está bien— enchufá un pendrive y **copiá la carpeta `respaldos\` entera** adentro. También sirve un disco externo o el correo, mandándote el `.zip` más nuevo a vos mismo.

Es la única precaución que el programa no puede tomar por vos: los respaldos automáticos están en la misma computadora, así que protegen contra un error tuyo o del programa, pero no contra que la computadora se rompa, se moje o te la roben. Una copia afuera de la máquina sí.

> Si querés guardar **todo** y no solo el respaldo, copiá la carpeta `Documentos\Recipes` completa. Con eso te llevás también los PDF.

---

## Si algo no funciona

**"El registro está abierto en Excel. Cerralo y volvé a intentar."**
Tenés la planilla `registro_recipes.xlsx` abierta en Excel, y mientras está abierta el programa no puede reescribirla. **Tu récipe se guardó igual y el PDF se generó igual**: lo único que quedó atrasado es la planilla. Cerrá el Excel y se pone al día sola con el próximo récipe que emitas. No pierdas tiempo con esto en medio de una consulta.

**"El récipe se guardó, pero no se pudo actualizar el registro de Excel. Se vuelve a intentar solo en el próximo récipe."**
Lo mismo que arriba, pero por otro motivo (por ejemplo, poco espacio en el disco). El récipe está a salvo. Si se repite muchas veces, fijate cuánto espacio libre te queda en el disco.

**"No se pudo abrir el PDF con el visor de Windows. Abrilo a mano desde: …"**
El récipe está hecho y guardado; lo que falló fue el programa que abre los PDF. El mensaje te muestra la ruta exacta del archivo: entrá a esa carpeta (o usá **Configuración → Abrir carpeta**, y de ahí a `pdf\`) y abrilo con doble clic. Si te pasa siempre, es que Windows no tiene un programa asignado para abrir PDF.

**"El récipe no entra en la hoja. Sacá un medicamento o acortá las indicaciones, y emití el resto en un segundo récipe."**
Cargaste más de lo que cabe en una hoja. El programa avisa **antes** de emitir, así que no se quemó ningún número: sacá un renglón, emití ese récipe, y hacé un segundo récipe con lo que falta.

**"El paciente que elegiste ya no está en la lista. Volvé a buscarlo o escribí el nombre de nuevo."**
Pasa si el programa quedó abierto mucho rato con el formulario a medio llenar. Volvé a escribir el nombre del paciente y elegilo de la lista de sugerencias.

**"No se pudo escribir el respaldo. Revisá que haya espacio en el disco y volvé a intentar."**
El respaldo no se hizo, pero **tus récipes están intactos**. Liberá espacio en el disco y apretá **Respaldar ahora** otra vez. Si el programa está arrancando, el respaldo de la semana se reintenta solo la próxima vez que lo abras.

**"No se pudo copiar la base de datos para el respaldo. Cerrá la aplicación y volvé a intentar."**
Cerrá el programa del todo (que no quede otra ventana abierta), volvé a abrirlo y apretá **Respaldar ahora**.

**"PIN incorrecto. Probá de nuevo."**
El PIN son de 4 a 6 números, sin letras ni espacios. Si te olvidaste el PIN, **no perdiste nada**: los PDF de todos tus récipes y la planilla de Excel siguen estando en `Documentos\Recipes` y los podés abrir sin el programa. Para sacar el PIN pedile ayuda a quien te instaló el programa.

**No encuentro un récipe viejo.**
Andá a **Historial** y buscá por código, por nombre del paciente, por medicamento o por rango de fechas. Desde ahí lo podés ver, **reimprimir** (sale el mismo PDF original, sin cambios) o **anular**.

**Emití un récipe con un error.**
No se borra: se **anula**, desde Historial, escribiendo el motivo. Queda tachado en la lista y anotado como anulado en el registro. El número no se reutiliza. Después emitís el récipe corregido, que sale con un número nuevo.

**El programa no abre / se cierra solo.**
Reiniciá la computadora y probá de nuevo. Si sigue igual, desinstalá el programa e instalá otra vez el `Setup.exe`: **no vas a perder ningún récipe**, porque tus datos están en `Documentos\Recipes` y el instalador no los toca.

---

## Para desarrolladores

Cómo levantar el proyecto, correr los tests, construir el `.exe`, compilar el instalador y publicar una versión nueva: **[`build/PUBLICAR.md`](build/PUBLICAR.md)**.

Stack: Python 3.11+ con Flask sobre `127.0.0.1` dentro de una ventana `pywebview`, SQLite (`sqlite3` de la stdlib), PDF con `fpdf2`, Excel con `openpyxl`, interfaz en HTML/CSS/JS sin framework ni paso de build; se empaqueta con PyInstaller `--onedir` + Inno Setup. Sin red, sin CDN, sin npm.
