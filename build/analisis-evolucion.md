# Análisis de la evolución — Fase 0 (historia médica)

> Generado el 2026-08-18 a partir de `referencias/Historia clínica.pdf`, las dos plantillas
> `informe medico plantilla*.docx` y `referencias/medicion-whatsapp-ejemplo.jpeg`,
> por tres agentes de análisis independientes.

---

# PARTE A — Historia clínica (PDF)

# Análisis de `Historia clínica.pdf` — Espacio Corporal

Archivo: `C:\Users\luxmu\OneDrive\Desktop\Récipe Espacio\referencias\Historia clínica.pdf`
Método: 5 páginas rasterizadas a 200–700 dpi con PyMuPDF y leídas visualmente. **El PDF no tiene capa de texto** (`get_text()` devuelve `''` en las 5 páginas; cada página es una sola imagen). Todo lo que sigue sale de lectura visual, no de OCR.

---

## 1. Qué es el documento

Es un **formulario preimpreso genérico**, fotocopiado/escaneado, titulado **"HISTORIA CLÍNICA DEL SERVICIO DE MEDICINA INTERNA."** — o sea, una historia clínica **hospitalaria** (de piso/internación), no de consultorio privado. Encima el médico hizo **anotaciones a mano con marcador negro**: tachados, checks (✓), un renombre de sección y tres cajas dibujadas.

| Pág. | Contenido | Naturaleza |
|---|---|---|
| 1 | Título, Ficha de identificación (tabla 2 columnas), Síntoma inicial, Padecimiento actual, Antecedentes heredo-familiares, cabecera de APNP | Preimpreso + marcas a mano |
| 2 | Antecedentes personales **no** patológicos (completo), cabecera de Antecedentes personales patológicos | Preimpreso + tachados |
| 3 | Antecedentes personales patológicos (completo), Interrogatorio por aparatos y sistemas (inicio) | Preimpreso + tachados + X grande |
| 4 | Interrogatorio por aparatos y sistemas (resto), **"EXAMEN FÍSICO" escrito a mano**, tabla de signos vitales | Preimpreso + X grande + escritura |
| 5 | Repetición de la tabla de signos vitales (tenue), Exploración física por regiones, **rectángulo grande vacío dibujado a mano** | Preimpreso + X grande + caja |

Ninguna página está rellenada con datos de un paciente real. Es una **plantilla que el médico está editando a mano para decirte qué quiere y qué no**.

Marcas de "esto SÍ": ✓ junto a `ANTECEDENTES ... FAMILIARES`, ✓ junto a `ANTECEDENTES PERSONALES NO PATOLÓGICOS`, ✓ junto a `Actividad física`, guiones cortos junto a Madre/Padre/Hermanos/Hijos, y el borde de la tabla de identificación **repasado a mano en negro grueso**.

Marcas sin texto: dos rectángulos vacíos dibujados arriba en la pág. 1 (esquina izq. y der., encima del título) y un rectángulo grande vacío al pie de la pág. 5. Ver preguntas.

---

## 2. Secciones y campos, en orden y con nombre literal

### 2.1 FICHA DE IDENTIFICACIÓN (pág. 1) — tabla de 2 columnas, borde repasado a mano

Columna izquierda:

| Campo literal | Tipo aparente | Nota |
|---|---|---|
| `NOMBRE:` | texto corto | ya existe en `pacientes.nombre` |
| `AFILIACIÓN:` | texto corto | hospitalario (seguro/institución) |
| `Cama:` | texto corto | hospitalario puro |
| `Ocupación:` | texto corto | |
| `Edad:` | número (años) | ya existe |
| `Origen:` | texto corto | lugar de nacimiento/procedencia |
| `Tipo de Interrogatorio:` | lista (directo / indirecto / mixto) | |
| `Elaboró:` | texto corto | quién escribió la historia |

Columna derecha:

| Campo literal | Tipo aparente | Nota |
|---|---|---|
| `Estado Civil:` | lista corta | |
| `Sexo:` | lista (M/F) | ya existe |
| `Religión:` | texto corto | |
| `Escolaridad:` | texto corto / lista | |
| `Clínica de Adscripción:` | texto corto | hospitalario |
| `Residente:` | texto corto | médico residente a cargo — hospitalario |
| `Tipo de Sangre:` | lista (A+, O−, …) | **ojo: repetido en APNP, y allá SÍ está tachado** |
| `Fecha de Elaboración:` | fecha | |

**No hay campo de cédula/DNI, ni teléfono, ni dirección, ni código de paciente** en el papel. Los tres primeros ya los tenés en la app; el código es la novedad que el médico pidió.

### 2.2 MOTIVO DE CONSULTA (pág. 1)

`SÍNTOMA INICIAL:` está **tachado** y reemplazado a mano por **`MOTIVO DE CONSULTA`**. Tipo: texto corto/medio, uno por consulta.

`PADECIMIENTO ACTUAL:` **tachado** (queda absorbido por el motivo de consulta).

### 2.3 ANTECEDENTES ~~HEREDO~~ FAMILIARES (pág. 1) — ✓ conservado

La palabra `HEREDO` está tachada; queda **"ANTECEDENTES FAMILIARES"**.

| Campo | Tipo |
|---|---|
| `Madre:` | texto largo |
| `Padre:` | texto largo |
| `Hermanos:` | texto largo |
| `Hijos:` | texto largo |

### 2.4 ANTECEDENTES PERSONALES NO PATOLÓGICOS (pág. 2) — ✓ conservado

| Campo literal | Tipo | Estado |
|---|---|---|
| `Tipo de Sangre:` | lista | **TACHADO** |
| `Cartilla de vacunación / esquema completo:` | sí/no + texto | **TACHADO** (ilegible por el trazo, es el campo de vacunación) |
| `Alimentación:` | cuestionario numérico | conservado |
| `Habitación:` | cuestionario de vivienda | conservado (no tachado) |
| `Actividad física:` | texto corto | conservado, con ✓ |
| `Fauna nociva:` | texto corto | **TACHADO** |
| `Higiene:` | texto corto | **TACHADO** |
| `Viajes recientes:` | texto corto | **TACHADO** |
| `Tatuajes/Piercings:` | sí/no | **TACHADO** |
| `Contacto con personas con Tuberculosis:` | sí/no | **TACHADO** |
| `Contacto con personas con COVID:` | sí/no | **TACHADO** |

Detalle de `Alimentación:` — son **fracciones con denominador impreso**, el médico anota el numerador:
`__/3 Comidas al día`, `__/7 veces de frutas y verduras`, `__/7 pollo`, `__/7 pescado`, `__/7 carnes rojas`, `__/7 alimentos con carbohidratos y lípidos`, `__/2 litros de agua al día`.
→ 7 números enteros pequeños, cada uno "sobre" un denominador fijo (3, 7, 7, 7, 7, 7, 2).

Detalle de `Habitación:` — `Casa propia ___`, `familiar con el que vive: ___`, `cocina ___`, `baños ___`, `recámaras ___`, `iluminación y ventilación ___`, `servicios básicos intra y extradomiciliarios ___`, `agua ___`, `luz ___`, `drenaje ___`, `construida de material ___`, `hacinamiento ___`. Son ~12 huecos cortos. **No está tachado, pero es el bloque más "hospital público mexicano" de todo el papel** — ver preguntas.

### 2.5 ANTECEDENTES PERSONALES PATOLÓGICOS (págs. 2–3)

| Campo literal | Tipo | Estado |
|---|---|---|
| `Crónico-degenerativos:` | texto largo | conservado (con "COVID" escrito a mano debajo) |
| `Alcoholismo:` | texto corto | conservado |
| `Tabaquismo:` | texto corto | conservado |
| `Toxicomanías:` | texto corto | conservado |
| `Quirúrgicos:` | texto largo | conservado |
| `Traumáticos:` | texto largo | conservado |
| `Ginecológicos:` | texto largo | conservado |
| `Hospitalizaciones previas:` | texto largo | conservado |
| `Transfusiones:` | texto corto | conservado |
| `Exposición a Biomasa:` | texto corto | **TACHADO** |
| `Enfermedades congénitas:` | texto largo | **TACHADO** |
| `Enfermedades de la infancia:` | texto largo | **TACHADO** |
| `Enfermedades infectocontagiosas:` | texto largo | **TACHADO** |
| `Alergias:` | texto largo | conservado |

En `Crónico-degenerativos:` el médico escribió a mano **"COVID."** — probablemente para indicar que el antecedente de COVID (que borró de APNP) va acá, dentro del texto libre.

### 2.6 INTERROGATORIO POR APARATOS Y SISTEMAS (págs. 3–4) — **TODO TACHADO con dos X gigantes**

Contenido que se elimina (dejo constancia completa):
- `Síntomas generales:` Astenia, Dinamia
- `Oftalmológicos:` Disminución de la agudeza visual, Escotomas, Amaurosis
- `Digestivo:` Dolor oral, Parestesias, Sialorrea, Xerostomía, Dolor en parótidas, Hiporexia, Pirosis, Episodios de regurgitación, Náusea, Dolor abdominal generalizado, Hematemesis, Vómito
- `Nefrourinario:` Disuria, Polaquiuria, Tenesmo vesical
- `Glándulas endocrinas:` Hirsutismo, Intolerancia a cambios de temperatura, Piel seca
- `Musculoesquelético y articular:` Dolor en extremidades
- `Hematológico:` Equimosis fáciles, Hematomas en miembros torácicos, Pélvicos, Petequias, Púrpura adenomegalias, Masas
- `Psiquiátrico:` Insomnio, Agitación psicomotriz, Llanto fácil, Pensamientos negativos

Todos eran casillas sí/no. **Ninguna sobrevive.**

### 2.7 EXAMEN FÍSICO (pág. 4) — sección renombrada a mano

