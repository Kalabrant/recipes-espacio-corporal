# App de Récipes Médicos — Instrucciones de construcción

> **Cómo usar este archivo:** creá una carpeta vacía para el proyecto, poné adentro una subcarpeta `referencias/` con el PDF modelo del récipe y el logo, guardá este archivo como `INSTRUCCIONES.md` en la raíz, abrí Claude Code ahí y escribí: *"Leé INSTRUCCIONES.md y empezá por la Fase 0."*

---

## 1. Qué se construye y para quién

Una aplicación de escritorio para Windows que un médico usa para **emitir récipes**. La usa una sola persona, que no es técnica. Todo el valor está en que emitir un récipe sea: escribir el nombre del paciente, elegir dos o tres medicamentos que el sistema ya conoce, y darle a imprimir.

**El resultado de cada uso es un PDF a color, listo para imprimir**, idéntico al modelo que está en `referencias/`.

Criterio rector: si una función agrega un clic al flujo principal, no va. Si agrega una pantalla, se discute.

---

## 2. Restricciones no negociables

1. **Cero red.** La app no hace ninguna llamada HTTP a internet. Ni APIs, ni CDN, ni fuentes de Google, ni telemetría, ni verificación de actualizaciones. Todo —fuentes, íconos, estilos— se empaqueta dentro del instalador. Debe funcionar con el cable desconectado, siempre.
2. **Sin cuentas ni nube.** No hay login remoto, no hay sincronización, no hay backend externo.
3. **Los datos son del médico y viven en su disco.** Son datos de salud: no salen de la máquina.
4. **Ningún récipe se borra.** Se anula, con motivo y fecha. El código queda quemado para siempre.
5. **La app sugiere, el médico decide.** El autocompletado nunca rellena un medicamento o una dosis sin que el médico lo seleccione explícitamente. No hay ninguna validación clínica automática (ni interacciones, ni dosis máximas, ni alergias) y el PDF no debe insinuar que la haya.

---

## 3. Stack técnico obligatorio

| Capa | Herramienta | Por qué |
|---|---|---|
| Lenguaje | Python 3.11 | Mantenible por el dueño del proyecto |
| Ventana | `pywebview` | Se ve como programa, no como pestaña del navegador |
| Servidor local | Flask, en `127.0.0.1`, puerto libre aleatorio | Nunca escucha en `0.0.0.0` |
| Interfaz | HTML + CSS + JavaScript sin framework ni build | Cero npm, cero CDN |
| Base de datos | SQLite (`sqlite3` de la stdlib) | Un archivo, sin servicio |
| PDF | `fpdf2` | Puro Python, se empaqueta limpio (no usar WeasyPrint: necesita GTK en Windows) |
| Excel | `openpyxl` | — |
| Empaquetado | PyInstaller `--onedir` + Inno Setup | Ver §11 |

**No agregues dependencias fuera de esta lista sin preguntar.** Cada paquete extra es un riesgo de empaquetado.

---

## 4. Estructura de archivos

### Del proyecto

```
recipe-app/
├─ INSTRUCCIONES.md          ← este archivo
├─ referencias/              ← SOLO LECTURA: modelo del récipe y logo
├─ app/
│  ├─ main.py                ← arranca Flask + pywebview
│  ├─ basedatos.py           ← esquema, migraciones, consultas
│  ├─ codigos.py             ← generación del código único
│  ├─ pdf_recipe.py          ← composición del PDF
│  ├─ excel.py               ← regeneración del registro
│  ├─ respaldo.py            ← copias de seguridad
│  ├─ rutas.py               ← endpoints Flask
│  └─ web/  index.html · estilos.css · app.js
├─ recursos/                 ← logo.png, firma.png, fuentes/*.ttf
├─ build/  recipe.spec · instalador.iss
└─ README.md                 ← instalación y respaldo, en lenguaje llano
```

### En la máquina del médico (la crea la app sola en el primer arranque)

