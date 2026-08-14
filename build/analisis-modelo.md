# Análisis del modelo — Fase 0

> Generado el 2026-08-14 a partir de `referencias/Récipe Espacio.pdf` y `referencias/Logo.jpg`,
> por dos agentes de análisis independientes. Parte A: el PDF modelo. Parte B: el logo.
>
> **Nota de reconciliación de colores:** los dos análisis midieron la paleta por caminos distintos y
> difieren en 1-2 unidades por canal. Vale la medición directa sobre `Logo.jpg` (Parte B), que es el
> archivo digital limpio: **verde lima `#9ABE0F`, teal medio `#157F6F`, teal oscuro `#125550`**.

---

# PARTE A — Análisis del PDF modelo

# Análisis del PDF modelo — `referencias/Récipe Espacio.pdf`

## 0. Naturaleza del archivo (leelo antes que nada)

| Dato | Valor |
|---|---|
| Páginas | 1 |
| `/Producer` | `mlkit` |
| `/CreationDate` | `D:20260814131627-04'00'` |
| Capa de texto | **ninguna** (`get_text()` devuelve `''`) |
| Contenido | **una sola imagen JPEG** (`DCTDecode`, DeviceRGB, 8 bits) de **2809 × 2191 px** que cubre toda la página |
| MediaBox / CropBox | `[0, 0, 1000, 780]` pt |
| `/Rotate` | ausente (0) |

**El PDF no es un original de diseño: es la foto de una hoja del talonario preimpreso, capturada con un escáner de teléfono (Google ML Kit).** Eso tiene tres consecuencias que mandan sobre todo lo demás:

1. El `MediaBox` (1000 × 780 pt = **352,78 × 275,17 mm**) **no es el tamaño del papel real**. Es el lienzo arbitrario que eligió el escáner. No lo uses como referencia de página.
2. Hay corrección de perspectiva residual: el mismo elemento medido en la mitad izquierda y en la derecha difiere hasta ~5 mm. **Todas las medidas de abajo llevan una tolerancia de ±1,5 mm**, y conviene usar siempre las de la mitad izquierda (la del Rp.), que está menos deformada.
3. Los colores están lavados por la iluminación de la foto. Para los colores de marca hay que confiar en `referencias/Logo.jpg`, no en el escaneo.

**Escala de trabajo usada:** rendericé la página a 200 dpi con PyMuPDF → 2778 × 2167 px. Con el papel real deducido (ver §1), la escala es **0,10058 mm/px en X y 0,09963 mm/px en Y** (prácticamente 1 px = 0,1 mm).

---

## 1. Tamaño de papel y orientación

### Dimensiones exactas extraídas

```
MediaBox = [0, 0, 1000, 780] pt  →  352,78 × 275,17 mm   (NO es el papel)
Relación de aspecto = 1000/780 = 1,2821
```

### Deducción del papel real

| Candidato | Relación | Diferencia |
|---|---|---|
| **Carta apaisada (279,4 × 215,9 mm)** | **1,2942** | **0,9 %** ✔ |
| A4 apaisada (297 × 210 mm) | 1,4143 | 10,3 % ✘ |
| Oficio apaisada (355,6 × 215,9) | 1,6470 | 28 % ✘ |

La prueba definitiva no es el aspecto sino **la línea de corte punteada**: cae en el píxel x = 1388,5 de 2778, es decir el **49,96 % del ancho**. Si el ancho es carta (279,4 mm = 11″), la línea cae en **139,70 mm = 5,5″ exactos**. Ninguna otra medida comercial da un corte redondo ahí.

### Conclusión

- **Hoja física: CARTA (Letter), 279,4 × 215,9 mm (11 × 8,5 in = 792 × 612 pt), orientación APAISADA (horizontal).**
- **Van DOS récipes por hoja**, partidos por una línea de corte vertical al medio.
- **Cada récipe es media carta VERTICAL: 139,7 × 215,9 mm (5,5 × 8,5 in = 396 × 612 pt).**
- La mitad izquierda es el **récipe propiamente dicho (`Rp.`)**; la mitad derecha son las **indicaciones (`Ind.`)**. No son dos récipes iguales: son las dos caras de un mismo acto médico.

---

## 2. Márgenes (media carta izquierda, la del `Rp.`)

Origen: esquina superior izquierda de la media hoja.

| Margen | Medida | Observación |
|---|---|---|
| Superior | **16,0 mm** hasta la primera tinta (borde superior del ícono del logo) | |
| Izquierdo (bloque de encabezado y cuerpo) | **16,4 mm** | El ornamento lateral ocupa de 0 a 11,4 mm; el texto arranca después |
| Izquierdo (renglón "Paciente:" al pie) | **10,5 mm** | Este renglón se mete más a la izquierda que todo lo demás |
| Derecho (hacia la línea de corte) | **13,0 mm** | Todas las rayas terminan en x ≈ 126,4 mm |
| Inferior | **21,0 mm** | Última tinta (raya de Paciente/Fecha) en y = 194,9 mm |

**Margen de trabajo recomendado para la app: 16 mm arriba, 16 mm izquierda, 13 mm derecha, 21 mm abajo**, con la salvedad de que el renglón Paciente/Fecha se saca a 10,5 mm por izquierda para ganar ancho de raya.

---

## 3. Distribución de zonas

### 3.1 Mitad izquierda — RÉCIPE (`Rp.`)

Coordenadas locales de la media carta (139,7 × 215,9 mm), origen sup-izq.

