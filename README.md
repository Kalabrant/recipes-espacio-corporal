# Récipes — Espacio Corporal

Programa de consultorio de Espacio Corporal: historia clínica, récipes, informes, **órdenes de exámenes** y **mapa de infiltraciones faciales**. Funciona sin internet y tus datos quedan solo en tu computadora.

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

- **El tutorial se abre solo** la primera vez que arranca el programa y te muestra, paso a paso, el camino: buscar al paciente, su historia, y de ahí el récipe y el informe. Se cierra cuando querés y no vuelve a aparecer.
- Antes de emitir el primer récipe, andá a **Configuración** y revisá tus datos: nombre, especialidad, MPPS, COMEZU, RIF, colegio de médicos, ciudad, dirección y teléfonos. El nombre, el COMEZU, el MPPS y la ciudad ya vienen cargados con los tuyos; si corregís alguno, queda como vos lo dejes. **En el récipe no salen** (el talonario se completa con tu sello), pero **en el informe médico sí**: van en la cabecera, y la ciudad en el renglón de la fecha al pie.
- **El PIN es opcional.** El programa arranca sin PIN: abre directo. Si querés que pida una clave de 4 a 6 números al abrir, la activás en **Configuración → PIN al abrir**. Como dice la propia pantalla:

  > El PIN es una barrera contra quien pase frente a la computadora, no una caja fuerte: los archivos siguen estando en tu carpeta de datos.

- **El programa abre en Historia clínica**, que es por donde empieza todo. Escribís el nombre o la cédula del paciente y lo elegís de la lista. ¿Viene por primera vez? Escribí su nombre y al pie de la lista aparece **"➕ Crear paciente nuevo"**: lo das de alta ahí mismo (lo único obligatorio es el nombre), se le asigna su código `EC-0001` y su carpeta, y su historia queda abierta.
- Con la historia abierta, los botones **Nuevo récipe para este paciente** y **Nuevo informe** arrancan con esa persona ya puesta: no la escribís de nuevo. Arriba del récipe una banda te dice de quién es y te deja cambiarlo.
- **Los escaneos que te llegan por WhatsApp** (el informe de la báscula, un laboratorio): guardalos siempre en la carpeta **«MEDICIONES — soltar aquí»** que el programa crea en tu Escritorio. Así quedan todos en un solo lugar y no regados por la computadora. Al abrir la historia del paciente, el programa te los muestra como fotitos: tocás la que corresponde y queda anexada (el archivo original no se toca). Si alguna se descargó sola en `Descargas`, también la va a encontrar.
- Emitir un récipe es siempre lo mismo: el paciente, los medicamentos y **Guardar e imprimir**. Ese botón hace todo: le pone el código, lo guarda, genera el PDF, actualiza el registro y lo abre listo para imprimir. Si tenés apuro y no querés abrir ninguna historia, en **Nuevo récipe** podés escribir el nombre del paciente a mano, como siempre.

---

## Órdenes de exámenes

La pestaña **Exámenes** se usa igual que el récipe y sale en la misma hoja: la mitad izquierda, **«Solicito:»**, es la que entregás en el laboratorio, y la derecha, **«Ind.»**, la que se lleva el paciente con la preparación de cada estudio.

- El programa trae **75 análisis cargados**, agrupados como los pensás: Hematología, Química sanguínea, Hormonas, Orina y heces, Inmunología y serología, Marcadores y Estudios. Los tildás de la lista y se agregan de una, con su tipo de muestra y su preparación ya puestas (*«Ayuno de 8 a 12 horas»*, *«Primera orina de la mañana, chorro medio»*…).
- **La lista no te limita.** Si pedís algo que no está, lo escribís y sale igual; el programa lo aprende y la próxima vez te lo sugiere. Y si una preparación tuya es distinta, la corregís en el renglón: manda lo que vos escribas.
- Con la historia del paciente abierta, la orden arranca con esa persona ya puesta, y abajo ves las órdenes que ya le emitiste, con su botón para reimprimirlas.

## Mapa de infiltraciones

La pestaña **Infiltraciones** reemplaza la lámina de papel: marcás **en qué puntos exactos** infiltraste, con qué producto y qué dosis, y sale un PDF para la historia clínica.

