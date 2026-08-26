# Contrato de la evolución 2.1 — pestañas «Exámenes» e «Infiltraciones»

Este archivo es el **contrato entre las piezas** de la 2.1. Cada módulo se
escribe contra lo que dice acá, no contra lo que otro módulo *parece* hacer.
Si algo de acá no cierra, se dice y se corrige acá primero.

Dos pestañas nuevas:

- **Exámenes** — orden de análisis de laboratorio. **Mismo formato que el
  récipe**: una carta apaisada con las dos mitades y la línea de corte. La
  mitad izquierda lleva la lista de lo que se pide (es la que se entrega en el
  laboratorio); la derecha, la preparación que el paciente tiene que leer.
- **Infiltraciones** — el mapa de infiltraciones faciales que hoy vive suelto
  en `App Botox`, anexado como pestaña e integrado con el paciente, la base y
  el PDF de marca.

Orden de las pestañas en la barra:

```
Historia clínica · Nuevo récipe · Exámenes · Infiltraciones · Récipes emitidos · Configuración
```

Versión que sale de esto: **2.1.0**.

---

## 0. Reglas que no se negocian

1. **La salida del PDF del récipe no cambia ni un punto.** `pdf_recipe.py` no
   se toca salvo para exportar constantes que ya existen. `tests/test_pdf_recipe.py`
   es la red.
2. Sin dependencias nuevas: `fpdf2`, `flask`, `pywebview`, `openpyxl`, `Pillow`.
   Nada de CDN, fuentes remotas ni `fetch` a internet.
3. Español rioplatense en la interfaz y en los comentarios, como el resto del
   proyecto. Terminología clínica correcta.