| # | Zona | x (mm) | y (mm) | Tamaño (mm) |
|---|---|---|---|---|
| 1 | Ornamento lateral (onda verde/teal) | 0 → 11,4 | 0 → 215,9 | ancho variable, máximo 11,4 mm a la altura y ≈ 39 mm |
| 2 | Ícono del logo (cuadrado verde con la "e") | 21,6 → 34,7 | 16,0 → 28,9 | **13,1 × 12,9** |
| 3 | Logotipo `espacio` / `CORPORAL` | 16,3 → 37,7 | 28,5 → 32,7 | **21,4 × 4,2** |
| 4 | Bajada `Salud y Bienestar` | 15,9 → 48,5 | 37,0 → 40,8 | **32,6 × 3,9** |
| 5 | Rótulo `Rp.` | 16,4 → 24,8 | 46,5 → 52,7 | **8,5 × 6,5** |
| 6 | **Cuerpo libre (lista de medicamentos)** | ≈ 14 → 130 | ≈ 55 → 164 | **≈ 116 × 109** — completamente en blanco, sin renglones, sin numeración, sin recuadro |
| 7 | Bloque de colegiatura (`Dr.` / `CI` / `MPPS`) | 74,7 → 126,4 | 166,8 → 180,9 | **51,7 × 14,1** |
| 8 | Renglón `Paciente:` + `Fecha:` | 10,5 → 126,7 | 189,5 → 194,9 | **116,2 × 5,4** |

**Detalle del bloque 7 (colegiatura).** Los tres rótulos están **alineados a la derecha por los dos puntos**, en x = 86,2 mm. Las rayas nacen en x = 88,5 y mueren en x ≈ 126,4.

| Renglón | Rótulo x0 | Raya | y de la raya | Largo | Grosor |
|---|---|---|---|---|---|
| `Dr.:` | 80,1 | 88,5 → 126,3 | **170,1** | 37,8 mm | 0,50 mm (1,4 pt) |
| `CI:` | 81,9 | 88,5 → 126,4 | **175,2** | 37,9 mm | 0,40 mm (1,1 pt) |
| `MPPS:` | 74,7 | 89,5 → 126,3 | **180,6** | 36,8 mm | 0,40 mm (1,1 pt) |

Interlínea del bloque: **5,2 mm**. El bloque está **descolgado a la derecha**: su borde izquierdo empieza recién a 74,7 mm, o sea que la mitad izquierda inferior del récipe queda vacía a propósito.

**Detalle del bloque 8 (paciente y fecha).**

| Elemento | x (mm) | Raya | y de la raya | Largo | Grosor |
|---|---|---|---|---|---|
| `Paciente:` | 10,5 → 28,0 | 30,2 → 83,4 | **194,6** | 53,2 mm | 0,40 mm |
| `Fecha:` | 84,8 → 96,2 | 96,9 → 126,7 | **194,5** | 29,9 mm | 0,50 mm |

### 3.2 Mitad derecha — INDICACIONES (`Ind.`)

Coordenadas locales (restando 139,7 mm a las absolutas).

| Zona | x (mm) | y (mm) |
|---|---|---|
| Ornamento lateral (**espejado, sobre el borde DERECHO**) | ≈ 129 → 139,7 | 0 → 215,9 |
| Ícono + logotipo | 17,8 → 39,3 | 16,0 → 32,7 |
| `Salud y Bienestar` | 18,2 → 50,4 | 36,7 → 40,6 |
| Rótulo `Ind.` | 18,2 → 28,0 | 47,2 → 52,4 |
| Cuerpo libre | ≈ 16 → 128 | ≈ 55 → 186 |
| `Paciente:` + raya | 16,4 → 36,7 / raya 38,3 → 87,5 | raya en 193,5 |
| `Fecha:` + raya | ≈ 103 / raya 102,9 → 130,1 | raya en 193,0 |

**Diferencia estructural clave: la mitad de indicaciones NO tiene el bloque `Dr.` / `CI` / `MPPS`.** Su cuerpo libre es por eso ~25 mm más alto que el del récipe. Los datos del médico van una sola vez, en la mitad del `Rp.`.

### 3.3 Zonas que el modelo NO tiene

Esto importa tanto como lo que sí está:

- **No hay ningún lugar previsto para el código único** (`EC-2026-0001`). Ni número de folio, ni QR, ni código de barras.
- **No hay campo de diagnóstico** (§7 y §9 de las instrucciones lo piden).
- **No hay campo de cédula del paciente**, ni de edad, ni de sexo, ni de teléfono. Sólo `Paciente:` y `Fecha:`.
- **No hay línea ni rótulo de firma.** El bloque `Dr./CI/MPPS` son datos de identificación, no un espacio de firma. El espacio en blanco entre y = 164 y y = 166 mm es el único hueco donde físicamente entraría una rúbrica, y es angosto.
- No hay dirección, teléfono, correo, RIF, colegio de médicos ni leyenda legal de ningún tipo.
- No hay marca de agua, sello, filigrana ni fondo de seguridad.
- No hay numeración ni viñetas preimpresas en el cuerpo.

Verifiqué esto con un barrido de todos los píxeles oscuros de la hoja (excluyendo ornamentos y línea de corte): aparecen **exactamente siete bandas de tinta**, que son las siete zonas listadas arriba. No hay nada más impreso en la hoja.

---

## 4. Colores

Doble columna: lo que mide el escaneo (degradado por la foto) y el valor de marca tomado de `referencias/Logo.jpg`, que es el que hay que usar en el PDF.