```
%USERPROFILE%\Documents\Recipes\
├─ datos\recipes.db
├─ pdf\2026\EC-2026-0001_PEREZ-Juan_2026-08-14.pdf
├─ registro\registro_recipes.xlsx
├─ respaldos\respaldo-2026-08-14.zip
└─ recursos\logo.png · firma.png
```

Sin tildes ni eñes en nombres de carpeta. En los nombres de archivo, sanitizá el nombre del paciente (sin acentos, sin caracteres prohibidos por Windows, máximo 60 caracteres). Si el archivo ya existe, agregá `_v2`, nunca sobrescribas.

---

## 5. Modelo de datos

SQLite, todas las tablas con `creado_en` y `actualizado_en` en ISO 8601.

- **`config`** — clave/valor: datos del médico (nombre, especialidad, MPPS, colegio de médicos, RIF, dirección, teléfonos), prefijo del código, ruta de la carpeta de datos, hash del PIN, rutas de logo y firma.
- **`pacientes`** — `nombre`, `cedula` (única, admite vacío), `fecha_nacimiento` **o** `edad`, `sexo`, `telefono`, `notas`, `veces_atendido`, `ultima_vez`.
- **`medicamentos`** — `nombre`, `presentacion`, `veces_usado`, `ultima_vez`. Único por (nombre, presentación).
- **`dosis`** — `medicamento_id`, `texto`, `veces_usado`, `ultima_vez`. **La dosis cuelga del medicamento**, no es una lista global.
- **`indicaciones`** y **`diagnosticos`** — `texto`, `veces_usado`, `ultima_vez`. Listas globales.
- **`recipes`** — `codigo` (único), `anio`, `secuencial`, `paciente_id`, `fecha_emision`, `diagnostico`, `notas`, `ruta_pdf`, `anulado` (0/1), `motivo_anulacion`, `fecha_anulacion`.
- **`recipe_items`** — `recipe_id`, `orden`, y **copia literal** de nombre, presentación, cantidad, dosis e indicaciones.

> **Punto crítico:** `recipe_items` guarda el texto copiado, no una referencia. Un récipe emitido es un documento histórico: si mañana se corrige la ortografía de un medicamento en el catálogo, los récipes de ayer **no cambian**.

- **`contador_anual`** — `anio` (PK), `ultimo_secuencial`.

**El Excel no es la base de datos.** Es un reporte que se regenera desde SQLite. Si el médico lo tiene abierto en Excel, la app no puede escribirlo — ver §9.

---

## 6. El código único

Formato: **`EC-2026-0001`** — prefijo `EC` (de *Espacio Corporal*), año de emisión, y secuencial de cuatro dígitos con ceros a la izquierda.

Reglas:

1. El secuencial **reinicia en `0001` cada 1 de enero**. Lo determina el año de emisión, no un contador corrido.
2. Se asigna **al guardar**, nunca al abrir el formulario. Un formulario abandonado no quema un número.
3. La asignación ocurre dentro de una transacción `BEGIN IMMEDIATE` que lee y actualiza `contador_anual` en la misma operación que inserta el récipe. Sin condiciones de carrera, incluso si el médico abre dos ventanas.
4. Los números **no se reciclan**. Un récipe anulado conserva su código y ese código no se vuelve a emitir.
5. **Desborde:** si un año pasara de 9999, seguí con cinco dígitos (`EC-2026-10000`) en vez de romper el formato o detenerte. Es improbable, pero se codifica y se prueba igual.
6. El prefijo vive en `config` y es editable desde Configuración, con `EC` por defecto. Al cambiarlo, los récipes ya emitidos conservan el prefijo con el que salieron.

Escribí `codigos.py` con **tests unitarios reales**: reinicio de año, concurrencia de dos escrituras simultáneas, relleno correcto de ceros (`0001`, `0042`, `1234`), desborde a cinco dígitos, y no reutilización tras anulación. Es la pieza que no puede fallar.

---

## 7. Interfaz

Tres pantallas. Ni una más.

**A · Nuevo récipe** (la que se abre al arrancar)