Justo encima de la tabla, escrito a mano y subrayado con flecha: **"EXAMEN FÍSICO"**. Es el reemplazo del bloque tachado. Lo que queda debajo es **la tabla de signos vitales**, en dos filas de seis:

| Campo | Tipo | Unidad implícita |
|---|---|---|
| `TA` | texto (sistólica/diastólica) | mmHg |
| `F.C.` | número entero | lpm |
| `F.R.` | número entero | rpm |
| `Temp.` | número decimal | °C |
| `TAM` | número (calculable de TA) | mmHg |
| `Dxtx` | número entero | mg/dL (glucemia capilar) |
| `TFG` | número | mL/min/1.73m² (calculable) |
| `SatO2` | número entero | % |
| `Peso` | número decimal | kg |
| `Talla` | número decimal | m o cm |
| `IMC` | número decimal | **calculable de peso/talla** |

La tabla aparece dos veces (pie de pág. 4 y cabecera de pág. 5) — es la misma tabla, repetida por el formulario. Una sola vez en la app.

### 2.8 EXPLORACIÓN FÍSICA (pág. 5) — **TODO TACHADO con X gigante**

Constancia de lo eliminado: `EXPLORACIÓN FÍSICA:` (rayado), `HABITUS EXTERIOR:` (rayado), `EXPLORACIÓN NEUROLÓGICA:`, `CABEZA:`, `CUELLO:`, `TORAX:`, `ABDOMEN:`, `GENITALES:`, `EXTREMIDADES:` (esta última queda justo al borde de la X — ambigua, ver preguntas).

Debajo, un **rectángulo grande vacío dibujado a mano** que ocupa el tercio inferior de la página.

---

## 3. Lista de tachados (excluidos del modelo de datos)

**Excluir con seguridad:**

1. `SÍNTOMA INICIAL` → renombrado a **Motivo de consulta**
2. `PADECIMIENTO ACTUAL`
3. `HEREDO` (de "Antecedentes heredo familiares") → queda **Antecedentes familiares**
4. `Tipo de Sangre` (el de APNP)
5. `Cartilla de vacunación`
6. `Fauna nociva`
7. `Higiene`
8. `Viajes recientes`
9. `Tatuajes/Piercings`
10. `Contacto con personas con Tuberculosis`
11. `Contacto con personas con COVID`
12. `Exposición a Biomasa`
13. `Enfermedades congénitas`
14. `Enfermedades de la infancia`
15. `Enfermedades infectocontagiosas`
16. **Todo `INTERROGATORIO POR APARATOS Y SISTEMAS`** (8 subsecciones, ~35 casillas — detalle completo en §2.6)
17. **Todo `EXPLORACIÓN FÍSICA` por regiones** (Habitus exterior, Neurológica, Cabeza, Cuello, Tórax, Abdomen, Genitales, y probablemente Extremidades)

**No tachados pero sospechosos** (campos de hospital público que no encajan en un consultorio privado): `AFILIACIÓN`, `Cama`, `Clínica de Adscripción`, `Residente`, `Tipo de Interrogatorio`, `Elaboró`, y el bloque entero de `Habitación`. Están en la lista de preguntas, no los excluyo por mi cuenta.

---

## 4. ¿Hay estructura de consultas / evolución repetible?

**No en el papel — y eso es el hallazgo más importante.**

Este formulario es una historia clínica de **ingreso**: se llena **una sola vez, de arriba a abajo**, para un episodio. No tiene hoja de evolución, ni notas por fecha, ni tabla de seguimiento. Por eso:

- La **tabla de signos vitales aparece dos veces** (pág. 4 y 5): el formulario original la repite justamente porque cada toma es un momento distinto, pero no hay estructura para muchas tomas.
- El **rectángulo grande dibujado a mano al pie de la pág. 5** es, casi seguro, el lugar donde el médico piensa "acá va lo que se repite": notas de evolución, o el espacio para pegar la imagen de medición de WhatsApp.

Pero el pedido del médico (historia + informes + imágenes de medición que llegan por WhatsApp + código por paciente que va en todos los récipes) **sí implica evolución**: un paciente que vuelve, que se pesa otra vez, que acumula mediciones. La app tiene que agregar lo que el papel no tiene.

**División propuesta:**

- **Se llena una vez por paciente (y se corrige)**: identificación, antecedentes familiares, APNP (alimentación, actividad física), APP (crónico-degenerativos, alcoholismo, tabaquismo, toxicomanías, quirúrgicos, traumáticos, ginecológicos, hospitalizaciones, transfusiones, alergias).
- **Se llena por consulta**: fecha, motivo de consulta, signos vitales completos (TA, FC, FR, Temp, TAM, Dxtx, TFG, SatO2, Peso, Talla, IMC), notas de evolución, diagnóstico, plan. Y de acá cuelgan los récipes, los informes y las imágenes.

Los signos vitales **tienen que ser por consulta**, no del paciente: son justo lo que cambia y lo que el médico va a querer comparar entre visitas.

---

## 5. Modelo de datos SQLite propuesto

Sigue el estilo de `app/basedatos.py`: español, `creado_en`/`actualizado_en` en toda tabla, texto libre generoso, migraciones incrementales sobre el esquema existente.

### 5.1 Ampliar `pacientes` (migración v2, `ALTER TABLE ADD COLUMN`)

```sql
ALTER TABLE pacientes ADD COLUMN codigo         TEXT;    -- código único POR PACIENTE
ALTER TABLE pacientes ADD COLUMN ocupacion      TEXT;
ALTER TABLE pacientes ADD COLUMN estado_civil   TEXT;
ALTER TABLE pacientes ADD COLUMN escolaridad    TEXT;
ALTER TABLE pacientes ADD COLUMN religion       TEXT;
ALTER TABLE pacientes ADD COLUMN origen         TEXT;    -- lugar de nacimiento/procedencia
ALTER TABLE pacientes ADD COLUMN direccion      TEXT;
ALTER TABLE pacientes ADD COLUMN tipo_sangre    TEXT;    -- solo si el médico lo quiere (§7)

CREATE UNIQUE INDEX IF NOT EXISTS ix_pacientes_codigo
    ON pacientes(codigo) WHERE codigo IS NOT NULL AND codigo <> '';
```

El **código por paciente** se asigna al crear el paciente y no cambia nunca. Sugerencia de formato en el espíritu de `recipes.codigo`: `EC-2026-0001` (prefijo, año de alta, secuencial), con contador propio:

```sql
CREATE TABLE IF NOT EXISTS contador_pacientes (
    anio              INTEGER PRIMARY KEY,
    ultimo_secuencial INTEGER NOT NULL DEFAULT 0,
    creado_en         TEXT NOT NULL,
    actualizado_en    TEXT NOT NULL
);
```

En `recipes` y en `informes` conviene **copiar el código literal** al emitir (`codigo_paciente TEXT`), igual que `recipe_items` copia los textos: un documento emitido es histórico y no debe cambiar si mañana se corrige la ficha.

### 5.2 `historia` — 1 a 1 con paciente, lo que se llena una sola vez

```sql
CREATE TABLE IF NOT EXISTS historia (
    id                 INTEGER PRIMARY KEY,
    paciente_id        INTEGER NOT NULL UNIQUE
                       REFERENCES pacientes(id) ON DELETE CASCADE,

    -- Antecedentes familiares (era "heredo familiares")
    fam_madre          TEXT NOT NULL DEFAULT '',
    fam_padre          TEXT NOT NULL DEFAULT '',
    fam_hermanos       TEXT NOT NULL DEFAULT '',
    fam_hijos          TEXT NOT NULL DEFAULT '',

    -- APNP (solo lo no tachado)
    alim_comidas_dia         INTEGER,   -- sobre 3
    alim_frutas_verduras     INTEGER,   -- sobre 7
    alim_pollo               INTEGER,   -- sobre 7
    alim_pescado             INTEGER,   -- sobre 7
    alim_carnes_rojas        INTEGER,   -- sobre 7
    alim_carbohidratos       INTEGER,   -- sobre 7
    alim_litros_agua         INTEGER,   -- sobre 2
    alimentacion_notas       TEXT NOT NULL DEFAULT '',
    actividad_fisica         TEXT NOT NULL DEFAULT '',
    habitacion               TEXT NOT NULL DEFAULT '',  -- un solo texto libre, no 12 campos

    -- APP (solo lo no tachado)
    cronico_degenerativos    TEXT NOT NULL DEFAULT '',
    alcoholismo              TEXT NOT NULL DEFAULT '',
    tabaquismo               TEXT NOT NULL DEFAULT '',
    toxicomanias             TEXT NOT NULL DEFAULT '',
    quirurgicos              TEXT NOT NULL DEFAULT '',
    traumaticos              TEXT NOT NULL DEFAULT '',
    ginecologicos            TEXT NOT NULL DEFAULT '',
    hospitalizaciones        TEXT NOT NULL DEFAULT '',
    transfusiones            TEXT NOT NULL DEFAULT '',
    alergias                 TEXT NOT NULL DEFAULT '',

    notas_generales    TEXT NOT NULL DEFAULT '',
    creado_en          TEXT NOT NULL,
    actualizado_en     TEXT NOT NULL
);
```

Nota de diseño: el papel descompone `Habitación` en 12 huecos y `Alimentación` en 7 números. Los 7 números valen la pena (son comparables entre consultas y el médico los usa como score dietético); los 12 de habitación no — un solo `TEXT` es más honesto y más rápido de llenar. `alergias` merece además una bandera visible en pantalla, porque es lo único de la historia que afecta directamente al récipe.

### 5.3 `consultas` — lo repetible, con signos vitales adentro