| Elemento | Medido en el escaneo | **Valor recomendado para la app** |
|---|---|---|
| Fondo / papel | `#FEFEFE` | **`#FFFFFF`** (papel, sin relleno) |
| Verde de marca (ícono, `CORPORAL`) | `#7F953F` → `#869853` | **`#9ABD0F`** (medido en el logo: ícono `#9ABD0F`, `CORPORAL` `#93B60F`) |
| Teal de marca (`espacio`) | `#7F876E` (muy lavado) | **`#1E8271`** |
| `Salud y Bienestar` | `#717778` (lavado) | **`#135652`** (teal oscuro del logo) |
| `Rp.` / `Ind.` | `#355B5C` / `#204747` | **`#1F5352`** — teal oscuro, misma familia que `Salud y Bienestar` |
| Rótulos `Dr.` `CI` `MPPS` `Paciente` `Fecha` | `#4E5454` / `#3C4C4C` | **`#4A5354`** (gris pizarra, no negro puro) |
| Rayas de llenado | `#505553` | **`#4A5354`**, 0,4–0,5 mm de grosor |
| Ornamento — relleno | degradado vertical: `#8BA63D` (arriba) → `#7C9D58` (medio) → `#5A968A` (abajo) | **degradado vertical `#9ABD0F` → `#1E8271`** |
| Ornamento — filete interno | `#3E7373` / `#37756C` | **`#1E8271`**, ~0,6–1,0 mm |
| Línea de corte punteada | `#C9C9C9` | **`#C9C9C9`** |
| Franja granate del borde superior | `#400C12` | **NO reproducir** — ver §7 |

Nota sobre el degradado: el ornamento **no es de un solo color**. Medido fila por fila, el relleno pasa de verde amarillento arriba a verde-teal abajo, mientras el filete interno se mantiene teal parejo. Es un degradado vertical de los dos colores de marca.

---

## 5. Tipografías

No hay capa de texto, así que todo es estimación óptica sobre el trazo. Las alturas están medidas en la altura de mayúscula (cap height) y convertidas a cuerpo asumiendo cap ≈ 0,70 em, que es lo típico de una sans humanista.

| Elemento | Alto de mayúscula | **Cuerpo estimado** | Estilo |
|---|---|---|---|
| `Salud y Bienestar` | 2,79 mm | **≈ 11,5 pt** | Sans humanista, Regular. Tracking apenas abierto |
| `Rp.` | 4,28 mm (con descendente: 6,48 mm) | **≈ 17,5 pt** | **Bold Italic** |
| `Ind.` | ≈ 4,2 mm (total 5,3 mm) | **≈ 17,5 pt** | **Bold Italic**, idéntico a `Rp.` |
| `Dr.:` | 3,09 mm | **≈ 12,5 pt** | Regular / SemiBold |
| `CI:` | 3,09 mm | **≈ 12,5 pt** | Regular / SemiBold |
| `MPPS:` | 3,19 mm | **≈ 13 pt** | Regular / SemiBold |
| `Paciente:` | ≈ 3,3 mm | **≈ 13 pt** | Regular / SemiBold |
| `Fecha:` | ≈ 3,3 mm | **≈ 13 pt** | Regular / SemiBold |
| `espacio` / `CORPORAL` | — | **no es tipografía**: es arte vectorial del logo (la palabra `espacio` está dibujada a mano) |

**Identificación de la familia.** Es una **sans humanista de eje vertical, "a" de doble piso, "t" con remate superior inclinado, terminales cortadas en diagonal y contadores abiertos**. La misma familia se usa en `Salud y Bienestar` dentro de `Logo.jpg`. Los candidatos más probables son **Lato**, **Segoe UI**, **Corbel** o **Museo Sans**.

**Recomendación para la app** (recordá §2 y §3 de las instrucciones: fuentes embebidas desde `recursos/fuentes/`, cero CDN): usar **Lato** (Regular, SemiBold/Bold y Bold Italic) — es libre (SIL OFL), se embebe sin problema en `fpdf2` y es la que más se le parece. Alternativas igual de válidas: Source Sans 3, Open Sans o Noto Sans.

**Anomalía observada:** en la mitad izquierda `Paciente:` sale más claro (`#7D898A`) que `Fecha:` (`#3C4C4C`), y en la mitad derecha pasa exactamente al revés (`Paciente:` `#4E5D5C`, `Fecha:` `#848C8D`). Como la inversión es cruzada, **no es diseño: es tinta despareja del talonario más la iluminación de la foto**. En el PDF hay que poner los cuatro rótulos con el mismo peso.

---

## 6. Textos literales impresos

Transcripción exacta, respetando mayúsculas, puntuación y espacios. Es **todo** lo que dice la hoja.

**Mitad izquierda (récipe):**

```
espacio
CORPORAL
Salud y Bienestar
Rp.
Dr.:
CI:
MPPS:
Paciente:
Fecha:
```

**Mitad derecha (indicaciones):**

```
espacio
CORPORAL
Salud y Bienestar
Ind.
Paciente:
Fecha:
```

Precisiones sobre la puntuación, que importa para reproducirlo:

- `Rp.` e `Ind.` llevan **punto final**, y van en **bold italic**.
- `Dr.:` lleva **punto y luego dos puntos** (`Dr` + `.` + `:`).
- `CI:` va **sin puntos internos** — no es `C.I.:`, es `CI:`.
- `MPPS:` en **mayúsculas sostenidas**, sin puntos.
- `Paciente:` y `Fecha:` con inicial mayúscula y dos puntos.
- El logotipo es `espacio` en minúsculas manuscritas sobre `CORPORAL` en mayúsculas.

**Datos del médico impresos: ninguno.** El talonario es genérico: `Dr.`, `CI` y `MPPS` van en blanco para llenar a mano. Tampoco hay dirección, teléfono, correo, RIF, colegio de médicos ni leyenda legal.