- Campo de paciente con búsqueda mientras se escribe. Al elegir uno existente, se completan cédula y edad. Si no existe, se crea escribiendo, sin pantalla aparte.
- Campo de diagnóstico con sugerencias.
- Lista de medicamentos. Cada renglón: medicamento (con sugerencias), presentación, cantidad, dosis (sugerencias filtradas **por ese medicamento**), indicaciones (sugerencias). Botón para agregar renglón; mínimo uno, sin tope fijo — si no caben en la hoja, avisá antes de generar.
- Vista previa del PDF a la derecha o en pestaña, y un solo botón grande: **Guardar e imprimir**.
- Ese botón hace todo: asigna código, guarda, aprende los términos nuevos, genera el PDF, actualiza el Excel y abre el PDF en el visor del sistema listo para imprimir.

**B · Historial**

Buscador por código, paciente, medicamento o rango de fechas. Cada resultado: ver PDF, reimprimir (el mismo PDF, mismo código, sin regenerar nada) y anular con motivo. Los anulados se ven tachados.

**C · Configuración**

Datos del médico, carga de logo y firma, carpeta de datos, prefijo del código, PIN, y un botón **Respaldar ahora**.

**Diseño:** tipografía grande (mínimo 16 px), campos altos, contraste alto, todo el flujo principal recorrible con Tab y Enter. Nada de íconos sin etiqueta. Nada de menús desplegables anidados. Los mensajes de error dicen qué hacer, no qué falló ("El registro está abierto en Excel. Cerralo y volvé a intentar").

---

## 8. Autocompletado

Al guardar cada récipe, la app registra los términos usados e incrementa `veces_usado`. La búsqueda es por subcadena, sin distinguir mayúsculas ni acentos, ordenada por `veces_usado DESC`, luego `ultima_vez DESC`, máximo 8 resultados.

Al elegir un medicamento, proponé su dosis más usada **como sugerencia visible y editable, nunca aplicada en silencio**. Sin catálogo precargado: la app arranca vacía y aprende del médico.

---

## 9. PDF y registro Excel

### PDF

**Fase 0 antes de escribir código:** abrí el PDF de `referencias/`, medí márgenes, posiciones, tamaños y colores, y escribí lo que encontraste en `build/analisis-modelo.md`. El PDF generado debe ser indistinguible del modelo, con el logo en la resolución mejorada que está en la carpeta.

Elementos: logo y encabezado con los datos del médico; el **código único visible y legible**, en el lugar que indique el modelo; fecha; datos del paciente; diagnóstico; lista de medicamentos numerada con dosis e indicaciones; espacio de firma con la firma escaneada (PNG con fondo transparente) y los datos de colegiatura.

Fuentes embebidas desde `recursos/fuentes/`. Colores en el espacio del modelo. Nada de imágenes que dependan de internet.

### Excel

Se regenera completo desde SQLite después de cada récipe. Dos hojas:

- **Récipes** — código, fecha, paciente, cédula, edad, diagnóstico, cantidad de medicamentos, estado, ruta del PDF.
- **Medicamentos** — una fila por renglón recetado: código del récipe, fecha, paciente, medicamento, presentación, cantidad, dosis, indicaciones.

Encabezados fijos, columnas anchas, filtro automático. Si el archivo está bloqueado porque el médico lo tiene abierto, **el récipe igual se guarda y el PDF igual se genera**: la app avisa y reintenta al próximo guardado. Que un Excel abierto nunca impida emitir.

---

## 10. Respaldos, PIN y anulación