```sql
CREATE TABLE IF NOT EXISTS consultas (
    id                 INTEGER PRIMARY KEY,
    paciente_id        INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    fecha              TEXT NOT NULL,          -- ISO
    motivo_consulta    TEXT NOT NULL DEFAULT '',  -- reemplaza "síntoma inicial"

    -- Examen físico: signos vitales (§2.7)
    ta                 TEXT,      -- "120/80"
    fc                 INTEGER,   -- lpm
    fr                 INTEGER,   -- rpm
    temp               REAL,      -- °C
    tam                REAL,      -- mmHg (autocalculable de TA)
    dxtx               INTEGER,   -- mg/dL
    tfg                REAL,      -- mL/min/1.73m²
    sato2              INTEGER,   -- %
    peso               REAL,      -- kg
    talla              REAL,      -- m
    imc                REAL,      -- autocalculable de peso/talla

    evolucion          TEXT NOT NULL DEFAULT '',  -- notas libres de la consulta
    diagnostico        TEXT NOT NULL DEFAULT '',
    plan               TEXT NOT NULL DEFAULT '',

    creado_en          TEXT NOT NULL,
    actualizado_en     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_consultas_paciente ON consultas(paciente_id, fecha DESC);
```

`tam` e `imc` se calculan pero se **guardan**: si el médico corrige a mano, gana lo que él escribió.

### 5.4 `informes` — el informe médico generado

```sql
CREATE TABLE IF NOT EXISTS informes (
    id                 INTEGER PRIMARY KEY,
    paciente_id        INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    consulta_id        INTEGER REFERENCES consultas(id) ON DELETE SET NULL,
    codigo_paciente    TEXT NOT NULL DEFAULT '',   -- copia literal al emitir
    fecha_emision      TEXT NOT NULL,
    titulo             TEXT NOT NULL DEFAULT '',
    dirigido_a         TEXT NOT NULL DEFAULT '',
    cuerpo             TEXT NOT NULL DEFAULT '',   -- texto largo del informe
    archivo_pdf        TEXT,                       -- ruta relativa al PDF generado
    anulado            INTEGER NOT NULL DEFAULT 0 CHECK (anulado IN (0,1)),
    motivo_anulacion   TEXT,
    fecha_anulacion    TEXT,
    creado_en          TEXT NOT NULL,
    actualizado_en     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_informes_paciente ON informes(paciente_id, fecha_emision DESC);
```

(El contenido concreto sale de `informe medico plantilla.docx` / `informe medico plantilla 1.docx`, que no eran objeto de esta tarea.)

### 5.5 `adjuntos` — las imágenes de medición de WhatsApp

```sql
CREATE TABLE IF NOT EXISTS adjuntos (
    id                 INTEGER PRIMARY KEY,
    paciente_id        INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    consulta_id        INTEGER REFERENCES consultas(id) ON DELETE SET NULL,
    tipo               TEXT NOT NULL DEFAULT 'medicion',  -- medicion | laboratorio | otro
    fecha              TEXT NOT NULL,       -- fecha del estudio, no de la importación
    titulo             TEXT NOT NULL DEFAULT '',
    descripcion        TEXT NOT NULL DEFAULT '',
    archivo            TEXT NOT NULL,       -- ruta relativa dentro de la carpeta de datos
    nombre_original    TEXT NOT NULL DEFAULT '',
    ancho              INTEGER,
    alto               INTEGER,
    bytes              INTEGER,
    creado_en          TEXT NOT NULL,
    actualizado_en     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_adjuntos_paciente ON adjuntos(paciente_id, fecha DESC);
```

Los archivos **copiados** a `datos/adjuntos/<paciente_id>/`, nunca referenciados desde Descargas (offline total, el disco del médico es la fuente de verdad; si él borra la foto del WhatsApp la app no se rompe). Pillow para normalizar orientación EXIF y generar una miniatura.

### 5.6 Vínculo con lo existente

```sql
ALTER TABLE recipes ADD COLUMN consulta_id     INTEGER REFERENCES consultas(id) ON DELETE SET NULL;
ALTER TABLE recipes ADD COLUMN codigo_paciente TEXT NOT NULL DEFAULT '';
```

Así el récipe queda colgado de la consulta y lleva impreso el código del paciente, que es lo que el médico pidió. `recipes.codigo` (el correlativo del récipe) **se queda igual**: son dos códigos distintos y conviene que ambos aparezcan en el PDF, rotulados.

---

## 6. Cómo debería verse en pantalla

Para un médico no técnico, un solo usuario, sin manual. La regla: **nunca se ve un formulario de 60 campos**.

**Pestaña nueva: "Historia"** (junto a las que ya existen)

**Paso 1 — Buscar paciente.** Una sola caja de búsqueda arriba, grande, que filtra mientras escribe por nombre/cédula/código, igual que ya funciona el autocompletado de pacientes en el récipe. Debajo, la lista de los últimos atendidos (ya tenés `veces_atendido`/`ultima_vez`). Botón grande "Paciente nuevo".

**Paso 2 — Ficha del paciente.** Encabezado fijo, siempre visible, que no scrollea:

> **MARÍA GONZÁLEZ** · Código **EC-2026-0042** · 47 años · F
> ⚠ Alergias: penicilina
> [ Nueva consulta ] [ Nuevo récipe ] [ Nuevo informe ]

El código y las alergias arriba de todo, siempre. El código porque va en todo lo que se imprima; las alergias porque es lo único de la historia que puede hacer daño si no se ve.

Debajo, dos zonas:

**A) "Datos del paciente" — secciones plegables, todas cerradas por defecto**, con un resumen de una línea en el título para saber si hay algo adentro sin abrir:

- ▸ Identificación — *María González · 47 años · Docente*
- ▸ Antecedentes familiares — *Madre: HTA · Padre: DM2*
- ▸ Hábitos (APNP) — *Actividad física: caminata 3v/sem*
- ▸ Antecedentes patológicos — *DM2, colecistectomía 2019*

Se editan en el lugar (clic en la sección → los campos se vuelven editables → "Guardar"). Sin botón "editar historia" global, sin pantalla modal.

Alimentación se muestra como **7 selectores chiquitos con el denominador impreso al lado**: `Comidas al día [2]/3` `Frutas y verduras [4]/7` … Es rápido y respeta exactamente el papel.

**B) "Consultas" — la línea de tiempo, que es lo que el médico mira todos los días.**
Lista descendente por fecha. Cada fila colapsada muestra: `18/08/2026 · Control de peso · TA 120/80 · Peso 78.4 kg · IMC 27.1 · 📎2 📄1`. Al abrir: signos vitales completos, evolución, diagnóstico, plan, y las miniaturas de las imágenes adjuntas + los récipes e informes emitidos ese día.

**"Nueva consulta"** abre una pantalla corta y en orden natural: fecha (hoy por defecto) → motivo de consulta → tabla de signos vitales en grilla compacta (TAM e IMC se calculan solos y aparecen en gris hasta que el médico los toque) → evolución (texto grande) → diagnóstico → plan. Peso y talla **prellenados con los de la consulta anterior**, porque casi nunca cambia la talla. Botones al pie: "Guardar", "Guardar y hacer récipe", "Guardar y hacer informe".

**Imágenes de WhatsApp.** Un recuadro punteado "Arrastrá acá la imagen de la medición" dentro de la consulta abierta, más un botón "Agregar imagen…". Al soltar: la app copia el archivo, muestra la miniatura y pide solo dos cosas: fecha del estudio (adivinada de la fecha del archivo) y un título corto. Clic en la miniatura → visor a pantalla completa con zoom. Casilla "incluir en el informe" para que el PDF del informe la anexe.

**Sugerencias que ahorran trabajo real:**
- Comparar peso/IMC entre consultas con una línea simple (los datos ya están en `consultas`, no cuesta nada y es lo que más le va a gustar a alguien que sigue mediciones).
- "Imprimir historia completa" → un PDF con fpdf2, mismo encabezado/logo que el récipe, con el código del paciente en cada página.

---

## 7. Preguntas para el médico

**Sobre campos que quedaron ambiguos**

1. **Tipo de sangre**: lo tachaste en Antecedentes no patológicos pero está también en la Ficha de identificación, donde no lo tachaste. ¿Lo guardamos o lo sacamos del todo?
2. **`EXTREMIDADES:`** quedó justo en el borde de la X de exploración física. ¿También va afuera, o ese lo querés conservar?
3. El bloque **`Habitación:`** (casa propia, cocina, baños, recámaras, agua, luz, drenaje, hacinamiento…) no lo tachaste. ¿Lo usás en consultorio privado? Si sí, ¿lo querés como 12 casillas separadas o como una nota libre?
4. **`Alimentación`**: ¿confirmás los denominadores (3 comidas/día, 7 días de frutas y verduras, 7 pollo, 7 pescado, 7 carnes rojas, 7 carbohidratos, 2 litros de agua)? ¿Agregarías algo (café, alcohol, suplementos)?
5. **`COVID`** que escribiste a mano bajo "Crónico-degenerativos": ¿es un ejemplo de lo que va ahí, o querés un campo propio de antecedente COVID/vacunación?

**Sobre campos hospitalarios que no tachaste pero probablemente no usás**

6. `AFILIACIÓN`, `Cama`, `Clínica de Adscripción`, `Residente`, `Tipo de Interrogatorio`, `Elaboró`: ¿alguno te sirve en consultorio, o los sacamos todos? (Son de historia de piso.)
7. `Religión`, `Escolaridad`, `Origen`, `Estado civil`, `Ocupación`: ¿cuáles conservás?
8. El papel no tiene **cédula, teléfono ni dirección**, pero la app ya guarda cédula y teléfono. ¿Querés también dirección y correo?

**Sobre las marcas dibujadas**