4. Flask escucha solo en `127.0.0.1`. Nada sale de la máquina.
5. Todo lo que se emite vive en la carpeta del paciente
   (`pacientes\EC-NNNN_APELLIDO-Nombre\`), nunca se pisa un PDF emitido.
6. Herramienta de **registro documental**: nunca sugiere, recomienda ni calcula
   dosis ni pide análisis por su cuenta. El catálogo son posiciones de partida.

---

## 1. Base de datos — migración nueva (la cuarta)

Se **agrega una sola cadena** al final de `MIGRACIONES` en `app/basedatos.py`
(queda de índice 3, o sea la versión 4 del esquema: la lista tiene tres
entradas, no once — cada una junta varias sentencias). No se toca ninguna
migración anterior: ya corrieron en la máquina del médico.

```sql
------------------------------------------------------------ órdenes de exámenes
CREATE TABLE IF NOT EXISTS examenes (
    id                     INTEGER PRIMARY KEY,
    codigo                 TEXT    NOT NULL,          -- el del PACIENTE (EC-0001)
    paciente_id            INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE RESTRICT,
    consulta_id            INTEGER REFERENCES consultas(id) ON DELETE SET NULL,
    fecha_emision          TEXT    NOT NULL,          -- ISO aaaa-mm-dd
    diagnostico            TEXT,
    indicaciones_generales TEXT,
    notas                  TEXT,
    ruta_pdf               TEXT,
    anulado                INTEGER NOT NULL DEFAULT 0 CHECK (anulado IN (0, 1)),
    motivo_anulacion       TEXT,
    fecha_anulacion        TEXT,
    creado_en              TEXT    NOT NULL,
    actualizado_en         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_examenes_fecha    ON examenes(fecha_emision DESC);
CREATE INDEX IF NOT EXISTS ix_examenes_paciente ON examenes(paciente_id);
CREATE INDEX IF NOT EXISTS ix_examenes_codigo   ON examenes(codigo);

CREATE TABLE IF NOT EXISTS examen_items (
    id           INTEGER PRIMARY KEY,
    examen_id    INTEGER NOT NULL REFERENCES examenes(id) ON DELETE CASCADE,
    orden        INTEGER NOT NULL,
    examen       TEXT    NOT NULL,   -- 'Hematología completa'
    muestra      TEXT,               -- 'Sangre' | 'Orina' | 'Heces' | '' …
    indicaciones TEXT                -- preparación de ESE análisis
);
CREATE INDEX IF NOT EXISTS ix_examen_items_examen ON examen_items(examen_id, orden);

------------------------------------------------------------ catálogo de análisis
-- Tabla de términos (mismo molde que `indicaciones` y `diagnosticos`, más tres
-- columnas propias). Entra en `TABLAS_TERMINOS`, así que `buscar_terminos`,
-- `obtener_o_crear_termino` y `registrar_uso_termino` la manejan sin cambios.
CREATE TABLE IF NOT EXISTS analisis (
    id             INTEGER PRIMARY KEY,
    texto          TEXT    NOT NULL,
    texto_norm     TEXT    NOT NULL UNIQUE,
    grupo          TEXT,               -- 'Hematología', 'Química sanguínea', …
    muestra        TEXT,
    preparacion    TEXT,               -- 'Ayuno de 8 a 12 horas', …
    de_fabrica     INTEGER NOT NULL DEFAULT 0 CHECK (de_fabrica IN (0, 1)),
    veces_usado    INTEGER NOT NULL DEFAULT 0,
    ultima_vez     TEXT,
    creado_en      TEXT    NOT NULL,
    actualizado_en TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analisis_orden ON analisis(veces_usado DESC, ultima_vez DESC);
CREATE INDEX IF NOT EXISTS ix_analisis_grupo ON analisis(grupo);

-- … + los INSERT OR IGNORE del catálogo de fábrica (§2)

------------------------------------------------------------ mapa de infiltraciones
CREATE TABLE IF NOT EXISTS infiltraciones (
    id             INTEGER PRIMARY KEY,
    codigo         TEXT    NOT NULL,   -- el del PACIENTE
    paciente_id    INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE RESTRICT,
    consulta_id    INTEGER REFERENCES consultas(id) ON DELETE SET NULL,
    fecha          TEXT    NOT NULL,   -- ISO aaaa-mm-dd
    vista          TEXT    NOT NULL,   -- 'mujer-frontal' | 'hombre-frontal'
    calibracion    TEXT,               -- JSON {pupilaIzq,pupilaDer,menton}
    productos      TEXT    NOT NULL DEFAULT '[]',   -- JSON
    puntos         TEXT    NOT NULL DEFAULT '[]',   -- JSON
    observaciones  TEXT,
    ruta_pdf       TEXT,
    anulado        INTEGER NOT NULL DEFAULT 0 CHECK (anulado IN (0, 1)),
    motivo_anulacion TEXT,
    fecha_anulacion  TEXT,
    creado_en      TEXT    NOT NULL,
    actualizado_en TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_infiltraciones_fecha    ON infiltraciones(fecha DESC);
CREATE INDEX IF NOT EXISTS ix_infiltraciones_paciente ON infiltraciones(paciente_id);
```

`TABLAS_TERMINOS` pasa a ser `("indicaciones", "diagnosticos", "analisis")`.

`VERSION_ESQUEMA` sale solo de `len(MIGRACIONES)`: no se toca a mano.

---

## 2. Catálogo de análisis de fábrica

Se siembra en la migración con `INSERT OR IGNORE`, `de_fabrica = 1`,
`veces_usado = 0`. **El médico manda**: puede escribir cualquier análisis que
no esté (se aprende igual que un medicamento), corregir el texto de uno o
agregar los suyos desde el propio campo. El catálogo es un punto de partida,
no una lista cerrada, y la interfaz nunca impide escribir algo que no figure.

Grupos y contenido mínimo (texto exacto, `muestra`, `preparacion`):

- **Hematología** — Hematología completa · Contaje de plaquetas · Velocidad de
  sedimentación globular (VSG) · Tiempo de protrombina (PT) e INR · Tiempo
  parcial de tromboplastina (PTT) · Grupo sanguíneo y factor Rh · Reticulocitos.
- **Química sanguínea** — Glicemia en ayunas · Glicemia post-prandial (2 horas)
  · Hemoglobina glicosilada (HbA1c) · Urea · Creatinina · Ácido úrico · Perfil
  lipídico completo · Colesterol total · Colesterol HDL · Colesterol LDL ·
  Triglicéridos · Proteínas totales y fraccionadas · Bilirrubina total y
  fraccionada · TGO (AST) · TGP (ALT) · Fosfatasa alcalina · Gamma glutamil
  transferasa (GGT) · Amilasa · Lipasa · Electrolitos (sodio, potasio, cloro) ·
  Calcio sérico · Magnesio · Fósforo · Hierro sérico · Ferritina · Transferrina.
- **Hormonas** — TSH · T3 total · T4 libre · Anticuerpos anti-TPO · Insulina
  basal · Cortisol matutino · Prolactina · FSH · LH · Estradiol · Progesterona
  · Testosterona total · Testosterona libre · Beta-HCG cuantitativa · Vitamina
  D (25-OH) · Vitamina B12 · Ácido fólico.
- **Orina y heces** — Examen de orina (uroanálisis) · Urocultivo con
  antibiograma · Examen de heces · Coprocultivo · Sangre oculta en heces.
- **Inmunología y serología** — VDRL · VIH (ELISA) · Antígeno de superficie de
  hepatitis B (HBsAg) · Anticuerpos anti-hepatitis C · Toxoplasma IgG e IgM ·
  Rubéola IgG e IgM · Proteína C reactiva (PCR) · Factor reumatoide · ASTO ·
  Anticuerpos antinucleares (ANA).
- **Marcadores** — Antígeno prostático específico (PSA) total · PSA libre.
- **Estudios** — Electrocardiograma · Radiografía de tórax PA y lateral ·
  Ecosonograma abdominal · Ecosonograma pélvico · Ecosonograma mamario ·
  Mamografía · Citología cervical (Papanicolau) · Densitometría ósea.

Preparaciones de referencia (se copian tal cual al ítem cuando el médico elige
del catálogo, y él las puede editar en el renglón):

- `Ayuno de 8 a 12 horas.` — glicemia, perfil lipídico, química en general.
- `Ayuno de 12 horas. No ingerir alcohol las 24 horas previas.` — triglicéridos.
- `Tomar la muestra entre las 7 y las 9 de la mañana.` — cortisol.
- `Primera orina de la mañana, chorro medio, previo aseo genital.` — orina.
- `Muestra tomada antes de iniciar antibióticos.` — urocultivo, coprocultivo.
- `No requiere ayuno.` — hematología, serología, hormonas tiroideas.
- `Vejiga llena: tomar un litro de agua una hora antes y no orinar.` — eco pélvico.
- `Sin desodorante, talco ni cremas en axilas ni mamas el día del estudio.` — mamografía.
- `No tener relaciones ni usar óvulos las 48 horas previas. Fuera del período menstrual.` — citología.

---

## 3. `app/pdf_examenes.py` — el PDF de la orden

Módulo **puro**: no toca la base, no lee configuración, no escribe nada más
que el PDF pedido. Misma hoja que el récipe: carta apaisada 279,4 × 215,9 mm,
dos mitades de 139,7 mm, línea de corte, ornamento, membrete, código arriba a
la derecha de cada mitad, pie con Paciente y Fecha.

Se implementa **subclasando `pdf_recipe._Recipe`** y reutilizando su geometría
(`MARGEN_IZQ_MM`, `GUIA_DER_MM`, `SANGRIA_MM`, `INTERLINEA_MM`, `CUERPO_Y0_MM`,
`PIE_RP`, `PIE_IND`, `ALTO_DISPONIBLE_RP_MM`, `ALTO_DISPONIBLE_IND_MM`, el
ornamento, la línea de corte y `_encabezado`). Lo único que se reescribe es
`componer()` y los dos cuerpos. **No se copia y pega la geometría.**

Rótulos de las mitades: izquierda **`Solicito:`**, derecha **`Ind.`**.
`_encabezado` recibe el rótulo por parámetro, así que alcanza con pasárselo;
hay que **verificar por medición** que `Solicito:` no se solapa con el logo ni
con el `N.º` del código, y si no entra a `PT_RP`, bajar el cuerpo de ese
rótulo lo mínimo necesario y dejarlo dicho en un comentario con el número.

### API pública

```python
def medir_contenido(datos, *, ruta_logo=..., dir_fuentes=...) -> dict
def generar_examenes(datos, ruta_salida, *, ruta_logo=..., dir_fuentes=...) -> str
```

`datos` es un dict plano:

```python
{
  "codigo": "EC-0001",
  "fecha_emision": "26/08/2026" | "2026-08-26" | date,
  "paciente_nombre": "María Fernanda Rodríguez Blanco",
  "items": [
     {"examen": "Hematología completa",   # sale en las DOS mitades, mismo número
      "muestra": "Sangre",                # solo en la mitad Solicito:, a la derecha
      "indicaciones": "No requiere ayuno."},  # solo en la mitad Ind.
  ],
  "indicaciones_generales": "Traer los resultados al control del 5 de septiembre.",
}
```

`medir_contenido` devuelve exactamente las mismas claves que el del récipe:
`entra`, `rp_usado_mm`, `rp_disponible_mm`, `ind_usado_mm`, `ind_disponible_mm`,
`nombre_estado`, `nombre_impreso` (se conservan los nombres `rp_*`/`ind_*` para
que la interfaz y los avisos sean los mismos).

### Reparto entre mitades (mismo criterio que el récipe, dec. 5 adaptada)

- **Solicito:** solo la lista numerada de análisis con su tipo de muestra a la
  derecha del renglón. Es la mitad que se entrega en el laboratorio.
- **Ind.:** cada análisis repetido con **su mismo número** y debajo su
  preparación; después, separado, el bloque de indicaciones generales. Un
  análisis sin preparación se lista igual, solo con su nombre: un hueco en la
  numeración se lee como un renglón perdido.

### Errores

`ExamenesError` (base) · `RecursoFaltanteError` (hereda de
`pdf_comun.RecursoFaltanteError` **y** de `ExamenesError`) ·
`ContenidoNoCabeError` · `NombreNoCabeError`. Mismo molde y mismos mensajes que
`pdf_recipe`, para que `rutas.py` los enganche igual.

### Bloque `if __name__ == "__main__":`

Ejemplo real de 6 análisis que escribe `build/examenes_prueba.pdf`.

---

## 4. `app/pdf_infiltraciones.py` — el PDF del mapa

Módulo puro. **Carta vertical** (`pdf_comun.HojaCarta`), una o dos páginas,
membrete de marca repetido, mismo aire que el informe y la historia clínica.

```python
def generar_infiltraciones(datos, ruta_salida, *, ruta_logo=..., dir_fuentes=...,
                           dir_laminas=...) -> str
```

`datos`:

```python
{
  "codigo": "EC-0001",
  "fecha": "2026-08-26",
  "paciente_nombre": "…",
  "paciente_edad": "38",          # puede venir vacío
  "vista": "mujer-frontal",       # elige la lámina en `dir_laminas`
  "productos": [
     {"id": "p1", "nombre": "Toxina A — marca 1", "tipo": "toxina",
      "unidad": "U", "color": "#D92B2B", "lote": "", "caducidad": ""}],
  "puntos": [
     {"orden": 1, "x": 0.412, "y": 0.233,   # normalizadas 0-1 sobre la lámina
      "lado": "I", "zona": "Frontal — línea media medial",
      "productoId": "p1", "dosis": 2, "notas": "intradérmico"}],
  "observaciones": "…",
}
```

Contenido, en este orden:

1. Membrete de marca + `N.º EC-0001` (los de `pdf_comun.HojaCarta`), título
   **«Registro de infiltraciones»** y la fecha en letra.
2. Paciente y edad en un renglón; nada de cédula (dec. 4 del récipe).
3. **La lámina con los marcadores dibujados por fpdf2**, al ancho útil: la
   imagen va con `image()` y encima, con las primitivas de dibujo, un círculo
   relleno del color del producto por cada punto con su **número adentro** en
   blanco o negro según el contraste. Los puntos con dosis 0 o vacía salen
   como círculo hueco gris. **Nada de canvas ni de `window.print()`**: el PDF
   se arma entero del lado del servidor.
4. Leyenda de productos debajo de la lámina: cuadradito de color · nombre ·
   unidad · lote.
5. Tabla de puntos **agrupada por región** (Frente, Glabela, Cejas, Periocular,
   Nariz, Tercio medio, Perioral, Tercio inferior, Cuello, Otras) con subtotal
   por grupo: `N.º · Lado · Zona · Producto · Dosis · Notas`. Cebreado suave,
   ninguna fila partida entre páginas.
6. **Totales por producto** destacados al pie de la tabla.
7. Observaciones.
8. Firma: la misma `recursos/firma.png` que usa el informe.

Los marcadores se distinguen **por número**, no solo por color (tiene que
leerse impreso en blanco y negro).

Errores: `InfiltracionesError` y `RecursoFaltanteError` (misma herencia doble
que arriba).

`dir_laminas` por defecto: `<raíz de recursos>/recursos/infiltraciones`, donde
ya están `base-mujer.jpg`, `base-hombre.jpg` y `plantillas.json`.

---

## 5. API HTTP (`app/rutas.py`)

Todo cuelga de `crear_app`, con el mismo estilo de los endpoints que ya están:
`_cuerpo()`, `_texto()`, `ErrorEntrada`, `jsonify`, transacción única.

### Exámenes

| Método | Ruta | Qué hace |
|---|---|---|
| `GET`  | `/api/sugerencias/analisis?q=` | `[{id, texto, grupo, muestra, preparacion, veces_usado}]` |
| `POST` | `/api/examenes/medir` | igual que `/api/medir`, para el aviso de capacidad |
| `POST` | `/api/examenes/vista-previa` | PDF inline, en carpeta temporal, sin escribir nada |
| `POST` | `/api/examenes` | guarda + PDF + visor → `{codigo, ruta_pdf, aviso?}` |
| `GET`  | `/api/examenes?q=&desde=&hasta=` | historial, tope 200, igual que récipes |
| `GET`  | `/api/pacientes/<id>/examenes` | los del paciente, para la historia |
| `GET`  | `/api/examenes/<id>/pdf` | devuelve el PDF guardado |
| `POST` | `/api/examenes/<id>/abrir` | lo abre en el visor del sistema |
| `POST` | `/api/examenes/<id>/anular` | anula con motivo, igual que el récipe |

Cuerpo de `POST /api/examenes` y de la vista previa:

```json
{ "paciente": { "id": 3, "nombre": "…", "cedula": "", "edad": "", "sexo": "", "telefono": "" },
  "items": [ {"examen": "…", "muestra": "…", "indicaciones": "…"} ],
  "diagnostico": "", "indicaciones_generales": "", "fecha_emision": null }
```

Mismo orden de operaciones que `guardar_recipe`: **medir antes de escribir**,
una sola transacción `BEGIN IMMEDIATE` (alta/actualización del paciente +
`codigos.asegurar_codigo_paciente` + inserción del examen y sus ítems +
aprendizaje de los términos nuevos en `analisis`), y recién después la carpeta
del paciente, el PDF y el visor. Si el PDF falla, la orden **queda guardada** y
se avisa con el código, igual que el récipe.

PDF en `pacientes\EC-NNNN_.../examenes\EXAMENES_EC-NNNN_AAAA-MM-DD.pdf`
(con `_v2`, `_v3`… si repite). Hace falta:

- agregar `"examenes"` e `"infiltraciones"` a `SUBCARPETAS_PACIENTE`;
- `ruta_examenes_nueva(dir_datos, codigo, nombre, fecha_iso)`, calcada de
  `ruta_informe_nueva`.

### Infiltraciones

| Método | Ruta | Qué hace |
|---|---|---|
| `GET`  | `/api/infiltraciones/catalogo` | `{vistas, puntos, plantillas, zonas, productos}` (de `recursos/infiltraciones/plantillas.json` + los productos genéricos) |
| `GET`  | `/recursos/infiltraciones/<archivo>` | sirve `base-mujer.jpg` / `base-hombre.jpg` (lista blanca, nada de rutas relativas) |
| `POST` | `/api/pacientes/<id>/infiltraciones` | crea la sesión, genera el PDF, lo abre |
| `GET`  | `/api/pacientes/<id>/infiltraciones` | lista las del paciente |
| `GET`  | `/api/infiltraciones/<id>` | la sesión entera, para reabrirla |
| `PUT`  | `/api/infiltraciones/<id>` | la corrige y **regenera** el PDF |
| `GET`  | `/api/infiltraciones/<id>/pdf` · `POST …/abrir` · `POST …/anular` | igual que el récipe |

El JSON de la sesión que viaja en `POST`/`PUT`/`GET` es el del modelo de datos
de `App Botox`, con `paciente` resuelto por `paciente_id` del lado del servidor:

```json
{ "fecha": "2026-08-26", "vista": "mujer-frontal",
  "calibracion": {"pupilaIzq":[0.33,0.41], "pupilaDer":[0.66,0.41], "menton":[0.5,0.83]},
  "productos": [...], "puntos": [...], "observaciones": "" }
```

Límites de validación: ≤ 200 puntos, ≤ 20 productos, `x`/`y` en `[0, 1]`,
`dosis` ≥ 0 y ≤ 999, textos con los topes de `MAX_TEXTO_CORTO` /
`MAX_TEXTO_LARGO` que ya existen.

---

## 6. Interfaz (`app/web/`)

- `index.html` — dos `<section class="panel">` nuevas (`panel-examenes`,
  `panel-infiltraciones`) y sus dos botones en el `<nav class="pestanas">`.
- `estilos.css` — lo nuevo se agrega **al final**, con los tokens que ya están
  (`--verde`, `--teal`, `--texto`…). Ningún color suelto fuera de los tokens,
  salvo los colores de producto de las infiltraciones, que son datos.
- `app/web/examenes.js` y `app/web/infiltraciones.js` — módulos nuevos, cargados
  con `<script src>` después de `app.js`. `app.js` expone lo mínimo que
  necesitan (`irAPestana`, el paciente abierto en la historia y los helpers de
  autocompletar) por un objeto global `window.Recipes = {...}`; no se
  reescribe `app.js` entero.

### Pestaña Exámenes

Calcada de «Nuevo récipe» y con la misma banda de paciente: si hay una historia
abierta, la orden arranca con ese paciente puesto y la banda lo dice.
Renglones con: **Análisis** (autocompletar sobre `/api/sugerencias/analisis`,
que al elegir rellena muestra y preparación pero **deja los dos campos
editables**), **Muestra**, **Preparación**. Botón «+ Agregar análisis».
Además, un **panel de análisis frecuentes agrupado por su `grupo`**, con casillas
para tildar varios de una: es la vía rápida, no la única. Aviso de capacidad y
vista previa en `<iframe>`, exactamente como el récipe. Botón único
«Guardar e imprimir».

### Pestaña Infiltraciones

El mapa de `App Botox` portado, **no un iframe**: su CSS entra en `estilos.css`
y su JS en `infiltraciones.js`, adaptados a esta app. Lo que se conserva tal
cual porque es el corazón del asunto:

- coordenadas faciales (origen interpupilar, unidad DIP, mentón `v = 1.667`),
  calibración de 3 clics y las dos láminas calibradas de fábrica;
- las 5 plantillas y los 35 puntos de `plantillas.json`;
- lienzo con overlay **SVG**, clic para agregar, arrastrar para mover, `Supr`
  para borrar, zoom con rueda, espejo con `M`, deshacer/rehacer ≥ 50 pasos;
- tabla viva sincronizada en los dos sentidos, agrupada por región, con
  totales en vivo por producto.

Lo que cambia al integrarse:

- el paciente **sale de la historia clínica**, no de un campo suelto;
- guardar ya no descarga un `.json`: va a la base con `POST`, y las sesiones
  anteriores del paciente se listan y se reabren desde la misma pestaña;
- imprimir ya no es `window.print()`: es el PDF del servidor (`§4`), que se
  guarda en la carpeta del paciente y se abre en el visor;
- los colores de la interfaz son los tokens de esta app.

---

## 7. Historia clínica

En el PDF de la historia (`pdf_historia.py`) y en la pantalla de la historia,
las órdenes de exámenes y los registros de infiltraciones aparecen listados
junto a los récipes y los informes del paciente, con su fecha y un botón para
abrir el PDF. Es un agregado, no una reescritura.

---

## 8. Pruebas

Una suite por pieza, con el estilo de las que ya están (pytest, sin red, con
`RECIPES_DIR` a un `tmp_path`):

- `tests/test_pdf_examenes.py` — geometría, reparto entre mitades, numeración
  pareja, capacidad, errores.
- `tests/test_pdf_infiltraciones.py` — marcadores donde tienen que ir, tabla,
  totales, salto de página.
- `tests/test_examenes_api.py` — alta, medición, previa, historial, anulación,
  aprendizaje del catálogo.
- `tests/test_infiltraciones_api.py` — alta, validación de límites, reapertura,
  edición, anulación.
- `tests/test_basedatos.py` — la migración nueva, el catálogo sembrado, y que
  una base de la 2.0 migre a la 2.1 sin perder nada.

Toda la suite tiene que pasar, la vieja incluida.