- **Respaldo:** al primer arranque de cada semana, ZIP de `datos\` + `registro\` en `respaldos\`, conservando los últimos 8. Más el botón manual en Configuración.
- **PIN:** 4 a 6 dígitos al abrir, guardado con hash. Configurable y desactivable. No es seguridad fuerte, es una barrera contra el que pasa frente a la computadora.
- **Anulación:** exige motivo escrito, marca el récipe, deja el PDF en disco y refleja el estado en el Excel.

---

## 11. Empaquetado

1. PyInstaller en modo **`--onedir`** (no `--onefile`: arranca más rápido y Windows Defender lo marca como falso positivo con mucha menos frecuencia), con `--windowed` y `--add-data` para `web/`, `recursos/` y las fuentes.
2. Instalador con **Inno Setup**: instala en `%LOCALAPPDATA%\Programs\RecipesMedicos`, crea acceso directo en el escritorio y en el menú Inicio, y permite desinstalar. No requiere permisos de administrador.
3. El instalador **nunca** toca la carpeta de datos: instalar encima o desinstalar deja los récipes intactos.
4. En `README.md`, escribí para el médico —no para un programador— cómo instalar, dónde quedan sus archivos, cómo respaldar y qué hacer si Windows muestra la advertencia de SmartScreen la primera vez.

---

## 12. Criterios de aceptación

Antes de dar por terminado, verificá una por una:

- [ ] Con Wi-Fi apagado, la app abre, emite un récipe y genera el PDF.
- [ ] Emitir tres récipes seguidos da `EC-2026-0001`, `-0002`, `-0003`.
- [ ] Cambiando la fecha del sistema a enero siguiente, el próximo récipe es `EC-2027-0001`.
- [ ] En los tests, el secuencial 9999 pasa a `EC-2026-10000` sin romper el formato.
- [ ] Anular un récipe no libera su número.
- [ ] El PDF generado, impreso a color, coincide con el modelo de `referencias/`.
- [ ] El segundo récipe del mismo paciente autocompleta nombre, cédula y edad.
- [ ] Un medicamento usado antes propone su dosis más frecuente, editable.
- [ ] Con el Excel abierto, el récipe se guarda igual y el mensaje es comprensible.
- [ ] Corregir el nombre de un medicamento en el catálogo no altera récipes ya emitidos.
- [ ] Reimprimir desde Historial entrega el PDF original, byte por byte.
- [ ] Instalar sobre una instalación previa conserva todos los datos.
- [ ] La app corre en una máquina limpia sin Python instalado.

---

## 13. Lo que NO hay que hacer

Ninguna llamada de red · ningún CDN ni fuente remota · ningún npm ni paso de build · ningún borrado definitivo de récipes · ninguna reutilización de códigos · ninguna validación clínica automática · ningún autoactualizador · ninguna dependencia fuera de §3 · ninguna pantalla adicional en el flujo principal · ninguna base de datos que no sea el SQLite (el Excel es salida, no fuente).

---

## 14. Orden de trabajo

Trabajá por fases y **frená al final de cada una para mostrar el resultado**. No avances a la siguiente sin luz verde.

| Fase | Entrega |
|---|---|
| **0** | Análisis del PDF modelo y del logo → `build/analisis-modelo.md`, más las preguntas de §15 |
| **1** | Esquema SQLite + `codigos.py` con sus tests pasando |
| **2** | `pdf_recipe.py` generando un PDF de prueba idéntico al modelo |
| **3** | Interfaz de Nuevo récipe con autocompletado, extremo a extremo |
| **4** | Historial, anulación, Excel, respaldos, PIN |
| **5** | PyInstaller + Inno Setup + `README.md` + lista de §12 verificada |

---

## 15. Preguntas a resolver en la Fase 0

Antes de escribir código, preguntá y esperá respuesta:

1. Datos exactos del médico para el encabezado: nombre completo, especialidad, número MPPS, colegio de médicos, RIF, dirección y teléfonos.
2. Tamaño de papel del modelo (¿carta, media carta, A5?) y si se imprime uno por hoja o dos.
3. ¿La firma escaneada va impresa en el PDF, o el médico firma a mano sobre el papel?
4. ¿La cédula del paciente es obligatoria o puede quedar vacía?
5. ¿El modelo lleva una sección de indicaciones generales separada de la dosis de cada medicamento?
6. ¿Hace falta un campo de "vigencia" o "válido hasta" en el récipe?