9. Dibujaste **dos rectángulos vacíos arriba de la primera página**. ¿Son el logo y los datos del consultorio en el encabezado impreso, como en el récipe?
10. Dibujaste un **rectángulo grande vacío al pie de la última página**. ¿Qué va ahí: las notas de evolución, el espacio para pegar la imagen de medición, o la firma y sello?

**Sobre la estructura, que el papel no resuelve**

11. El formulario se llena **una sola vez** y no tiene hoja de evolución. Confirmame la división que propongo: antecedentes = una vez por paciente; motivo de consulta + signos vitales + evolución = cada vez que viene. ¿Correcto?
12. Los **signos vitales** (TA, FC, peso, IMC…), ¿son por consulta —se guarda el histórico y podés comparar entre visitas— o querés solo el último valor?
13. **Código de paciente**: ¿qué formato querés? Propongo `EC-2026-0001` (prefijo + año de alta + correlativo). ¿O preferís usar la cédula, o un número corrido sin año?
14. El **récipe ya tiene su propio código correlativo**. ¿En el PDF del récipe querés los dos códigos (el del récipe y el del paciente), rotulados, o el del paciente reemplaza al otro?
15. **Informes médicos**: ¿son texto libre sobre una plantilla, o tienen secciones fijas? (Voy a mirar los dos .docx, pero decime si esas plantillas son las definitivas.)
16. **Imágenes de WhatsApp**: ¿van colgadas de una consulta concreta, o son una carpeta suelta del paciente ordenada por fecha? ¿Querés que se anexen automáticamente al PDF del informe?
17. Cuando una imagen no corresponde a un día de consulta (te la mandan entre visitas), ¿la guardamos igual con su fecha, sin consulta asociada?
18. ¿Querés poder **borrar** una consulta o una imagen, o solo anularlas/ocultarlas como se hace hoy con los récipes?

---

# PARTE B — Plantillas de informe médico (.docx)

# Análisis de las dos plantillas de informe médico

Archivos analizados:
- `C:\Users\luxmu\OneDrive\Desktop\Récipe Espacio\referencias\informe medico plantilla.docx` (la llamo **Plantilla A**)
- `C:\Users\luxmu\OneDrive\Desktop\Récipe Espacio\referencias\informe medico plantilla 1.docx` (la llamo **Plantilla B**)

Método: se leyó el XML crudo del ZIP (`word/document.xml`, `styles.xml`, `docProps/*`) con `python-docx` 1.2.0 + `zipfile`, se extrajeron las imágenes embebidas y se renderizó cada `.docx` a PDF con Word para ver el resultado visual real y medir posiciones con PyMuPDF. No se escribió ni modificó nada del proyecto.

---

## 0. El hallazgo que manda sobre todo lo demás

Las dos plantillas **no son de Espacio Corporal**. Sus metadatos dicen:

```
dc:title    = "Plantilla Informe"
dc:creator  = "AXA Seguros"
```

y el logo embebido (`word/media/image1.png`, 422×227 px, idéntico en los dos archivos) es el de **"UNIDAD MEDICO QUIRURGICA 4 C.A." — RIF: J-408961261-1**, con paleta azul/amarillo/verde oliva.

O sea: el médico tomó **un formulario de informe de una aseguradora (AXA)**, le pegó el membrete de la clínica donde opera y su firma escaneada, y de ahí salieron las dos versiones. Nada de esto está atado a la identidad de Espacio Corporal. Eso condiciona las preguntas del punto 6.

Las dos imágenes embebidas (idénticas byte a byte en A y en B):

| Imagen | Contenido | Tamaño en la hoja |
|---|---|---|
| `image1.png` (86.917 B, md5 `9446f437…`) | Logo *Unidad Medico Quirurgica 4 C.A.* + RIF J-408961261-1 | 48,7 × 26,2 mm |
| `image2.png` (86.249 B, md5 `4b544560…`) | **Firma manuscrita escaneada** + "Dr. Eleazar Shiera Bastidas / R:I.F.: V.- 7769162 / M.P.P.S. 34846 / COMEZU: 7414" | 86,8 × 37,0 mm |

(Hay además un `hdphoto1.wdp` de 41 KB: es el efecto "quitar fondo" de Word sobre la firma. Por eso en el render aparece una mancha amarillenta tenue debajo de la firma — un residuo del recorte, no tinta.)

---

## 1. Estructura de cada plantilla

### Común a las dos

- **Encabezado/pie de página de Word: vacíos.** Todo, incluido el logo, está en el cuerpo.
- El **logo es una imagen flotante** (`<wp:anchor>`, `positionH relativeFrom="margin" align=left`, `positionV offset=11430 EMU`), arriba a la izquierda, pegada al margen: x ≈ 12,7 mm, y ≈ 23,3 mm.
- Debajo, el título **`INFORME MEDICO`** (así, sin tilde), 12 pt negrita. **No está centrado con alineación**: está empujado con ~70 espacios en blanco dentro de un párrafo alineado a la izquierda. Cae en x ≈ 78 mm, que *parece* centrado.
- **No hay datos del médico impresos como membrete de texto**: el nombre y la colegiatura salen dentro de una tabla (A los deja en blanco, B los rellena) y otra vez dentro de la imagen de la firma.
- Todos los "recuadros" que se ven **no son bordes de tabla**: el estilo `Normal` del documento trae `w:pBdr` en los cuatro lados (línea simple, `w:sz=2` = 0,25 pt, color `#7F7F7F`) aplicado a **cada párrafo**. Los párrafos vacíos consecutivos se fusionan visualmente y forman los cajones altos. Las tablas usan `TableGrid` sin `tblBorders` propios.

### Plantilla A — formulario en blanco (2 páginas)

Textos fijos LITERALES, en orden, con `{{campo}}` donde va lo variable:

```
INFORME MEDICO                                    (12 pt, negrita)

┌──────────────────────────────┬─────────────────────────────────┐
│ Nombre del Medico            │ COMEZU                     MPPS │
│ {{medico_nombre}}            │ 7414                      34846 │
├──────────────────────────────┼─────────────────────────────────┤
│ Especialidad                 │ Fecha del Informe               │
│ {{medico_especialidad}}      │ {{fecha_informe}}               │
└──────────────────────────────┴─────────────────────────────────┘

Datos de la prestación                            (11 pt)

┌──────────────────────────────┬─────────────────────────────────┐
│ Nombre del Paciente          │ Nº de póliza                    │
│ {{paciente_nombre}}          │ {{numero_poliza}}               │
├──────────────────────────────┼─────────────────────────────────┤
│ Prestación sanitaria         │                                 │
│ {{prestacion_sanitaria}}     │                                 │
└──────────────────────────────┴─────────────────────────────────┘

Antecedentes patológicos del paciente (indicar fecha de inicio de la patología)
{{antecedentes}}                                   (recuadro ~4 renglones)

Motivo de la consulta y/o ingreso (indicar la fecha de inicio de la enfermedad de los síntomas y del diagnóstico.)
{{motivo_consulta}}                                (recuadro ~7 renglones)

Diagnóstico
{{diagnostico}}                                    (recuadro ~4 renglones)

Evolución
{{evolucion}}                                      (recuadro ~4 renglones)

┌───────────────────────────────────────────────┐
│ {{espacio_libre_o_firma}}                     │   (tabla 1×1 vacía)
└───────────────────────────────────────────────┘

Firma del facultativo
[imagen de firma escaneada]
```

Ojo con dos detalles: **"COMEZU 7414" y "MPPS 34846" ya están escritos duro en la plantilla** (son del Dr. Shiera), y **la firma se cae a una segunda página** — la plantilla, tal como está, imprime 2 hojas y la segunda trae sólo la firma. Es un defecto del `.docx`, no una decisión.

### Plantilla B — informe redactado, con un caso real (1 página)

```
INFORME MEDICO                                    (12 pt, negrita)

┌──────────────────────────────┬─────────────────────────────────┐
│ Nombre del Medico            │ COMEZU                     MPPS │
│ Dr. Eleazar Shiera Bastidas  │ 7414                      34846 │
└──────────────────────────────┴─────────────────────────────────┘

  {{paciente_nombre}} , C.I. {{paciente_cedula}}
      → literal del ejemplo: "Mónica  Galue , C.I. 7856151"

  {{cuerpo_del_informe}}
      → literal: "Se trata de paciente femenino de 60 años de edad, quien
         consulta por presentar aumento de peso progresivo con antecedentes
         de dislipidemia y trastornos del sueño."

Diagnóstico:
              {{diagnostico}}          → "Dislipidemia"

Tratamiento indicado:   {{tratamiento}} → "Se indican exámenes pertinentes diagnósticos"

 {{ciudad}};  {{fecha_larga}}          → "Maracaibo;  07 de Junio de 2026"

[imagen de firma escaneada]
```

Los únicos textos verdaderamente fijos de B son: `INFORME MEDICO`, `Nombre del Medico`, `COMEZU`, `MPPS`, `7414`, `34846`, `Diagnóstico:`, `Tratamiento indicado:` y la ciudad `Maracaibo;`.

El cuerpo tiene una fórmula reconocible y reutilizable:

> **Se trata de paciente {{sexo: femenino|masculino}} de {{edad}} años de edad, quien consulta por presentar {{motivo}} con antecedentes de {{antecedentes}}.**

---

## 2. En qué difieren: ¿dos tipos o dos versiones?

**Son el mismo documento base, pero funcionan como dos tipos distintos de informe.** La evidencia:

- Mismo `dc:title`, mismo creador (AXA Seguros), mismas imágenes, mismo `styles.xml`, misma `sectPr`. B es descendiente directo de A (A: revisión 2, creada 23/06/2026; B: revisión 5, creada 23/06/2026 y modificada 13/07/2026).
- Pero B **borró** casi todos los rótulos de A: `Especialidad`, `Fecha del Informe`, `Datos de la prestación`, `Nombre del Paciente`, `Nº de póliza`, `Prestación sanitaria`, `Antecedentes patológicos…`, `Motivo de la consulta y/o ingreso…`, `Evolución`, `Firma del facultativo`. Y **agregó** cosas que A no tiene: la cédula del paciente, el cuerpo narrativo en prosa, `Tratamiento indicado:` y el renglón de **ciudad y fecha** al pie.
- A es un **formulario a llenar por campos** (con `Nº de póliza` y `Prestación sanitaria`: vocabulario puro de seguros). B es una **carta clínica en prosa firmada**.

Mi lectura y los nombres que les pondría en la app:

| | Nombre propuesto | Para qué sirve | Cuándo se usa |
|---|---|---|---|
| **A** | **Informe para la aseguradora** (o "Informe de prestación") | Reclamo/autorización ante seguro: póliza, prestación sanitaria, antecedentes, motivo, diagnóstico, evolución | Cuando el paciente tiene seguro y hay que sustentar un reembolso o una autorización |
| **B** | **Informe médico** (constancia clínica) | Documento libre para el paciente, otro colega, laboratorio o empresa | El día a día |

En la app las haría **dos plantillas del mismo módulo de informes**, no dos módulos: comparten membrete, bloque de médico, firma y numeración; cambia el cuerpo. Y si sólo hay que elegir una para arrancar, arrancá por **B**: es la que el médico ya usa de verdad (es la que tiene un paciente real cargado) y es la que se resuelve sola con los datos que la app ya guarda.

---

## 3. Formato visual, medido