---

## 7. Elementos gráficos

1. **Ornamento lateral en forma de onda/hoja** — el elemento gráfico dominante. Está compuesto por **dos trazos**:
   - Un **cuerpo ancho** que nace en la esquina superior del borde exterior, se ensancha hasta **11,4 mm** a la altura de y ≈ 39 mm, y se va afinando hacia abajo hasta desaparecer cerca de y ≈ 200 mm. Relleno con degradado verde→teal, con un **filete teal más oscuro sobre su canto interno**.
   - Un **trazo fino secundario** que aparece desde y ≈ 77 mm y cruza al cuerpo principal por dentro (a x ≈ 2–9 mm), cerrando la silueta de hoja.
   
   **Está sólo sobre el borde EXTERIOR de cada mitad**: en el borde izquierdo de la mitad `Rp.` y en el borde derecho de la mitad `Ind.`, en espejo. Los cantos internos (los que quedan contra la línea de corte) **no llevan nada**. Lo confirmé barriendo píxeles de color a lo ancho de toda la hoja: sólo hay color entre 0–11 mm y entre 269–279 mm.

2. **Línea de corte vertical punteada** — en x = **139,70 mm exactos**, de y = 0,1 a y = 214,7 mm (o sea, toda la altura). Punteado irregular, gris claro `#C9C9C9`. Es la marca de troquel/corte del talonario.

3. **Cinco rayas horizontales de llenado** — las tres del bloque de colegiatura y las dos del renglón paciente/fecha. Grosor 0,4–0,5 mm (1,1–1,4 pt). Trazo simple, sin punteado.

4. **Franja granate `#400C12` en el borde superior** — recorre todo el ancho, entre y = 0,3 y y = 1,2 mm. **No es un elemento de diseño: es el engomado del talonario** (el lomo de pegamento que une las hojas del bloc), capturado por la foto. Argumentos: está exactamente sobre el filo del papel, tiene grosor irregular, el color no pertenece a la paleta de marca y **no se repite en el borde inferior**. **No hay que reproducirla en el PDF.**

5. **No hay** recuadros, marcos, marcas de agua, filigranas, sellos, tramas de seguridad ni renglones guía en el cuerpo. El área de escritura es blanco liso.

---

## 8. Puntos relevantes para las preguntas de la §15

Contra las seis preguntas del documento, esto es lo que el modelo contesta solo y lo que queda pendiente de decisión del médico.

**§15.1 — Datos del médico.**
El modelo **no trae ningún dato impreso**. Lo que define son **tres campos y no más**: `Dr.`, `CI` y `MPPS`, cada uno con 37–38 mm de raya. Ojo con dos desajustes respecto de la §5 de las instrucciones:
- El modelo pide **CI** (cédula del médico), que no está en la lista de `config` de la §5.
- El modelo **no** tiene lugar para especialidad, colegio de médicos, RIF, dirección ni teléfonos. Si esos datos tienen que salir impresos, hay que **agregar zonas que el modelo no tiene** y eso rompe la fidelidad. Hay que preguntar explícitamente si van o no van.
- Con 37–38 mm de raya y cuerpo ~12,5 pt, entran cómodos **unos 22–26 caracteres** por renglón. Un nombre largo con título va a necesitar reducción automática de cuerpo.

**§15.2 — Tamaño de papel y cuántos por hoja.** Resuelto por medición: **carta apaisada, dos por hoja, cada récipe en media carta vertical de 139,7 × 215,9 mm.** Pero queda una decisión de implementación que hay que preguntar, porque cambia todo `pdf_recipe.py`:
- **(a)** El PDF sale en **media carta vertical (396 × 612 pt)**, dos páginas por récipe (una `Rp.`, una `Ind.`), y el médico imprime en hojas media carta o dos por hoja desde el diálogo de impresión.
- **(b)** El PDF sale en **carta apaisada (792 × 612 pt)**, una sola página con las dos mitades y la línea de corte, calcado del modelo. Es lo que más se parece al talonario físico y lo que yo recomendaría.
- **(c)** Carta vertical con las dos mitades apiladas. No corresponde con el modelo, la descarto.

**§15.3 — Firma.** **El modelo no tiene línea ni rótulo de firma.** Sólo el bloque `Dr./CI/MPPS`. El único hueco donde entraría una rúbrica escaneada es la franja entre y ≈ 158 y y ≈ 166 mm, sobre la raya del `Dr.`, y es angosta (unos 8 mm de alto). Si la firma va impresa, hay que decidir si se superpone sobre esa zona o si se corre el bloque de colegiatura hacia abajo.

**§15.4 — Cédula del paciente.** **El modelo no tiene campo de cédula del paciente, ni de edad.** El renglón inferior es sólo `Paciente:` + `Fecha:`. Como la §5 y la §9 de las instrucciones sí piden cédula y edad en el PDF, hay conflicto: o se agrega un campo que el modelo no tiene, o la cédula y la edad se escriben en el mismo renglón de `Paciente:` (entra: la raya mide 53,2 mm), o no se imprimen. Decisión del médico.

**§15.5 — Sección de indicaciones separada.** **Sí, y es una mitad entera de la hoja.** El modelo está construido alrededor de esa separación: `Rp.` a la izquierda (los medicamentos), `Ind.` a la derecha (las indicaciones), cada una con su propio logo y su propio renglón de paciente y fecha, para entregarse juntas o por separado. Esto tiene consecuencias directas sobre el modelo de datos de la §5: hoy `recipe_items` guarda `indicaciones` **por renglón de medicamento**, pero el papel prevé un **bloque de indicaciones general del récipe**. Hay que preguntar si las indicaciones que van en la mitad `Ind.` son (a) la concatenación de las indicaciones de cada medicamento, (b) un campo de texto libre aparte a nivel de récipe, o (c) las dos cosas.