- Elegís la lámina (hombre o mujer), aplicás una de tus **plantillas** —«Full face» son los 35 puntos— y ajustás solo lo que cambia en ese paciente. **Todas las dosis nacen vacías**: el programa nunca sugiere ni calcula una dosis, solo anota la que vos ponés.
- Hacés clic para agregar un punto, lo arrastrás para moverlo, `Supr` lo borra, la tecla `M` hace el simétrico del otro lado, y `Ctrl+Z` deshace (aplicar una plantilla entera se deshace de un solo golpe).
- A la derecha, la tabla se llena sola, agrupada por región y con el subtotal de cada una y el total por producto siempre a la vista.
- **Guardar y generar PDF** guarda el mapa en la historia del paciente y abre el PDF: la lámina con los puntos numerados, la leyenda de productos con su lote, la tabla por regiones y los totales.
- Los mapas anteriores de ese paciente se listan abajo y **se vuelven a abrir para corregirlos**. Corregir uno no pisa el PDF anterior: se guarda uno nuevo.

---

## Dónde quedan tus datos

Todo vive en una sola carpeta de tu computadora:

```
Documentos\Recipes\
```

Adentro hay estas carpetas:

| Carpeta | Qué hay adentro |
|---|---|
| `datos\` | El archivo con **toda la información**: pacientes, medicamentos, récipes emitidos. Es el corazón del programa. |
| `pacientes\` | Una carpeta por paciente (`EC-0001_APELLIDO-Nombre\`) con `recipes\`, `informes\`, `examenes\`, `infiltraciones\` y `anexos\` adentro. Ahí cae todo lo nuevo de esa persona. El nombre de la carpeta se escribe una sola vez, cuando el paciente recibe su código: si después corregís cómo se llama, la carpeta no cambia de nombre (la que manda es el código) y todo sigue junto. |
| `pdf\` | Los récipes emitidos con las versiones anteriores del programa, ordenados por año. Se quedan donde están y se siguen abriendo e imprimiendo igual desde **Récipes emitidos**. Los récipes nuevos ya no van acá, van a `pacientes\`. |
| `registro\` | La planilla de Excel con la lista de todos los récipes y todos los medicamentos recetados. Sirve para mirar, buscar y sacar cuentas. |
| `respaldos\` | Las copias de seguridad automáticas, en archivos `.zip`. Adentro va `datos\`, `registro\` y `pacientes\` entera. |
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
El récipe está hecho y guardado; lo que falló fue el programa que abre los PDF. El mensaje te muestra la ruta exacta del archivo: entrá a esa carpeta (o usá **Configuración → Abrir carpeta**, y de ahí a `pacientes\` y la carpeta del paciente) y abrilo con doble clic. Si te pasa siempre, es que Windows no tiene un programa asignado para abrir PDF.

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
Andá a **Récipes emitidos** y buscá por código, por nombre del paciente, por medicamento o por rango de fechas. Desde ahí lo podés ver, **reimprimir** (sale el mismo PDF original, sin cambios) o **anular**. También los tenés todos juntos en la historia del paciente.

**Emití un récipe con un error.**
No se borra: se **anula**, desde **Récipes emitidos**, escribiendo el motivo. Queda tachado en la lista y anotado como anulado en el registro. Después emitís el récipe corregido: sale con el mismo código, porque el código es del paciente y lo llevan todos sus récipes; lo que los distingue es la fecha.

**¿Dónde quedan las órdenes de exámenes y los mapas de infiltraciones?**
En la carpeta del paciente, al lado de sus récipes: `Documentos\Recipes\pacientes\EC-0001_APELLIDO-Nombre\`, en las subcarpetas `examenes\` e `infiltraciones\`. También los ves listados en la historia del paciente y salen impresos en el PDF de la historia clínica.

**El programa no abre / se cierra solo.**
Reiniciá la computadora y probá de nuevo. Si sigue igual, desinstalá el programa e instalá otra vez el `Setup.exe`: **no vas a perder ningún récipe**, porque tus datos están en `Documentos\Recipes` y el instalador no los toca.

---

## Para desarrolladores

Cómo levantar el proyecto, correr los tests, construir el `.exe`, compilar el instalador y publicar una versión nueva: **[`build/PUBLICAR.md`](build/PUBLICAR.md)**.

Stack: Python 3.11+ con Flask sobre `127.0.0.1` dentro de una ventana `pywebview`, SQLite (`sqlite3` de la stdlib), PDF con `fpdf2`, Excel con `openpyxl`, interfaz en HTML/CSS/JS sin framework ni paso de build; se empaqueta con PyInstaller `--onedir` + Inno Setup. Sin red, sin CDN, sin npm.