| Propiedad | Valor (idéntico en A y B) |
|---|---|
| Papel | **A4**, 210 × 297 mm (`w:pgSz w=11900 h=16840` twips), vertical |
| Márgenes | 12,7 mm (0,5") arriba, abajo, izquierda y derecha — preset "Estrecho" de Word |
| Encabezado/pie | 12,7 mm (vacíos) |
| Ancho útil | 184,6 mm |
| Fuente base (estilo `Normal`) | **Franklin Gothic Book, 10 pt, negro `#000000`** |
| Título | 10 pt heredado, subido a **12 pt negrita** en el run |
| "Datos de la prestación" (sólo A) | 11 pt |
| Interlineado | Sencillo, `spacing after = 0` en el estilo; algunos párrafos con 3,3–3,5 pt de aire |
| Alineación | **Todo a la izquierda**; lo que parece centrado está empujado con espacios y tabuladores |
| Negritas | Sólo `INFORME MEDICO` |
| Bordes | `#7F7F7F` a 0,25 pt en los cuatro lados de **cada párrafo** (estilo `Normal`), más tablas `TableGrid` |
| Colores fuera del negro/gris | Ninguno en el texto. Todo el color viene de las dos imágenes |
| Tablas | A: 9540 dxa (logo) + tres de 9528 dxa (16,8 cm). B: 9540 + una de 10348 dxa (18,25 cm) |
| Logo | Flotante, pegado al margen izquierdo, 48,7 × 26,2 mm, y ≈ 23,3 mm |
| Firma | Flotante, margen izquierdo, 86,8 × 37,0 mm (en A se va a la página 2) |

**¿Coincide con la marca de Espacio Corporal? No, en nada.** Muestreo de color del logo embebido:

| Color del membrete de las plantillas | Marca Espacio Corporal |
|---|---|
| Azul `#0060A8` / `#0C5484` | Verde lima `#9ABE0F` |
| Amarillo `#F0CC00` | Teal `#157F6F` |
| Verde oliva `#6C9030` | Teal oscuro `#125550` |
| Celeste `#609CCC` | — |
| Tipografía Franklin Gothic Book | Lato (embebida en la app) |

No hay ni rastro de la "e" de Espacio Corporal, ni del ornamento lateral, ni de "Salud y Bienestar". Las plantillas son de otra institución.

---

## 4. Cómo generarlo: PDF con fpdf2, sin dependencias nuevas

**Recomendación: generar el informe como PDF con fpdf2. No hay absolutamente nada en estos `.docx` que exija otra cosa.**

Argumentos concretos:

1. **El contenido es trivial de componer**: texto plano en una sola fuente, dos imágenes, tablas de una y dos columnas, rectángulos de borde fino. La app ya hace cosas mucho más difíciles en `C:\Users\luxmu\OneDrive\Desktop\Récipe Espacio\app\pdf_recipe.py` (curvas Bézier con degradado nativo, tracking calibrado al décimo de milímetro).
2. **No hay campos de formulario de Word, ni macros, ni controles de contenido, ni tabla de contenidos, ni estilos que haya que preservar.** Los "recuadros" son bordes de párrafo: en fpdf2 son un `rect()`.
3. **El médico sólo imprime o comparte** — el PDF es mejor para las dos cosas: no se le descuadra al abrirlo en otra máquina y no lo puede editar quien lo recibe (importante en un documento firmado).
4. **Franklin Gothic Book no está garantizada en ninguna máquina** (es fuente de Office). Un `.docx` en una PC sin ella se re-maquetea solo y se corre todo. Con fpdf2 y Lato embebida, eso no puede pasar. Además Lato es más limpia y ya está en `recursos/fuentes/`.
5. Pasar a `.docx` como salida obligaría a arrastrar `python-docx` (o a hacer plantillado de XML a mano) al `.exe` empaquetado, y a cargar con los defectos del original (la firma que se cae a la página 2, el título centrado con espacios).

**Ventajas de rehacerlo en fpdf2**, además: se arregla el salto de página de la firma, `INFORME MEDICO` queda centrado de verdad, los recuadros crecen o se achican según cuánto escribió el médico (en el `.docx` son cajas fijas y el texto largo las desborda), y el informe puede llevar el **código único del paciente** arriba a la derecha con el mismo criterio que el récipe (`N.º  EC-2026-0001`, `PT_CODIGO = 13`, guía derecha), que es justamente el cambio que se viene.

**Plan B, si la aseguradora exige Word** (sólo la Plantilla A podría tener esa exigencia): se puede generar `.docx` **sin instalar nada**, usando el `.docx` original como molde y reemplazando marcadores dentro de `word/document.xml` con `zipfile` + `str.replace` de la stdlib. Es un módulo de ~40 líneas. Requiere primero limpiar el `document.xml` (hoy los textos están partidos en varios `<w:r>` y un `{{campo}}` no sobreviviría a un solo `replace`). Lo dejaría preparado sólo si el médico confirma que alguien se lo pide en Word.

**Lo que sí hay que resolver antes de escribir código**: qué membrete lleva el informe. Hoy hay dos identidades en juego (Unidad Médico Quirúrgica 4 C.A. en la plantilla, Espacio Corporal en la app) y una firma escaneada embebida, mientras que en el récipe el médico decidió **no imprimir firma** y dejar los renglones de Dr./CI/MPPS en blanco para el sello. Los dos documentos no pueden seguir criterios opuestos por accidente.

Si se confirma que el informe lleva la marca Espacio Corporal, la maqueta que propongo (A4, márgenes de 20 mm, Lato, paleta de marca) reusa tal cual el `_texto()`, `_texto_der()`, `_envolver()`, `_raya()` y el logo de `pdf_recipe.py`; sólo hay que factorizar esos helpers a un módulo compartido (`pdf_comun.py`) y agregar `pdf_informe.py`.

---

## 5. Qué sale solo de la base y qué escribe el médico

La base ya tiene (`app\basedatos.py`): `pacientes(nombre, cedula, fecha_nacimiento, edad, sexo, telefono, notas, veces_atendido, ultima_vez)`, `recipes(codigo, anio, secuencial, paciente_id, …)`, `recipe_items`, `diagnosticos`, `indicaciones`, `medicamentos`, `dosis`.

### Sale solo — cero tecleo

| Campo del informe | De dónde |
|---|---|
| `{{paciente_nombre}}` | `pacientes.nombre` |
| `{{paciente_cedula}}` (C.I.) | `pacientes.cedula` |
| `{{edad}}` ("de 60 años de edad") | `pacientes.edad`, o calculada de `fecha_nacimiento` — mejor calculada, así no envejece mal |
| `{{sexo}}` ("paciente femenino/masculino") | `pacientes.sexo`, concordando el adjetivo |
| `{{codigo_paciente}}` (el código único nuevo, por paciente) | tabla `pacientes` una vez que migre desde `recipes.codigo` |
| `{{fecha_informe}}` / `{{fecha_larga}}` | fecha del sistema, en formato largo: "07 de Junio de 2026" |
| `{{ciudad}}` ("Maracaibo") | constante o `config` |
| `{{medico_nombre}}`, `{{medico_especialidad}}`, COMEZU, MPPS | `config` (hoy son literales dentro del `.docx`) |
| Membrete y firma | archivo en `recursos/` |

### Sale solo pero el médico debe poder editarlo antes de imprimir

| Campo | De dónde | Por qué editable |
|---|---|---|
| `{{diagnostico}}` | último diagnóstico del paciente / catálogo `diagnosticos` con autocompletado | Un informe puede citar un diagnóstico distinto del último récipe |
| `{{tratamiento}}` | armado con los `recipe_items` del récipe más reciente (medicamento + dosis) | En el ejemplo real dice sólo "Se indican exámenes pertinentes diagnósticos": no siempre es la lista de fármacos |
| `{{antecedentes}}` (Plantilla A) | de la historia clínica, sección antecedentes | Se resume distinto según a quién va dirigido |
| `{{motivo_consulta}}` / `{{evolucion}}` (A) | de las notas de evolución de la historia | Idem |

### Lo escribe el médico cada vez

| Campo | Comentario |
|---|---|
| `{{cuerpo_del_informe}}` (B) | El párrafo narrativo. Se puede **pre-armar** con la fórmula "Se trata de paciente {sexo} de {edad} años de edad, quien consulta por presentar …" y que él sólo complete el motivo y los antecedentes. Eso le ahorra la mitad del tecleo sin quitarle el control |
| `{{numero_poliza}}` (A) | Dato del seguro; no está en la base. Habría que agregar columna en `pacientes` (o por informe: una persona puede cambiar de póliza) |
| `{{prestacion_sanitaria}}` (A) | Vocabulario de la aseguradora; conviene un catálogo tipo `diagnosticos`, que aprenda lo que ya escribió |
| `{{destinatario}}` | Ninguna de las dos plantillas lo tiene, pero un informe casi siempre va dirigido a alguien ("A quien pueda interesar", una empresa, un colega). Vale preguntarlo |

Regla de oro para el módulo: **todo campo autocompletado tiene que quedar editable en la pantalla antes de generar**, y lo que el médico corrige a mano se guarda en el informe (no pisa la historia clínica). Y como los informes van a alimentar el histórico del paciente, cada informe emitido debería quedar guardado en la base con su texto final y su PDF, colgado del paciente y de su código único — igual que los récipes.

---

## 6. Preguntas para el médico

**Sobre la identidad del documento (bloqueantes: sin esto no se puede maquetar)**

1. El informe, ¿va con el membrete de **Espacio Corporal** (logo verde/teal, como el récipe) o con el de **Unidad Médico Quirúrgica 4 C.A.** (el azul/amarillo de las plantillas)? ¿Depende de dónde atendió al paciente? Si es lo segundo, ¿la app tiene que dejarlo **elegir el membrete al generar**?
2. ¿Tiene el archivo original del logo de Unidad Médico Quirúrgica en buena calidad? El que está dentro del `.docx` es de 422 × 227 px: sirve para pantalla, pero impreso a 48,7 mm queda en ~220 dpi y se nota apenas blando.
3. En el récipe decidió **no imprimir firma** y dejar los renglones para el sello. En el informe la firma escaneada **sí** está embebida. ¿Quiere que el PDF del informe salga ya firmado (misma imagen), o prefiere firmar a mano cada copia impresa?
4. ¿Confirma los datos de colegiatura para dejarlos fijos en la app? En el documento aparecen: **Dr. Eleazar Shiera Bastidas, COMEZU 7414, M.P.P.S. 34846, R.I.F. V-7769162**. ¿Y cuál es la **especialidad** que va en el informe (el campo está vacío en las dos plantillas)?
5. Ciudad al pie: ¿siempre **Maracaibo**?

**Sobre los tipos de informe**

6. ¿La versión con `Nº de póliza` / `Prestación sanitaria` / `Evolución` (Plantilla A) **se la pide alguna aseguradora en particular**, y con ese formato exacto? ¿La entrega en papel, o alguien le exige el archivo Word?
7. Si la respuesta a 6 es "en papel o PDF": armamos las dos como **PDF**. ¿Le sirve elegir el tipo con un desplegable ("Informe médico" / "Informe para la aseguradora") al momento de generar?
8. ¿Hay un **tercer tipo** que hoy hace a mano y no está en estos archivos? (constancia de reposo, referencia a un colega, informe de resultados de medición…)

**Sobre el contenido y el flujo**

9. El párrafo de B arranca siempre igual: *"Se trata de paciente femenino de 60 años de edad, quien consulta por presentar…"*. ¿Quiere que la app le arme esa primera frase sola con los datos del paciente y él siga escribiendo, o prefiere el recuadro en blanco?
10. `Tratamiento indicado:` — ¿le sirve que la app le ofrezca, con un botón, **volcar los medicamentos del último récipe** de ese paciente, para después editarlos?
11. El **código único por paciente**, ¿quiere verlo impreso en el informe (por ejemplo arriba a la derecha, `N.º EC-2026-0001`, como en el récipe)?
12. ¿El informe debe llevar el **teléfono / dirección / correo** del consultorio en algún lado? Las plantillas no traen ninguno.
13. Cuando el informe se pase de una página (un antecedente largo, por ejemplo), ¿prefiere que la app lo **deje pasar a la hoja 2** con el membrete repetido, o que le avise *"no entra, acortá"* como hace hoy el récipe?
14. ¿Los informes se **guardan** en la app junto a la historia del paciente (para reimprimir o consultar después), o son de un solo uso?
15. Las **imágenes de medición que le llegan por WhatsApp**: ¿tienen que salir **anexadas dentro del PDF del informe** (por ejemplo una página "Anexos" con las fotos), o sólo viven en la historia clínica y el informe apenas las menciona?

**Un dato que conviene aclararle**

16. Estas dos plantillas salieron de un formulario cuyo autor figura como **AXA Seguros**. Antes de que la app las convierta en su formato oficial, conviene confirmar que el diseño de la Plantilla A (rótulos, orden de secciones) no es algo que la aseguradora exija literalmente — si lo es, hay que respetarlo al pie de la letra; si no lo es, conviene rediseñarla con la marca propia y de paso arreglar lo que hoy sale torcido (la firma que se va sola a una segunda página, y los recuadros de tamaño fijo que se desbordan cuando el texto es largo).

---

# PARTE C — Imagen de medición (WhatsApp)

# Análisis: imagen de informe de medición que llega por WhatsApp

Archivo analizado: `C:\Users\luxmu\OneDrive\Desktop\Récipe Espacio\referencias\medicion-whatsapp-ejemplo.jpeg`

**Hallazgo previo importante:** el mismo archivo, byte por byte (SHA-256 idéntico, 131.949 bytes), está también en la raíz del proyecto con el nombre `WhatsApp Image 2026-08-18 at 3.14.48 PM.jpeg`. O sea: tenemos evidencia directa de cómo el archivo aterriza en la máquina del médico — con el nombre por defecto de WhatsApp Desktop/Web. Eso condiciona todo el punto 4.

---

## 1. Qué es

Es el **informe de composición corporal generado por la app de una báscula de bioimpedancia Bluetooth**, no un análisis de laboratorio ni un estudio de imagen.

- **Equipo:** `CF610_G`, MAC Bluetooth `CF:E9:10:14:70:1C` (visible en el pie).
- **Método:** bioimpedancia eléctrica (BIA) de báscula con 4 u 8 electrodos — reporta análisis segmental (brazos/tronco/piernas), así que es de las de handles o de plataforma con segmentación estimada.
- **Advertencia legal impresa en el propio informe** (relevante para el informe médico): dice que las básculas de grasa corporal Bluetooth que venden *"no son dispositivos médicos"* y que el usuario debe consultar a un médico. Conviene que el PDF de la historia lo respete como dato de origen, no como diagnóstico.
- **Idioma:** español, pero con **traducción automática defectuosa** desde el chino/inglés. Hay que saberlo porque el médico va a leer cosas raras:
  - `27edad` = "27 años"
  - `seglar` = **segmental** (mala traducción de *segmental*)
  - `Nivel de adiposidad` = grado/índice de obesidad
  - `Puntuación de salud ... 58punto` = score interno de la app, 0–100
  - `Proyecto` (encabezado de tabla) = *ítem / parámetro*

### Transcripción completa de los valores visibles

**Identificación**
| Campo | Valor |
|---|---|
| Nombre | Luciana |
| Sexo | Femenino (ícono ♀ rosado) |
| Fecha y hora de la medición | **14/08/2026 13:41:08** |
| Edad | 27 años |
| Altura | 168 cm |

**Composición corporal**
| Ítem | Valor | Rango normal |
|---|---|---|
| Puntuación de salud | 58 puntos | — |
| Peso | **97,9 kg** | 50,4 – 68,2 |
| Agua corporal total | 39,9 kg | — |
| Masa proteica | 10,8 kg | — |
| Minerales | 3,8 kg | — |
| Masa grasa | 43,4 kg | — |

*(nota al pie de esa tarjeta: Peso total = Agua corporal + Masa proteica + Minerales + Masa grasa)*

**Análisis de grasa muscular** (barras Bajo / Normal / Alto, escala en % del estándar)
| Ítem | Valor | Rango normal | Ubicación |
|---|---|---|---|
| Peso (kg) | 97,9 | 50,4 – 68,2 | Alto |
| Cantidad de músculo esquelético (kg) | 30,2 | 22,4 – 27,5 | Alto |
| Masa grasa (kg) | 43,4 | 11,9 – 19,0 | Alto (fuera de escala) |

**Análisis de obesidad** (barras Bajo / Estándar / Alto)
| Ítem | Valor | Rango normal | Ubicación |
|---|---|---|---|
| IMC (kg/m²) | **34,6** | 18,5 – 25,0 | Alto |
| Porcentaje de grasa (%) | **44,3** | 18,0 – 28,0 | Alto |
| Nivel de adiposidad | 165 | 90,0 – 110,0 | Alto (fuera de escala) |

**Tipo de cuerpo** (matriz 3×3, celda resaltada en azul): **"Tipo de sobrepeso muscular"**

**Otros indicadores**
| Ítem | Valor |
|---|---|
| Masa libre de grasa | 54,5 kg |
| Masa grasa subcutánea | 38,1 kg |
| Edad corporal | 35 |
| Grasa visceral | 19 |
| Ingesta calórica recomendada | 2011 kcal/día |

**Control de peso**
| Ítem | Valor |
|---|---|
| Peso estándar | 70,8 kg |
| Control de peso | −27,1 kg |
| Control de grasa | −27,1 kg |
| Control muscular | 0 kg |
| TMB (tasa metabólica basal) | 1547 kcal |

**Análisis segmental de grasa** (kg y % del estándar)
| Segmento | Izq. | Der. |
|---|---|---|
| Brazos | 2,3 kg / 255,5 % | 2,4 kg / 266,6 % |
| Tronco (B) | 22,5 kg / 409 % | — |
| Piernas | 6 kg / 260,8 % | 6 kg / 260,8 % |

**Análisis segmental muscular** (kg, sin porcentaje)
| Segmento | Izq. | Der. |
|---|---|---|
| Brazos | 2,7 kg | 2,6 kg |
| Tronco (B) | 24,7 kg | — |
| Piernas | 8,1 kg | 8,3 kg |

Total: **~30 valores numéricos** por informe. Es una cantidad seria de datos — más de lo que el médico va a querer tipear a mano.

---

## 2. Calidad técnica

| Propiedad | Medición |
|---|---|
| Dimensiones | **909 × 1280 px** (relación 1:1,408, vertical) |
| Peso | **131.949 bytes (129 KB)** |
| Formato | JPEG **progresivo**, sin submuestreo visible de daño grave (~0,11 bytes/px ⇒ calidad ~75–80) |
| Perfil / DPI | **sin metadatos de DPI**, densidad JFIF `(1,1)` unidad 0 = sin unidad |
| EXIF | **ninguno** (WhatsApp lo borra) |
| Colores únicos | 35.251 (mucho para un render puro ⇒ hay artefactos JPEG alrededor del texto) |

### ¿Captura de pantalla o foto?

**Ni una ni otra en sentido estricto: es una imagen generada por la app** ("compartir informe"). Pruebas duras:

- Las esquinas superiores izquierda y derecha tienen **exactamente la misma media y el mismo desvío estándar** de color (media 70,4/113,9/254,5; σ 3,98/2,93/0,87) — es un degradado sintético perfectamente simétrico.
- La franja inferior es **blanco puro absoluto, σ = 0,00** en ambas esquinas. Una foto nunca da eso; una captura con ruido de cámara tampoco.
- **No hay barra de estado** (ni reloj, ni batería, ni señal), y la relación 909:1280 (0,71) no corresponde a ninguna pantalla de teléfono (los teléfonos dan 0,46–0,56). Es un lienzo compuesto por la app.
- Los 1280 px del lado largo son el **tope de reescalado de WhatsApp**: la imagen original era más grande y WhatsApp la bajó a 1280 y la recomprimió.

Consecuencia práctica: es lo mejor que podemos esperar (texto vectorial renderizado, no fotografiado), pero **ya viene degradado por WhatsApp** y no podemos recuperar la resolución original. Si el médico quisiera mejor calidad tendría que pedirle al paciente que le mande el archivo **como documento** en WhatsApp (sin compresión), no como foto.

### Legibilidad impresa

Medí las alturas reales de línea de texto en píxeles:

| Elemento | Altura |
|---|---|
| Nombre / valores grandes | 17–21 px |
| Texto legal del pie, etiquetas de tabla | 11–12 px |
| Números de las escalas de las barras | 9 px |
| Leyenda pequeña ("Masa muscular: insuficiente / estándar / excelente") | **6 px** |

**Carta vertical (216×279 mm) con márgenes de 20 mm** → la imagen entra ajustada por altura: 170 × 239 mm, **≈136 dpi efectivos**.

| Elemento | Altura impresa | Veredicto |
|---|---|---|
| Valores y nombres | 3,2–3,9 mm | Perfectamente legible |
| Etiquetas de tabla y pie legal | 2,2 mm | Legible |
| Números de las escalas | 1,7 mm | Al límite, se lee con esfuerzo |
| Leyenda de colores | **1,1 mm** | **Ilegible** |

**Media carta (140×216 mm)** → entra ajustada por ancho: 116 × 163 mm, **≈199 dpi**, pero todo se achica un 32 %: las etiquetas de tabla caen a 1,5 mm y los números de escala a 1,15 mm.

> **Conclusión: sí, imprimir a página completa carta vertical y no menos.** En media carta solo sobreviven los números grandes; las tablas se vuelven una mancha. Y en el récipe (que hoy es **carta apaisada**, 279×216 mm) esta imagen no tiene lugar — va en la historia y en el informe, que deberían ser **carta vertical**.

---

## 3. ¿Posiciones fijas o variables?

Respuesta corta: **la plantilla es fija, la geometría no.** Es "extraíble a futuro" pero no por coordenadas absolutas.

**Lo que es estable** (misma app, mismo modelo de báscula, mismo idioma):
- El orden y la existencia de las tarjetas: cabecera → composición → tipo de cuerpo → otros indicadores → control de peso, en la columna izquierda; grasa muscular → obesidad → segmental, en la derecha.
- Los rótulos son literales fijos ("Masa Libre de Grasa", "TMB (Tasa Metabólica Basal)", "Nivel de adiposidad"…), incluidas las traducciones malas. Sirven como **anclas**.
- El formato de fecha `DD/MM/AAAA HH:MM:SS` y las unidades pegadas al número (`54.5kg`, `2011kcal/Día`, `168cm`).

**Lo que va a variar:**
- **El tamaño de la imagen.** 909×1280 salió de que WhatsApp achicó a 1280 el lado largo; el ancho depende del ancho de pantalla del teléfono del paciente. Otro teléfono → otra relación de aspecto → todas las coordenadas absolutas se mueven.
- **La altura de las tarjetas**, si la app agrega o quita filas por sexo/edad, o si el nombre es largo y hace salto de línea.
- **La posición horizontal de los valores dentro de las barras**, que es justamente proporcional al valor (por eso "97.9" está a media barra y "43.4" contra el borde).
- El **modelo de báscula**: si el paciente cambia de equipo, cambia el layout entero.

**Traducción a arquitectura:** cualquier extracción futura tiene que ser **relativa a anclas de texto** (encontrar "Masa Libre de Grasa" y leer a la derecha), nunca por recortes de píxeles fijos. Y hay que guardar el **ancho original en px** de cada imagen para poder normalizar.

**Pero — y esto es lo importante — nada de eso es requisito ahora.** La prioridad es anexar la imagen. Lo único que hay que hacer hoy pensando en el futuro es **guardar el original sin tocar** (sin recortar, sin recomprimir, sin reescalar) y guardar su hash. Si en dos años se quiere extraer datos, se procesa el archivo guardado. Si hoy recomprimimos "para ahorrar espacio", esa puerta se cierra para siempre.

---

## 4. Flujo propuesto

### El problema real, con datos de esta máquina

Miré cómo llega hoy el archivo y cómo está el entorno:

- El archivo llega con nombre **`WhatsApp Image 2026-08-18 at 3.14.48 PM.jpeg`**. Es el nombre por defecto de WhatsApp Desktop/Web al descargar.
- **La fecha del nombre no es la fecha de la medición.** El nombre dice 18/08/2026; el informe adentro dice 14/08/2026. Cuatro días de diferencia. **Jamás usar la fecha del archivo como fecha clínica.**
- La carpeta `Descargas` del médico tiene **55 archivos** de todo tipo (instaladores, PDFs, `.stl`, `CLAUDE.md`…) con imágenes sueltas de 2024. Es un basurero, no un buzón.
- La app ya tiene una carpeta de datos consolidada: `%USERPROFILE%\Documents\Recipes\` con `datos\`, `pdf\`, `registro\`, `respaldos\`, `recursos\`.

### Evaluación de las opciones

**(a) Carpeta especial vigilada**

*Pros:* el médico tiene un lugar mental único ("las mediciones van ahí"); la app no tiene que adivinar; se puede acumular varias imágenes y procesarlas después.

*Contras (fuertes, para este usuario):* **le exige cambiar un hábito**. En WhatsApp Web dentro de Chrome, la descarga va a `Descargas` de una, sin diálogo, salvo que active "Preguntar dónde guardar cada archivo" — que es tocar la configuración del navegador, algo que él no va a hacer ni debería. En WhatsApp Desktop sí aparece un "Guardar como", pero navegar a la carpeta correcta **cada vez** es exactamente la clase de fricción que hace que en la tercera semana deje de usarlo y vuelva a guardar en Descargas.

**(b) Botón "Adjuntar imagen" con el selector apuntado a Descargas**

*Pros:* cero hábitos nuevos, funciona con lo que ya hace, y es el único camino para casos raros (una foto de un informe en papel, un PDF de laboratorio, algo que le pasaron por correo).

*Contras:* con 55 archivos y nombres como `WhatsApp Image 2026-08-18 at 3.14.48 PM.jpeg`, elegir el correcto es incómodo, y el diálogo de Windows a veces ordena por nombre y no por fecha. Riesgo real de anexar la imagen equivocada al paciente equivocado.

### Recomendación: (c) ambas — pero con un reparto específico

No es "las dos por si acaso". Es que cada una cubre una mitad distinta, y hay una tercera pieza que resuelve el contra principal de (b).

**Pieza 1 — Bandeja de imágenes recientes (esto es lo principal).**
Dentro de la pantalla de la historia del paciente, un panel plegable: **"Imágenes recientes en tu computadora"**. La app mira, sin vigilancia en segundo plano (solo al abrir la pantalla o al apretar "Actualizar"):
1. `%USERPROFILE%\Downloads`
2. `%USERPROFILE%\OneDrive\Escritorio` y `%USERPROFILE%\Desktop`
3. `%USERPROFILE%\Documents\Recipes\entrada\` (la crea la app)

Filtra imágenes (`.jpg .jpeg .png .webp`) modificadas en los **últimos 30 días**, y muestra **miniaturas** ordenadas de más nueva a más vieja, con la fecha del archivo debajo. Debajo de cada una, un botón **"Anexar a esta historia"**.

Las miniaturas son la clave: el médico **ve** el informe azul de Luciana y hace clic. No lee nombres de archivo, no navega carpetas, no cambia hábitos. Elimina de un saque el riesgo de anexar la imagen equivocada, que es el peor contra de (b).

Las que ya anexó (por hash SHA-256) dejan de aparecer, así que la bandeja se va vaciando sola sin borrar nada del disco.

**Pieza 2 — Botón "Adjuntar imagen…" siempre visible**, que abre el selector de archivos con carpeta inicial en `Descargas`. Es la salida de emergencia y el camino para PDFs o archivos de otro lado. Barato de hacer, imposible de que falle.

**Pieza 3 — La carpeta `entrada` con acceso directo en el Escritorio.**
La app crea `Documents\Recipes\entrada\` y, la primera vez, deja un acceso directo en el Escritorio llamado **`MEDICIONES — soltar aquí`**. No es obligatorio usarlo. Sirve para el médico que sí quiere ordenarse: arrastra ahí lo que va acumulando y lo procesa el viernes. Como la bandeja ya vigila esa carpeta, funciona sin configurar nada.

**Opcional, si sale barato:** arrastrar y soltar la imagen directamente sobre la ventana de la historia. En pywebview el drag-and-drop de archivos es peleado (hay que habilitar el acceso al path real del archivo, y no es parejo entre WebView2 y otros backends). Yo lo dejaría para una versión posterior y **no lo pondría en el alcance de esta**; con las tres piezas de arriba el flujo ya es más corto que arrastrar.

### El flujo, contado como lo vive el médico

1. Le llega la imagen por WhatsApp Web, en la misma computadora.
2. Clic en la imagen → flechita de descargar. (Lo que ya hace hoy.)
3. Abre la app → busca al paciente → **Historia**.
4. En "Imágenes recientes" ya está la miniatura arriba de todo.
5. Clic en **"Anexar a esta historia"**.
6. Se abre un diálogo chico: **fecha de la medición** (prellenada con la fecha del archivo, **marcada como "verificá esta fecha"** porque casi nunca coincide), **tipo** (desplegable: Medición de composición corporal / Laboratorio / Estudio de imagen / Otro) y **nota** opcional.
7. Guardar. La miniatura pasa a la lista de anexos de la historia y desaparece de la bandeja.

Cinco clics y un campo a revisar. Sin explorador de archivos, sin nombres de archivo, sin carpetas.

---

## 5. Cómo guardarla en la historia

### En el disco

Copia — **nunca mover, nunca borrar, nunca modificar el original**. Si la copia falla a mitad, el original sigue en Descargas y el médico no perdió nada.

Con el código ahora **por paciente**, la estructura natural es:

```
%USERPROFILE%\Documents\Recipes\
  pacientes\
    EC-2026-0001_Luciana-Perez\
      anexos\
        2026-08-14_medicion_01.jpg
        2026-08-14_medicion_01.thumb.jpg     ← miniatura 400px, generada
        2026-09-11_laboratorio_01.jpg
```

Reglas:
- **Nombre:** `<fecha-de-la-medición>_<tipo>_<nn>.<ext-original>`. La fecha es la que el médico confirmó en el paso 6, **no** la del archivo. El `nn` correlativo resuelve dos mediciones el mismo día.
- **Extensión original preservada** y **bytes originales sin tocar** — nada de recomprimir ni reescalar. Son 129 KB; mil anexos son 130 MB. No hay problema de espacio que justifique perder el original.
- **Miniatura aparte** (Pillow, ~400 px de lado largo) para que la pantalla de la historia cargue rápido sin abrir el JPEG completo cada vez.
- En la base, una tabla `anexos`: `id`, `paciente_id`, `ruta_relativa`, `sha256`, `fecha_medicion`, `tipo`, `nota`, `ancho_px`, `alto_px`, `bytes`, `origen` (ruta de donde se copió), `creado_en`. El `sha256` da deduplicación (si anexa dos veces la misma imagen, avisar) y hace de marca de "ya procesada" para la bandeja.
- Rutas **relativas** a la carpeta de datos, para que mover `Documents\Recipes` a otro disco no rompa nada — igual que ya funciona hoy.
- La carpeta de anexos entra en el **respaldo zip** existente. Ojo: los respaldos hoy son de la base sola y pesan poco; con imágenes van a crecer. Vale la pena que el respaldo diario sea incremental o que se pregunte si incluir anexos.

### En pantalla

Sí, mostrarla. En la historia, una sección **"Anexos"** con grilla de miniaturas, cada una con su fecha y tipo debajo. Clic → visor a tamaño completo (lightbox simple, con zoom, porque a 909 px de ancho el médico va a querer agrandar las tablas). Y un botón "Abrir con el visor de Windows" para cuando quiera imprimirla sola.

### En el PDF

Sí, pero **como anexo al final y opt-in por documento**, no incrustada en medio del texto.

- Al generar el PDF de la historia o del informe, una lista de casillas: **"¿Qué anexos incluir?"**, con las miniaturas y la fecha. Por defecto, ninguno marcado en el informe (los informes suelen ser cortos y para entregar) y quizás todos marcados en la historia completa.
- Cada anexo va en **su propia página**, con un encabezado tipo `Anexo A — Informe de medición de composición corporal — 14/08/2026` más el código del paciente, y la imagen ajustada al área imprimible manteniendo proporción.
- **Carta vertical obligatorio** para las páginas de anexo, aunque el récipe siga siendo carta apaisada. Con márgenes de 20 mm la imagen sale a 170×239 mm y ~136 dpi efectivos, que según lo medido arriba es el mínimo donde las tablas se leen.
- Con fpdf2 esto es directo: `pdf.image(ruta, x, y, w=170)` calculando la altura por proporción y centrando. Pillow para leer las dimensiones y decidir si ajustar por ancho o por alto (si alguna vez llega una imagen apaisada, hay que manejarlo).
- El PDF crece ~130 KB por anexo. Aceptable.

---

## 6. Preguntas para el médico

**Sobre el contenido**
1. ¿Esta báscula `CF610_G` es la única fuente, o vas a recibir informes de otras marcas/modelos con otro diseño? ¿Es tu equipo del consultorio o el de cada paciente en su casa?
2. ¿Qué otras cosas te llegan por WhatsApp que también querrías anexar? ¿Laboratorios, ecos, fotos de recetas de otros médicos, fotos del paciente para seguimiento? Esto define el desplegable de "tipo" y si hay que aceptar PDFs además de imágenes.
3. ¿Cuántas mediciones por paciente por año, más o menos? ¿Alguna vez vas a querer una vista de "evolución" comparando dos informes lado a lado?
4. ¿Te interesa que en algún momento la app te deje **tipear a mano** los 5 o 6 valores clave (peso, IMC, % de grasa, masa muscular, grasa visceral) para poder graficar la evolución — aunque la imagen quede igual anexada? Es mucho más simple y confiable que cualquier lectura automática, y son 30 segundos por medición.

**Sobre el flujo**
5. ¿Usás **WhatsApp Web en Chrome** o la **aplicación de escritorio de WhatsApp**? Cambia si al descargar aparece o no un diálogo de "Guardar como".
6. Cuando descargás una imagen de WhatsApp hoy, ¿dónde termina? ¿Le cambiás el nombre o la dejás como viene?
7. ¿Te resulta más natural (i) descargar como siempre y que la app te muestre las imágenes recientes con miniaturas, o (ii) tener una carpeta fija en el Escritorio donde ir dejando las cosas? Podés tener las dos, pero quiero saber cuál vas a usar de verdad.
8. La imagen ya llega comprimida por WhatsApp. ¿Podés pedirle a quien te la manda que te la envíe **como documento/archivo** en vez de como foto? Se ve bastante mejor impresa. ¿O es imposible en la práctica?

**Sobre la salida impresa**
9. La historia clínica y los informes, ¿los querés en **carta vertical**? (El récipe hoy es carta apaisada. Los anexos necesitan vertical para leerse.)
10. Cuando entregás un informe médico al paciente o a otro colega, ¿querés que **incluya la imagen de la medición** o preferís que el informe sea solo tu texto y la imagen quede guardada nada más en tu historia? ¿Querés decidirlo caso por caso?
11. ¿Querés que el PDF reproduzca la **advertencia legal** de la báscula ("no son dispositivos médicos") junto al anexo, o preferís que no aparezca?

**Sobre los datos**
12. ¿Vas a anexar imágenes con **nombre y datos de otro paciente** visibles (como esta, que dice "Luciana")? Si el nombre en la imagen no coincide con el paciente de la historia, ¿querés que la app te avise o que no se meta?
13. ¿La carpeta `Documents\Recipes` está sincronizada con OneDrive? Con imágenes esa carpeta va a crecer bastante y quiero saber si eso te trae problemas de espacio o de sincronización.

---

## Resumen de decisiones que propongo

| Punto | Decisión |
|---|---|
| Prioridad | **Anexar la imagen.** Extracción de datos: fuera de alcance, pero se preserva el original para no cerrar la puerta. |
| Formato de entrada | JPEG/PNG/WEBP y también PDF (llega laboratorio en PDF seguro) |
| Flujo | Bandeja de miniaturas de `Descargas` + `Escritorio` + `Recipes\entrada`, **más** botón "Adjuntar imagen…" clásico |
| Vigilancia | Al abrir la pantalla y a demanda. **Sin proceso en segundo plano.** |
| Almacenamiento | Copia byte a byte en `Recipes\pacientes\<CODIGO>_<Nombre>\anexos\`, nombre `AAAA-MM-DD_tipo_nn.ext` |
| Fecha | **Siempre confirmada por el médico**, prellenada pero marcada como sospechosa (probado: 4 días de desfase) |
| Original | Nunca se mueve, nunca se borra, nunca se recomprime |
| Pantalla | Grilla de miniaturas + visor con zoom |
| PDF | Anexo al final, una página por imagen, **carta vertical**, elegible con casillas al generar |