**§15.6 — Vigencia / "válido hasta".** **No existe en el modelo.** Ningún campo de vencimiento ni de cantidad de repeticiones.

**Pregunta adicional que el modelo obliga a hacer (no está en la §15).**
**No hay ningún lugar previsto para el código único `EC-2026-0001`**, y la §9 lo exige "visible y legible". Hay que decidir dónde ponerlo. Mis tres candidatos, por orden:
1. **Arriba a la derecha de cada mitad**, a la altura del logo (y ≈ 17–24 mm, alineado a la derecha en x = 126,4 mm, misma guía que las rayas). Es la zona más vacía del modelo y no pisa nada.
2. Pegado al renglón inferior, a la derecha de `Fecha:` — pero ahí ya no queda ancho.
3. Debajo del bloque `Dr./CI/MPPS`, en y ≈ 185 mm.

Con la opción 1, sugiero rotularlo `N.º` o `Código:` en el mismo gris `#4A5354`, cuerpo ~11 pt regular, y el código en SemiBold ~13 pt. **El mismo código tiene que ir en las dos mitades**, porque se entregan juntas y de otro modo la hoja de indicaciones queda huérfana.

**Segunda pregunta adicional: el diagnóstico.** La §7 y la §9 lo piden y **el modelo no tiene campo**. O va como primer renglón del cuerpo del `Rp.` (con un rótulo `Dx:` que el modelo no trae), o va en la mitad `Ind.`, o no se imprime aunque se guarde en la base. Decisión del médico.

---

## 9. Nota de implementación sobre el ornamento

El único activo gráfico complejo del récipe es la onda lateral, y **no lo tenemos en vectorial**: sólo existe dentro de una foto JPEG de 2809 × 2191 px, lavada y con perspectiva residual. `referencias/Logo.jpg` (1024 × 1024, JPEG, verde `#9ABD0F` y teal `#1E8271` sobre `#FEFEFE`) trae el logo pero **no** el ornamento.

Tres caminos, de mejor a peor:

1. **Pedirle al médico el arte original** del talonario (el AI/PDF/PNG que le dio la imprenta). Es lo que resuelve el problema de raíz y vale la pena preguntar antes de dibujar nada.
2. **Redibujarlo como vector** (dos curvas Bézier con degradado) y componerlo directo en `fpdf2`. Es reproducible, escala perfecto y pesa nada. Es mi recomendación si no aparece el original.
3. Recortar el ornamento del escaneo, limpiarlo, saturarlo a los colores de marca y embeberlo como PNG con transparencia. Rápido, pero arrastra el ruido y la deformación de la foto, y en una impresión a color se va a notar.

Del logo sí conviene usar `referencias/Logo.jpg` (la §9 de las instrucciones habla de "la resolución mejorada que está en la carpeta"), **recortándolo**: en el récipe el bloque del logo es ícono + `espacio CORPORAL` (21,7 × 16,7 mm), y `Salud y Bienestar` va **compuesto aparte y más ancho** (32,6 mm, contra 21,4 mm de `CORPORAL`). En `Logo.jpg` los tres elementos vienen en un solo lockup con proporciones distintas: si se pega tal cual, `Salud y Bienestar` sale chico. Además el JPEG tiene fondo blanco opaco, así que hay que recortar el fondo o generar un PNG con alfa.

---

# PARTE B — Análisis del logo

# Análisis del logo — Fase 0b

Archivo: `C:\Users\luxmu\OneDrive\Desktop\Récipe Espacio\referencias\Logo.jpg`

---

## 1. Ficha técnica del archivo

| Dato | Valor |
|---|---|
| Dimensiones | **1024 × 1024 px** (cuadrado exacto) |
| Peso | **54.408 bytes = 53,1 KB** |
| Formato | JPEG progresivo, 24 bits, `Format24bppRgb` |
| Submuestreo de croma | **4:2:0** (croma a mitad de resolución) |
| Calidad JPEG | Alta (tabla de cuantización Y arranca en 4/3/3, ~q90) |
| Metadato DPI | 72 dpi (JFIF) — es un valor nominal sin peso: lo que manda es el conteo de píxeles |
| Perfil de color | ICC **sRGB** incrustado (`Google Inc. 2016`, 456 bytes) |
| Canal alfa | **No tiene** (JPEG no soporta transparencia) |

### Geometría interna medida (umbral de no-blanco < 225)

| Elemento | Caja (x0–x1, y0–y1) | Tamaño px |
|---|---|---|
| Contenido total | 159–864, 142–863 | **706 × 722** |
| Símbolo (hoja verde) | 333–661, 145–466 | 329 × 322 |
| Punto de la «i» de *espacio* | 721–740, 473–493 | 20 × 21 |
| «espacio» + «CORPORAL» | 160–863, 509–697 | 704 × 189 |
| **Lockup símbolo + wordmark (sin bajada)** | 160–863, 145–697 | **704 × 553** (relación 1,273) |
| «Salud y Bienestar» | 165–859, 774–860 | 695 × 87 |

El contenido ocupa el 69 % del ancho del lienzo: hay **~159 px de margen blanco a cada lado y ~142/160 px arriba/abajo**. Es margen muerto que hay que recortar antes de meterlo al PDF.

---

## 2. Qué representa, colores y tipografía

### Qué representa

Es el logo de **Espacio Corporal — Salud y Bienestar**, en versión vertical apilada, tres bloques:

1. **Símbolo:** un cuadrado de esquinas redondeadas y contorno irregular / dibujado a mano (no es un rectángulo geométrico: los lados están apenas curvados y las esquinas son desiguales), en verde lima sólido. Adentro, **calado en blanco, un trazo tipo pincel que forma una «e» minúscula cursiva** — la «e» de *espacio*. El trazo también se lee como una hoja o una silueta corporal en espiral, coherente con «bienestar». El contraojo de la «e» queda verde (es contraforma, no un óvalo blanco pintado).
2. **Logotipo:** «espacio» en lettering manuscrito monolineal, verde azulado, con las letras sueltas y muy espaciadas; debajo y en contacto, «CORPORAL» en mayúsculas verde lima.
3. **Bajada:** «Salud y Bienestar» en gris-verde azulado oscuro, ancho igual al bloque de arriba.

### Colores dominantes (medidos sobre el núcleo de cada trazo, mediana del decil más oscuro)

| Uso | Hex | RGB | CMYK aprox. | % del lienzo |
|---|---|---|---|---|
| **Verde lima** — símbolo y «CORPORAL» | **`#9ABE0F`** | 154, 190, 15 | 19 / 0 / 92 / 25 | 9,5 % |
| **Teal medio** — script «espacio» | **`#157F6F`** | 21, 127, 111 | 84 / 0 / 13 / 50 | ~1,0 % |
| **Teal oscuro** — «Salud y Bienestar» | **`#125550`** | 18, 85, 80 | 79 / 0 / 6 / 67 | ~1,2 % |
| Blanco de fondo | `#FFFFFF` | 255, 255, 255 | — | 83,4 % |

Notas de color:
- El símbolo y «CORPORAL» son prácticamente el mismo verde (`#99BE0E` vs `#97B80A`): unificá en **uno solo**, `#9ABE0F`.
- El script «espacio» y la bajada **no son el mismo teal**: la bajada es netamente más oscura (`#125550` vs `#157F6F`). Es diferencia real del archivo digital, no ruido. Son dos tintas distintas de la paleta.
- El CMYK es solo informativo: `fpdf2` trabaja en RGB y la impresión va a salir por el driver RGB de una impresora de escritorio. Lo que importa son los valores hex.
- Estos tres colores son **la paleta del récipe completo**, no solo del logo: las ondas del borde del modelo son un degradado del verde lima al teal, y los textos («Rp.», «Ind.», «Paciente:», «Fecha:») son el teal oscuro. Fijá los tres como constantes en `pdf_recipe.py`.

### Tipografía

| Bloque | Diagnóstico |
|---|---|
| «espacio» | **Lettering a medida**, no una fuente. Monolineal, trazo de ancho constante, letras desconectadas, tracking muy abierto, «i» con el punto desplazado a la derecha. **No es reproducible con una fuente: tiene que ir sí o sí como imagen.** |
| «CORPORAL» | Sans **geométrica**, mayúsculas, peso bold, «O» perfectamente circular, «R» con pata recta en diagonal, «A» de ápice puntiagudo, tracking cerrado (letras casi tocándose). Compatible con **Century Gothic Bold / Futura Medium / Poppins SemiBold**. Va como imagen junto al símbolo — no vale la pena recomponerla. |
| «Salud y Bienestar» | Sans **humanista**, peso regular, «a» de doble piso con espolón, «y» de descendente recta y afinada, «t» con el ápice cortado en diagonal. Compatible con **Open Sans / Source Sans Pro / Noto Sans**. |

**Hallazgo clave para el PDF:** en el modelo la bajada **no forma parte del logo colocado**. Medido sobre el escaneo, el lockup (símbolo + «espacio CORPORAL») ocupa 27,6 mm de ancho mientras «Salud y Bienestar» ocupa **41,3 mm** — un 50 % más ancha, y separada por un espacio que no existe en `Logo.jpg`. Es decir: en el récipe impreso la bajada está compuesta como **texto vivo**, aparte, más grande, y con la misma fuente humanista que el resto del formulario. Si pegás `Logo.jpg` entero, las proporciones no van a coincidir con el modelo.

---

## 3. Fondo

**Blanco puro y opaco.** No es transparente (imposible en JPEG) ni tiene color de fondo:

- Marco exterior de 100 px: mínimo por canal **253, 253, 253**, media 254,9 — limpísimo.
- Franja superior (y 5–60): min 254, max 255, promedio 255,0.
- 70,5 % de los píxeles son `#FFFFFF` exacto; otro 13,3 % está por encima de 245.
- **No hay ruido de escaneo, ni papel, ni sombra, ni viñeteo.** Este archivo es una exportación digital, no un escaneo.

### ¿Hace falta transparencia? — Análisis del calado

Hice una prueba de conectividad (flood fill desde los bordes sobre los píxeles con luminancia ≥ 230):

```
blancos totales:                     913.938
conectados al borde (exterior):      902.365
blancos interiores aislados:          11.573
dentro del símbolo: blancos = 48.003 → conectados al exterior = 48.003 (100 %)
```

**El 100 % del blanco de la «e» está conectado con el fondo exterior**: el trazo del pincel rompe el borde inferior del cuadrado verde y sale afuera. No es un óvalo cerrado. Consecuencia práctica:

- Si convertís blanco → alfa, **la «e» también se vuelve transparente**. Sobre papel blanco el resultado es idéntico; sobre cualquier fondo de color, la «e» se llenaría de ese color y el logo se rompe.
- Los 11.573 blancos aislados son los ojales de las letras (O, P, R, A, e, a, d, B). Ahí la transparencia sí es el comportamiento correcto.

### Recomendación de fondo

**Convertir a PNG sí, con transparencia no.** Razones:

1. En el modelo el logo va arriba a la izquierda, **sobre la zona blanca del papel** (el borde de ondas verde/teal está bien lejos, a la izquierda). Fondo blanco opaco y fondo transparente dan **exactamente el mismo resultado impreso**.
2. El calado abierto de la «e» hace que el alfa sea riesgoso, no neutro.
3. El submuestreo 4:2:0 dejó **23.464 píxeles casi-blancos con desviación de color mayor a 6** (12.821 con más de 12) — un halo verdoso/amarillento alrededor del arte. Sobre blanco es invisible; recortado con alfa se convertiría en una **orla sucia** visible.

Las instrucciones piden transparencia explícitamente solo para `firma.png` (§9), que sí se superpone a la línea de firma. El logo no la necesita.

---

## 4. Calidad y resolución: ¿alcanza para imprimir a color?

### Tamaño al que aparece en el modelo

El PDF modelo (`referencias/Récipe Espacio.pdf`) es **una sola imagen JPEG escaneada** de 2809 × 2191 px a 203 dpi efectivos, sobre una página de 1000 × 780 pt = 352,8 × 275,2 mm, con **dos récipes por hoja** (Rp. e Ind., separados por una línea de corte punteada). Medido sobre el escaneo:

| Elemento en el récipe impreso | Tamaño |
|---|---|
| Lockup símbolo + «espacio CORPORAL» | **27,6 × 21,3 mm** |
| Símbolo solo | 12,5 × 11,7 mm |
| «Salud y Bienestar» (texto vivo aparte) | 41,3 × 5,1 mm |

La relación de aspecto del lockup impreso (1,296) coincide con la del archivo digital (1,273) dentro del error de escaneo → **confirmado que es este mismo logo**, sin la bajada.

> Advertencia: son milímetros **tal como fueron escaneados**. Si el escaneo no fue 1:1 el tamaño real cambia proporcionalmente. Conviene confirmarlo midiendo un récipe físico con regla — sumalo a las preguntas de §15 (va de la mano con la pregunta 2, tamaño de papel).

### DPI efectivos

Usando el **recorte del lockup (704 px de ancho)**, que es lo que realmente se va a colocar:

| Ancho impreso | DPI efectivos | Veredicto |
|---|---|---|
| **28 mm (el del modelo)** | **639 dpi** | Excelente |
| 30 mm | 596 dpi | Excelente |
| 35 mm | 511 dpi | Excelente |
| 40 mm | 447 dpi | Excelente |
| 50 mm | 358 dpi | Muy bien |
| **59,6 mm** | **300 dpi** | Límite de calidad de imprenta |

Usando el lienzo completo de 1024 px sin recortar, los números son aún más holgados (867 dpi a 30 mm, 520 dpi a 50 mm), pero ese cálculo es engañoso porque un tercio de esos píxeles es margen blanco.

**Veredicto: sobra resolución, con más del doble de margen.** Al tamaño del modelo (~28 mm) estamos en ~640 dpi contra los 300 dpi que se consideran calidad de imprenta, y los 150–300 dpi que en la práctica satura una impresora de escritorio a color. Se podría imprimir el logo hasta a 6 cm de ancho sin bajar de 300 dpi.

### Calidad real más allá del conteo de píxeles

- **Nitidez de borde:** perfil horizontal cruzando el borde izquierdo del símbolo (fila y=300): `255, 254, 253, 248, 236, 224, 127, 121…` → transición de **~3 px**. Es antialiasing limpio, no hay evidencia de reescalado agresivo. El archivo está a su resolución nativa.
- **Ringing JPEG:** nulo. No aparece el rebote típico (píxeles más claros que el fondo antes del borde). El fondo se mantiene en 253–255 hasta el borde mismo.
- **Único defecto real:** el halo de croma 4:2:0 descrito arriba (23.464 px casi-blancos con tinte). Invisible sobre blanco, pero conviene limpiarlo igual.
- **Comparación con el modelo:** el verde del símbolo *tal como fue escaneado del récipe impreso* es `rgb(134, 156, 67)` — apagado, desaturado y sucio frente al digital `rgb(154, 190, 15)`. Esto es degradación de impresión + escaneo, no el color de marca. **Nunca recortes el logo del escaneo del PDF modelo**: usá siempre `Logo.jpg`, que es la «resolución mejorada» a la que se refiere §9 de las instrucciones.

---

## 5. Recomendaciones para `recursos/logo.png`

### 5.1 Generar dos archivos, no uno

| Archivo | Contenido | Recorte en `Logo.jpg` | Tamaño resultante |
|---|---|---|---|
| **`recursos/logo.png`** | Símbolo + «espacio CORPORAL», **sin la bajada** | `(156, 141) – (868, 702)` | **713 × 562 px** |
| `recursos/logo_completo.png` *(reserva)* | Lockup entero con bajada | `(155, 138) – (869, 868)` | 715 × 731 px |

El principal es el primero. «Salud y Bienestar» se compone como **texto vivo** en `pdf_recipe.py`, con la fuente humanista embebida, en `#125550`, a ~41 mm de ancho — que es lo que hace el modelo. Guardá `logo_completo.png` por si al comparar contra el récipe físico resulta que la bajada sí venía del bloque de imagen.

Las cajas de recorte incluyen ~4 px de aire respecto del bounding box exacto, para no comerse el antialiasing de las curvas.

### 5.2 No reescalar

Exportá **1:1, sin resampleo**. A 713 px de ancho colocados a 28 mm ya estamos en ~647 dpi. Reescalar hacia arriba no agrega información y solo reintroduce blandura; reescalar hacia abajo tira margen que no cuesta nada conservar (el PNG va a pesar decenas de KB, no megas).

Si querés un número redondo para documentar: **713 px a 30,2 mm = 600 dpi exactos**. Es prácticamente el tamaño del modelo.

### 5.3 Limpieza del fondo antes de guardar

Dos pasos, en este orden, **sin tocar los píxeles por debajo de 242** (ahí vive el antialiasing y aplanarlo dentaría las curvas):

1. **Neutralizar croma:** todo píxel con luminancia ≥ 242 → `R = G = B = luminancia`. Esto mata el halo verdoso/amarillento del 4:2:0 conservando el degradado del borde.
2. **Fijar blanco puro:** todo píxel con luminancia ≥ 252 → `#FFFFFF` exacto. Elimina el ruido residual de 253–254 y deja el PNG comprimiendo mucho mejor.

Se hace con Pillow + NumPy, que ya están disponibles en la máquina — pero ojo: **es un paso de preparación de recurso que se corre una sola vez a mano, no código de la app.** Ninguna de las dos entra en las dependencias de §3.

### 5.4 Formato y metadatos de salida

- **PNG-24 (RGB), sin canal alfa, fondo blanco opaco.** Justificación completa en §3.
- **Descartar el perfil ICC** al guardar. Los valores ya son sRGB y `fpdf2` no hace gestión de color: los escribe literales. Un ICC incrustado no cambia nada y solo agrega peso y una fuente de sorpresas.
- Sin metadatos EXIF ni texto.
- Peso esperado: 40–80 KB (dos colores planos comprimen muy bien).

### 5.5 Color: dejarlo fijo en código, no derivarlo de la imagen

En `pdf_recipe.py`, constantes explícitas:

```python
VERDE_LIMA  = (154, 190, 15)   # #9ABE0F  simbolo y CORPORAL
TEAL_MEDIO  = (21, 127, 111)   # #157F6F  script "espacio"
TEAL_OSCURO = (18, 85, 80)     # #125550  bajada y textos del recipe
```

Nunca muestrees el escaneo del PDF modelo para sacar estos colores: te va a dar el verde apagado `rgb(134,156,67)` de la impresión degradada.

### 5.6 Ícono de la aplicación (gratis, de paso)

El **símbolo solo** (329 × 322 px, casi cuadrado, muy legible en chico) es el candidato natural para el `.ico` que van a pedir PyInstaller y Inno Setup en la Fase 5. Recortalo de `(330, 142) – (664, 469)`, cuadralo agregando blanco, y generá un `.ico` multirresolución con 16/32/48/64/128/256 px. Guardalo como `build/icono.ico`.

### 5.7 Ciclo de vida del archivo en la app

Según §4 y §5 de las instrucciones:
- `recursos/logo.png` va empaquetado con `--add-data` (§11.1).
- La app lo copia a `%USERPROFILE%\Documents\Recipes\recursos\logo.png` en el primer arranque.
- La ruta vive en la tabla `config`.
- Configuración (pantalla C) permite reemplazarlo. **Cuando el médico cargue un logo nuevo, reencodealo a PNG normalizado** (mismo tratamiento de §5.3) en vez de copiar el archivo crudo, y validá extensión y dimensiones mínimas: si el ancho es menor a 350 px, avisale que va a salir pixelado al imprimir — con un mensaje que diga qué hacer, según §7.

### 5.8 Verificación (para la lista de §12)

- [ ] `recursos/logo.png` abre en un visor y no tiene borde gris, halo de color ni margen blanco sobrante.
- [ ] En el PDF generado, el lockup mide **27,6 mm de ancho** (o el valor que confirme la medición del récipe físico) y su relación de aspecto está dentro del 2 % de 1,273 — sin deformar.
- [ ] Impreso a color y superpuesto contra el modelo a contraluz, símbolo y wordmark coinciden en posición y tamaño.
- [ ] Mirado con lupa, el borde curvo del símbolo no muestra escalonado ni orla de color.
- [ ] La bajada «Salud y Bienestar» del PDF generado coincide en ancho y peso con la del modelo (~41 mm).

---

## 6. Advertencias y puntos abiertos

1. **No uses el logo del PDF modelo.** El PDF es un escaneo plano a 203 dpi; su logo está degradado en color y nitidez. `Logo.jpg` es la fuente buena.
2. **El PDF modelo es una imagen, no un documento vectorial.** Todo el récipe —ondas del borde, «Rp.», líneas de firma— hay que redibujarlo en `fpdf2`. Es tarea del análisis del PDF (Fase 0a), pero condiciona al logo: las ondas usan la misma paleta de tres colores, así que fijala una sola vez.
3. **A confirmar con el médico, para sumar a §15:** el tamaño real del récipe impreso medido con regla, para validar los 27,6 mm del logo. El escaneo puede no ser 1:1 y todas las medidas en mm escalan con ese dato.
4. **A confirmar:** si el récipe se imprime uno por hoja o dos por hoja (el modelo trae Rp. e Ind. lado a lado con línea de corte). Si van dos, el logo se coloca dos veces por página.
5. **Ninguna herramienta nueva.** La preparación del PNG usa Pillow, que ya está instalado en la máquina y se corre a mano una única vez; no entra como dependencia de la app (§3). Si en algún momento se quisiera **vectorizar** el logo a SVG para calidad infinita, haría falta una herramienta externa (potrace/Inkscape) — no lo hago sin luz verde, y de todos modos **no hace falta**: 640 dpi al tamaño de uso ya está muy por encima de lo que cualquier impresora de escritorio puede resolver.
