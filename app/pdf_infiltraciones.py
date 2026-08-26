# -*- coding: utf-8 -*-
"""Composición del PDF del registro de infiltraciones faciales — Espacio Corporal.

Carta VERTICAL sobre `pdf_comun.HojaCarta` (dec. 14), membrete repetido, una o
dos páginas y la firma escaneada al pie, igual que el informe (§4 del contrato
de la 2.1):

    generar_infiltraciones({"vista": "mujer-frontal", ...}, "salida.pdf")

QUÉ ES ESTE DOCUMENTO
---------------------
El registro de **qué se infiltró, dónde, con qué producto y en qué dosis**, en
una sesión de toxina botulínica, ácido hialurónico o mesoterapia. Es una
herramienta de **registro documental**: no sugiere, no recomienda y no calcula
dosis (regla 6 del contrato). Todo lo que sale impreso lo escribió el médico.

CÓMO SE DIBUJA LA LÁMINA (y por qué así)
----------------------------------------
La lámina anatómica se pega con `image()` y los marcadores se dibujan **encima,
con las primitivas vectoriales de fpdf2**. Nada de `canvas`, nada de
`window.print()`, nada de recibir una imagen ya compuesta desde el navegador:
el PDF se arma entero de este lado. Las razones son tres y son medibles:

1. Un `canvas` del navegador llega como PNG rasterizado a la resolución de la
   pantalla; impreso a 88 mm de ancho eso son unos 120 ppp y los números de los
   marcadores se empastan. Vectorial se imprime nítido a cualquier tamaño.
2. Un marcador vectorial pesa decenas de bytes; el PNG compuesto, cientos de
   kilobytes por documento, multiplicado por cada sesión de cada paciente.
3. Lo que se archiva tiene que salir del mismo lugar siempre. Si la imagen la
   compone el navegador, el PDF de la historia depende de qué versión del
   navegador tenía puesta la máquina el día que se emitió.

Los marcadores se distinguen **por número**, no solo por color: esto se imprime
en blanco y negro y se fotocopia, y ahí el color no existe. El color es la
ayuda; el número es el dato. Por eso también la tabla repite todo lo que dice
la lámina: si el marcador no se lee, la tabla manda.

QUÉ SE APOYA EN QUÉ
-------------------
* Las coordenadas de los puntos llegan **normalizadas 0–1 sobre la lámina**.
  La aritmética facial (origen interpupilar, unidad DIP, calibración de tres
  clics) vive en la interfaz; acá entra ya resuelta. Este módulo es puro: no
  toca la base, no lee configuración y no escribe nada más que el PDF pedido.
* La región de cada punto sale del `grupo` de `recursos/infiltraciones/plantillas.json`
  cuando el punto trae `plantillaId`, y si no, del texto de la `zona`. Lo que
  no encaja en ninguna región cae en «Otras», que es un cajón honesto: mejor
  una fila en «Otras» que una fila perdida.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

try:  # como paquete (``from app import pdf_infiltraciones``)
    from . import pdf_comun
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import pdf_comun  # type: ignore[no-redef]

# Atajos a lo compartido, tomados del módulo (no con `from ... import`) por la
# misma razón que en `pdf_informe`: `pdf_comun` se resuelve de dos formas según
# cómo se cargue la app.
ANCHO_UTIL_MM = pdf_comun.ANCHO_UTIL_MM
GUIA_DER_MM = pdf_comun.GUIA_DER_MM
MARGEN_IZQ_MM = pdf_comun.MARGEN_IZQ_MM
INTERLINEA_MM = pdf_comun.INTERLINEA_MM
CUERPO_Y1_MM = pdf_comun.CUERPO_Y1_MM
GRIS_DATO = pdf_comun.GRIS_DATO
GRIS_ROTULO = pdf_comun.GRIS_ROTULO
GRIS_RECUADRO = pdf_comun.GRIS_RECUADRO
TEAL_MEDIO = pdf_comun.TEAL_MEDIO
TEAL_OSCURO = pdf_comun.TEAL_OSCURO

TITULO = "Registro de infiltraciones"


# =============================================================================
# 1. LAMINAS
# =============================================================================

#: Dónde viven `base-mujer.jpg`, `base-hombre.jpg` y `plantillas.json`.
DIR_LAMINAS_DEFECTO = os.path.join(pdf_comun.raiz_recursos(), "recursos",
                                   "infiltraciones")

#: Las dos vistas frontales calibradas de fábrica. El identificador es el mismo
#: que guarda la columna `vista` de la tabla `infiltraciones` (§1 del contrato).
LAMINAS = {
    "mujer-frontal": "base-mujer.jpg",
    "hombre-frontal": "base-hombre.jpg",
}

ARCHIVO_PLANTILLAS = "plantillas.json"


# =============================================================================
# 2. REGIONES
# =============================================================================
# El orden es el del contrato (§4) y es anatómico, de arriba hacia abajo: el
# médico lee la tabla siguiendo la cara, no el orden en que fue pinchando.

ORDEN_REGIONES = ("frente", "glabela", "cejas", "periocular", "nariz", "medio",
                  "perioral", "inferior", "cuello", "otras")

ETIQUETA_REGION = {
    "frente": "Frente",
    "glabela": "Glabela",
    "cejas": "Cejas",
    "periocular": "Periocular",
    "nariz": "Nariz",
    "medio": "Tercio medio",
    "perioral": "Perioral",
    "inferior": "Tercio inferior",
    "cuello": "Cuello",
    "otras": "Otras",
}

REGION_OTRAS = "otras"

#: Zonas del catálogo de la interfaz, con su región. Es la misma tabla que usa
#: el mapa en pantalla: la tabla del PDF tiene que agrupar igual que la de la
#: pantalla, o el médico no reconoce lo que firmó. Los puntos de fábrica de
#: `plantillas.json` **pisan** lo que diga acá (ahí glabela y cejas son
#: regiones propias y no un subconjunto de la frente).
ZONAS_CATALOGO = {
    "frente": ("Frontal — línea alta", "Frontal — línea media medial",
               "Frontal — línea media lateral", "Frontal — línea baja", "Sien"),
    "glabela": ("Glabela — prócer", "Glabela — corrugador", "Nasion / radix"),
    "cejas": ("Cola de ceja — medial", "Cola de ceja — media",
              "Cola de ceja — lateral"),
    "periocular": ("Patas de gallo — haz superior", "Patas de gallo — haz medio",
                   "Patas de gallo — haz inferior",
                   "Párpado inferior — pretarsal", "Canto externo"),
    "nariz": ("Líneas de conejo (nasal transverso)", "Depresor del septo nasal",
              "Punta nasal", "Dorso nasal"),
    "medio": ("Elevador del labio superior y del ala de la nariz "
              "(sonrisa gingival)", "Pómulo / malar", "Surco nasogeniano",
              "Ojera / surco lagrimal", "Mejilla"),
    "perioral": ("Líneas peribucales (código de barras)", "Lip flip",
                 "Labio superior", "Labio inferior", "Comisura",
                 "Depresor del ángulo de la boca (DAO)"),
    "inferior": ("Mentoniano", "Mentón — proyección",
                 "Línea mandibular / prejowl", "Masetero"),
    "cuello": ("Bandas platismales — medial", "Bandas platismales — lateral",
               "Nefertiti", "Escote"),
}

#: Cuando la zona no está en el catálogo, se la clasifica por su **prefijo**:
#: lo que va antes de la raya larga o de la barra («Frontal — lo que sea» sigue
#: siendo frente aunque el médico haya escrito una variante propia).
PREFIJOS_REGION = (
    ("frontal", "frente"),
    ("sien", "frente"),
    ("glabela", "glabela"),
    ("nasion", "glabela"),
    ("entrecejo", "glabela"),
    ("cola de ceja", "cejas"),
    ("ceja", "cejas"),
    ("patas de gallo", "periocular"),
    ("párpado", "periocular"),
    ("parpado", "periocular"),
    ("canto externo", "periocular"),
    ("periocular", "periocular"),
    ("líneas de conejo", "nariz"),
    ("lineas de conejo", "nariz"),
    ("depresor del septo", "nariz"),
    ("punta nasal", "nariz"),
    ("dorso nasal", "nariz"),
    ("nasal", "nariz"),
    ("nariz", "nariz"),
    ("pómulo", "medio"),
    ("pomulo", "medio"),
    ("malar", "medio"),
    ("surco nasogeniano", "medio"),
    ("ojera", "medio"),
    ("mejilla", "medio"),
    ("líneas peribucales", "perioral"),
    ("lineas peribucales", "perioral"),
    ("lip flip", "perioral"),
    ("labio", "perioral"),
    ("comisura", "perioral"),
    ("depresor del ángulo", "perioral"),
    ("depresor del angulo", "perioral"),
    ("elevador del labio", "perioral"),
    ("perioral", "perioral"),
    ("mentoniano", "inferior"),
    ("mentón", "inferior"),
    ("menton", "inferior"),
    ("línea mandibular", "inferior"),
    ("linea mandibular", "inferior"),
    ("prejowl", "inferior"),
    ("masetero", "inferior"),
    ("mandíbula", "inferior"),
    ("mandibula", "inferior"),
    ("bandas platismales", "cuello"),
    ("nefertiti", "cuello"),
    ("escote", "cuello"),
    ("cuello", "cuello"),
    ("platisma", "cuello"),
)


# =============================================================================
# 3. MEDIDAS
# =============================================================================

PT_TITULO = 15.0
TITULO_BASE_Y_MM = 60.0
FECHA_BASE_Y_MM = 66.6
CUERPO_Y0_MM = 74.0              # primera línea de base debajo del título

PT_CUERPO = 11.0
PT_PIE = 9.5

# -- lámina -------------------------------------------------------------------
# Las dos láminas miden 896 x 1200 px, o sea 3:4 exacto. El ancho se eligió
# midiendo lo que queda para la tabla, que es lo que de verdad se lee:
#
#   cuerpo útil de la hoja  262,0 - 74,0                       = 188,0 mm
#   paciente + aire                                            =   7,0 mm
#   lámina a 88 mm de ancho -> 88 * 1200/896                   = 117,9 mm
#   leyenda de 2 productos + nota del lado                     =  13,6 mm
#   ------------------------------------------------------------------------
#   queda para la tabla en la PRIMERA hoja                     =  49,5 mm
#
# 49,5 mm son la cabecera de la tabla más unas nueve filas: una sesión corta
# entra entera en una carilla y una larga sigue en la segunda con la cabecera
# repetida. A 95 mm la lámina se come 9 mm más y la primera hoja se queda con
# seis filas; a 80 mm los marcadores caen a 3,2 mm de diámetro y el número de
# dos cifras deja de leerse. 88 mm es el punto donde las dos cosas todavía
# funcionan.
LAMINA_ANCHO_MM = 88.0
LAMINA_ALTO_MAX_MM = 124.0
LAMINA_AIRE_MM = 3.0

#: Radio del marcador. Con la calibración de fábrica la distancia interpupilar
#: cae en ~29,3 mm impresos, así que 1,75 mm de radio es un disco de 3,5 mm:
#: se ve de lejos, entra el número de dos cifras y todavía deja ver la lámina.
MARCADOR_RADIO_MM = 1.75
MARCADOR_BORDE_MM = 0.25         # halo claro, para que dos marcadores pegados
                                 # se sigan distinguiendo uno del otro
MARCADOR_HUECO_MM = 0.35         # trazo del círculo hueco (punto sin dosis)

#: Cuerpo del número según cuántas cifras tenga. Medido: «35» a 5,2 pt mide
#: 2,05 mm y el disco tiene 3,5 mm de diámetro.
PT_NUMERO = {1: 6.0, 2: 5.2, 3: 4.2}
#: De la línea de base a la mitad de la altura de las mayúsculas de la Lato.
#: (cap-height ~0,72 em; la mitad son 0,36 em, y un em son `pt * PT_A_MM` mm.)
NUMERO_CENTRADO = 0.36

# -- leyenda -------------------------------------------------------------------
PT_LEYENDA = 9.0
LEYENDA_INTERLINEA_MM = 4.6
LEYENDA_CUADRO_MM = 3.0
LEYENDA_AIRE_MM = 2.0
PT_NOTA = 7.8

# -- tabla ---------------------------------------------------------------------
PT_TABLA = 8.5
PT_TABLA_CABECERA = 8.5
TABLA_INTERLINEA_MM = 4.0
TABLA_PAD_MM = 1.4               # aire interno horizontal de cada celda
TABLA_ALTO_EXTRA_MM = 1.7        # aire vertical de la fila, arriba y abajo
TABLA_CABECERA_ALTO_MM = 6.0
TABLA_REGION_ALTO_MM = 5.6

#: `(rótulo, ancho en mm, alineación)`. Suman 175,9 = el ancho útil exacto.
COLUMNAS = (
    ("N.º", 9.5, "izq"),
    ("Lado", 11.0, "izq"),
    ("Zona", 60.0, "izq"),
    ("Producto", 38.0, "izq"),
    ("Dosis", 17.0, "der"),
    ("Notas", 40.4, "izq"),
)

CEBRA = (243, 246, 246)          # gris apenas más oscuro que el papel
BANDA_REGION = (228, 240, 238)   # teal muy lavado, el mismo aire que la marca
BANDA_TOTALES = (236, 243, 241)

TOTALES_PAD_MM = 2.0

FIRMA_ANCHO_MM = pdf_comun.FIRMA_ANCHO_MM
FIRMA_ALTO_MM = FIRMA_ANCHO_MM / pdf_comun.FIRMA_PROPORCION   # ~25,0 mm
FIRMA_AIRE_MM = 6.0

NOTA_LADO = ("Lado: I = hemifacial izquierdo del paciente · D = derecho · "
             "C = línea media. La lámina es una vista frontal, así que el lado "
             "izquierdo del paciente aparece a la derecha de la imagen.")


# =============================================================================
# 4. ERRORES
# =============================================================================

class InfiltracionesError(pdf_comun.DocumentoError):
    """Error al componer el PDF del registro de infiltraciones."""


class RecursoFaltanteError(pdf_comun.RecursoFaltanteError, InfiltracionesError):
    """Falta el logo, la firma, la lámina o alguna de las fuentes Lato."""


class VistaDesconocidaError(InfiltracionesError):
    """La `vista` pedida no es ninguna de las láminas calibradas."""

    def __init__(self, vista: Any):
        self.vista = vista
        disponibles = " o ".join(f"«{v}»" for v in sorted(LAMINAS))
        super().__init__(
            f"No existe la lámina «{vista}». Elegí {disponibles}: son las dos "
            "vistas frontales calibradas que trae la aplicación."
        )


# =============================================================================
# 5. AYUDAS
# =============================================================================

def _t(datos: Mapping[str, Any], clave: str, defecto: str = "") -> str:
    """Un campo del dict, ya recortado. Nunca `None`."""
    valor = datos.get(clave)
    if valor is None:
        return defecto
    texto = str(valor).strip()
    return texto if texto else defecto


def _dic(valor: Any) -> dict[str, Any]:
    """Un mapping cualquiera (dict, `sqlite3.Row`…) como dict de verdad."""
    if isinstance(valor, Mapping):
        return dict(valor)
    try:
        return dict(valor)
    except (TypeError, ValueError):
        return {}


def _numero(valor: Any) -> float | None:
    """Un número escrito a mano: acepta coma decimal y espacios. `None` si no."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(" ", "").replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def formatear_dosis(valor: float) -> str:
    """`2` · `0,5` · `12,25`. Sin ceros de relleno y con coma decimal."""
    redondeado = round(float(valor), 3)
    if abs(redondeado - round(redondeado)) < 1e-9:
        return str(int(round(redondeado)))
    texto = f"{redondeado:.3f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def color_desde_hex(valor: Any,
                    defecto: tuple[int, int, int] = GRIS_ROTULO
                    ) -> tuple[int, int, int]:
    """`#D92B2B` → `(217, 43, 43)`. Lo que no entiende cae en el gris."""
    texto = str(valor or "").strip().lstrip("#")
    if len(texto) == 3:
        texto = "".join(c * 2 for c in texto)
    if len(texto) != 6:
        return defecto
    try:
        return (int(texto[0:2], 16), int(texto[2:4], 16), int(texto[4:6], 16))
    except ValueError:
        return defecto


def luminancia_relativa(color: Sequence[int]) -> float:
    """Luminancia relativa WCAG 2.x de un color sRGB (0 = negro, 1 = blanco).

    La fórmula, tal cual la define WCAG:

        c   = canal / 255
        lin = c / 12,92                    si c <= 0,03928
        lin = ((c + 0,055) / 1,055) ^ 2,4  si no
        L   = 0,2126·R + 0,7152·G + 0,0722·B      (con los canales linealizados)

    Los tres pesos no son iguales porque el ojo no ve igual: el verde aporta
    casi tres cuartos del brillo percibido y el azul, apenas un catorceavo. Un
    azul saturado (#2456C4) y un naranja (#A85A0B) pueden tener el mismo
    promedio RGB y uno pedir número blanco y el otro negro.
    """
    canales = []
    for bruto in tuple(color)[:3]:
        c = max(0.0, min(255.0, float(bruto))) / 255.0
        canales.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    rojo, verde, azul = canales
    return 0.2126 * rojo + 0.7152 * verde + 0.0722 * azul


def tinta_sobre(color: Sequence[int]) -> tuple[int, int, int]:
    """Blanco o negro: el que más contraste da sobre `color`.

    Contraste WCAG = (L_claro + 0,05) / (L_oscuro + 0,05). Contra blanco da
    `1,05 / (L + 0,05)`; contra negro, `(L + 0,05) / 0,05`. Igualarlos despeja
    el umbral en L = √(1,05·0,05) − 0,05 ≈ 0,1791: por encima gana el negro.
    """
    umbral = (1.05 * 0.05) ** 0.5 - 0.05
    return (0, 0, 0) if luminancia_relativa(color) > umbral else (255, 255, 255)


# -----------------------------------------------------------------------------
# 5.1 Regiones
# -----------------------------------------------------------------------------

def _normalizar(texto: Any) -> str:
    return " ".join(str(texto or "").strip().lower().split())


_ZONA_A_REGION: dict[str, str] = {}
for _region, _zonas in ZONAS_CATALOGO.items():
    for _zona in _zonas:
        _ZONA_A_REGION[_normalizar(_zona)] = _region


def cargar_plantillas(dir_laminas: str) -> dict[str, Any]:
    """`plantillas.json` leído del disco. Un `{}` si no está o no se puede leer.

    No se rompe por esto a propósito: la región es una comodidad para agrupar
    la tabla, no un dato clínico. Sin el archivo, la zona escrita alcanza para
    clasificar cada punto y el documento sale igual.
    """
    ruta = os.path.join(dir_laminas, ARCHIVO_PLANTILLAS)
    if not os.path.isfile(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _indice_puntos(plantillas: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """`{id del punto de fábrica: su definición}` de `plantillas.json`."""
    indice: dict[str, dict[str, Any]] = {}
    for punto in plantillas.get("puntos") or ():
        if not isinstance(punto, Mapping):
            continue
        identificador = str(punto.get("id") or "").strip()
        if identificador:
            indice[identificador] = dict(punto)
    return indice


def region_de_zona(zona: Any) -> str:
    """Región de una zona escrita: exacta primero, por prefijo después."""
    clave = _normalizar(zona)
    if not clave:
        return REGION_OTRAS
    if clave in _ZONA_A_REGION:
        return _ZONA_A_REGION[clave]
    # El prefijo es lo que va antes de la raya larga o de la barra: «Frontal —
    # lo que el médico haya escrito» sigue siendo frente.
    prefijo = clave
    for separador in ("—", "-", "/", "("):
        prefijo = prefijo.split(separador)[0]
    prefijo = prefijo.strip()
    for arranque, region in PREFIJOS_REGION:
        if prefijo.startswith(arranque) or clave.startswith(arranque):
            return region
    return REGION_OTRAS


# =============================================================================
# 6. NORMALIZACION DE LOS DATOS
# =============================================================================
#
# `normalizar_productos` y `normalizar_puntos` son PUBLICAS a proposito. Las usa
# `pdf_historia`, que lista los registros de infiltraciones del paciente y tiene
# que dar los mismos totales que este modulo: resolver `productoId` -> producto y
# numerar los puntos es justamente lo que hay que hacer igual en los dos lados.
# Si se vuelven privadas otra vez, la historia empieza a recalcular por su cuenta
# y las dos cifras se separan el dia que una de las dos cambie.

def normalizar_productos(brutos: Any) -> tuple[list[dict[str, Any]],
                                                dict[str, dict[str, Any]]]:
    """Lista de productos lista para imprimir + índice por `id`."""
    productos: list[dict[str, Any]] = []
    indice: dict[str, dict[str, Any]] = {}
    for orden, bruto in enumerate(brutos or (), start=1):
        crudo = _dic(bruto)
        if not crudo:
            continue
        identificador = str(crudo.get("id") or "").strip() or f"__p{orden}"
        producto = {
            "id": identificador,
            "nombre": _t(crudo, "nombre") or f"Producto {orden}",
            "unidad": _t(crudo, "unidad"),
            "lote": _t(crudo, "lote"),
            "caducidad": _t(crudo, "caducidad"),
            "color": color_desde_hex(crudo.get("color"), TEAL_MEDIO),
        }
        productos.append(producto)
        indice[identificador] = producto
    return productos, indice


def normalizar_puntos(brutos: Any, indice_productos: Mapping[str, Any],
                       indice_plantillas: Mapping[str, Any]
                       ) -> list[dict[str, Any]]:
    """Puntos ordenados y numerados 1..N, con su región y su producto resueltos.

    El número que se numera acá es el que va **adentro del marcador y en la
    columna N.º de la tabla**: son el mismo número a propósito, es lo único que
    ata el dibujo con el renglón cuando el documento está fotocopiado en gris.
    """
    crudos: list[tuple[float, int, dict[str, Any]]] = []
    for posicion, bruto in enumerate(brutos or ()):
        crudo = _dic(bruto)
        if not crudo:
            continue
        orden = _numero(crudo.get("orden"))
        crudos.append((orden if orden is not None else float(posicion + 1),
                       posicion, crudo))
    crudos.sort(key=lambda t: (t[0], t[1]))

    puntos: list[dict[str, Any]] = []
    for numero, (_, _, crudo) in enumerate(crudos, start=1):
        plantilla = indice_plantillas.get(str(crudo.get("plantillaId") or "").strip())
        zona = _t(crudo, "zona") or (_t(plantilla, "zona") if plantilla else "")
        lado = _t(crudo, "lado") or (_t(plantilla, "lado") if plantilla else "")
        if plantilla and _t(plantilla, "grupo"):
            region = _t(plantilla, "grupo")
        else:
            region = region_de_zona(zona)
        if region not in ETIQUETA_REGION:
            region = REGION_OTRAS

        producto = indice_productos.get(str(crudo.get("productoId") or "").strip())
        dosis = _numero(crudo.get("dosis"))
        if dosis is not None and dosis <= 0:
            dosis = None
        # Sin producto no hay dosis que anotar: el marcador queda hueco y la
        # fila dice «—». Es un punto registrado, no un punto infiltrado.
        if producto is None:
            dosis = None

        puntos.append({
            "numero": numero,
            "x": max(0.0, min(1.0, _numero(crudo.get("x")) or 0.0)),
            "y": max(0.0, min(1.0, _numero(crudo.get("y")) or 0.0)),
            "lado": lado,
            "zona": zona,
            "region": region,
            "producto": producto,
            "dosis": dosis,
            "notas": _t(crudo, "notas"),
        })
    return puntos


def agrupar_por_region(puntos: Sequence[Mapping[str, Any]]
                       ) -> list[tuple[str, list[Mapping[str, Any]]]]:
    """`[(región, sus puntos)]` en el orden anatómico del contrato."""
    cajones: dict[str, list[Mapping[str, Any]]] = {}
    for punto in puntos:
        cajones.setdefault(str(punto.get("region") or REGION_OTRAS), []).append(punto)
    grupos = [(region, cajones[region]) for region in ORDEN_REGIONES
              if region in cajones]
    # Cualquier región que no esté en el orden (no debería pasar: se normaliza
    # arriba) se agrega al final antes que perderla.
    grupos.extend((region, filas) for region, filas in cajones.items()
                  if region not in ETIQUETA_REGION)
    return grupos


def totales_por_producto(puntos: Sequence[Mapping[str, Any]]
                         ) -> list[dict[str, Any]]:
    """Suma de dosis y cantidad de puntos por producto, en orden de aparición."""
    acumulado: dict[str, dict[str, Any]] = {}
    for punto in puntos:
        producto = punto.get("producto")
        dosis = punto.get("dosis")
        if not producto or dosis is None:
            continue
        clave = str(producto["id"])
        fila = acumulado.setdefault(clave, {"producto": producto,
                                            "dosis": 0.0, "puntos": 0})
        fila["dosis"] += float(dosis)
        fila["puntos"] += 1
    return list(acumulado.values())


def _resumen_dosis(puntos: Iterable[Mapping[str, Any]]) -> str:
    """«12 U · 1,5 ml» — el subtotal de una región, por unidad de producto."""
    orden: list[str] = []
    suma: dict[str, float] = {}
    for punto in puntos:
        producto = punto.get("producto")
        dosis = punto.get("dosis")
        if not producto or dosis is None:
            continue
        unidad = str(producto.get("unidad") or "").strip()
        if unidad not in suma:
            orden.append(unidad)
            suma[unidad] = 0.0
        suma[unidad] += float(dosis)
    partes = []
    for unidad in orden:
        texto = formatear_dosis(suma[unidad])
        partes.append(f"{texto} {unidad}".strip())
    return " · ".join(partes)


def _plural_puntos(cantidad: int) -> str:
    return "1 punto" if cantidad == 1 else f"{cantidad} puntos"


# =============================================================================
# 7. COMPOSITOR
# =============================================================================

class _Infiltraciones(pdf_comun.HojaCarta):
    """Lienzo del registro. La API pública es `generar_infiltraciones`."""

    _ERROR_RECURSO = RecursoFaltanteError

    def __init__(self, ruta_logo: str, dir_fuentes: str, ruta_firma: str,
                 codigo: str = "") -> None:
        super().__init__(ruta_logo, dir_fuentes, codigo)
        self.ruta_firma = ruta_firma

    # ------------------------------------------------------------ encabezado
    def abrir(self, fecha: Any) -> None:
        """Primera página: membrete, título y la fecha en letra."""
        self.nueva_pagina()
        self._texto_centrado(MARGEN_IZQ_MM, GUIA_DER_MM, TITULO_BASE_Y_MM,
                             TITULO, "B", PT_TITULO, TEAL_OSCURO)
        larga = pdf_comun.fecha_larga(fecha)
        if larga:
            self._texto_centrado(MARGEN_IZQ_MM, GUIA_DER_MM, FECHA_BASE_Y_MM,
                                 larga, "", PT_PIE, GRIS_ROTULO)
        self.pluma_y = CUERPO_Y0_MM

    # ---------------------------------------------------------------- lámina
    def lamina(self, ruta: str, puntos: Sequence[Mapping[str, Any]]) -> None:
        """Pega la lámina centrada y le dibuja los marcadores encima.

        Dos pasadas a propósito: primero **todos** los discos y después
        **todos** los números. En la cola de la ceja hay puntos de fábrica a
        1,7 mm uno del otro y sus discos de 3,5 mm se solapan; dibujando en dos
        pasadas, ningún número queda tapado por el disco del vecino.
        """
        ancho_px, alto_px = pdf_comun.medidas_imagen(ruta)
        ancho, alto = pdf_comun.encajar(ancho_px, alto_px, LAMINA_ANCHO_MM,
                                        LAMINA_ALTO_MAX_MM)
        self.asegurar(alto + LAMINA_AIRE_MM)
        x0 = MARGEN_IZQ_MM + (ANCHO_UTIL_MM - ancho) / 2.0
        y0 = self.pluma_y - INTERLINEA_MM * 0.8
        self.image(ruta, x=x0, y=y0, w=ancho, h=alto)

        # Coordenadas normalizadas 0-1 sobre la lámina -> milímetros de la hoja.
        posiciones = [(x0 + float(p["x"]) * ancho, y0 + float(p["y"]) * alto)
                      for p in puntos]

        for punto, (cx, cy) in zip(puntos, posiciones):
            self._disco(cx, cy, punto)
        for punto, (cx, cy) in zip(puntos, posiciones):
            self._numero_marcador(cx, cy, punto)

        self.pluma_y = y0 + alto + LAMINA_AIRE_MM

    def _disco(self, cx: float, cy: float, punto: Mapping[str, Any]) -> None:
        """El círculo del marcador: relleno si se infiltró, hueco si no."""
        radio = MARCADOR_RADIO_MM
        producto = punto.get("producto")
        if producto is None or punto.get("dosis") is None:
            # Punto marcado y no infiltrado (dosis 0, vacía o sin producto):
            # queda registrado, pero no puede parecer una aplicación.
            self.set_draw_color(*GRIS_ROTULO)
            self.set_line_width(MARCADOR_HUECO_MM)
            self.ellipse(cx - radio, cy - radio, radio * 2, radio * 2, style="D")
            return
        self.set_fill_color(*producto["color"])
        self.set_draw_color(255, 255, 255)
        self.set_line_width(MARCADOR_BORDE_MM)
        self.ellipse(cx - radio, cy - radio, radio * 2, radio * 2, style="DF")

    def _numero_marcador(self, cx: float, cy: float,
                         punto: Mapping[str, Any]) -> None:
        texto = str(punto["numero"])
        pt = PT_NUMERO.get(len(texto), PT_NUMERO[3])
        producto = punto.get("producto")
        if producto is None or punto.get("dosis") is None:
            tinta = GRIS_DATO
        else:
            tinta = tinta_sobre(producto["color"])
        base_y = cy + NUMERO_CENTRADO * pt * pdf_comun.PT_A_MM
        self._texto_centrado(cx - MARCADOR_RADIO_MM, cx + MARCADOR_RADIO_MM,
                             base_y, texto, "B", pt, tinta)

    # --------------------------------------------------------------- leyenda
    def leyenda(self, productos: Sequence[Mapping[str, Any]]) -> None:
        """Cuadradito de color · nombre · unidad · lote."""
        if not productos:
            return
        self.espacio(LEYENDA_AIRE_MM)
        for producto in productos:
            self.asegurar(LEYENDA_INTERLINEA_MM)
            y = self.pluma_y
            self.set_fill_color(*producto["color"])
            self.set_draw_color(*GRIS_RECUADRO)
            self.set_line_width(pdf_comun.GROSOR_RECUADRO_MM)
            self.rect(MARGEN_IZQ_MM, y - LEYENDA_CUADRO_MM + 0.4,
                      LEYENDA_CUADRO_MM, LEYENDA_CUADRO_MM, style="DF")
            partes = [producto["nombre"]]
            if producto["unidad"]:
                partes.append(producto["unidad"])
            if producto["lote"]:
                partes.append(f"lote {producto['lote']}")
            self._texto(MARGEN_IZQ_MM + LEYENDA_CUADRO_MM + 2.0, y,
                        " · ".join(partes), "", PT_LEYENDA, GRIS_DATO)
            self.pluma_y += LEYENDA_INTERLINEA_MM

    def nota(self, texto: str) -> None:
        """Letra chica gris al pie de la leyenda."""
        for renglon in self._envolver(texto, ANCHO_UTIL_MM, "I", PT_NOTA):
            self.asegurar(3.6)
            self._texto(MARGEN_IZQ_MM, self.pluma_y, renglon, "I", PT_NOTA,
                        GRIS_ROTULO)
            self.pluma_y += 3.6

    # ----------------------------------------------------------------- tabla
    def _x_columnas(self) -> list[float]:
        equis = [MARGEN_IZQ_MM]
        for _, ancho, _ in COLUMNAS:
            equis.append(equis[-1] + ancho)
        return equis

    def _celdas_fila(self, punto: Mapping[str, Any]) -> list[str]:
        producto = punto.get("producto")
        dosis = punto.get("dosis")
        if producto is None:
            texto_producto = "—"
        else:
            texto_producto = str(producto["nombre"])
        if dosis is None:
            texto_dosis = "—"
        else:
            unidad = str(producto.get("unidad") or "").strip() if producto else ""
            texto_dosis = f"{formatear_dosis(dosis)} {unidad}".strip()
        return [
            str(punto["numero"]),
            str(punto.get("lado") or "—"),
            str(punto.get("zona") or "—"),
            texto_producto,
            texto_dosis,
            str(punto.get("notas") or ""),
        ]

    def _renglones_fila(self, celdas: Sequence[str]) -> list[list[str]]:
        partidas = []
        for texto, (_, ancho, _) in zip(celdas, COLUMNAS):
            partidas.append(self._envolver(texto, ancho - 2 * TABLA_PAD_MM,
                                           "", PT_TABLA) or [""])
        return partidas

    def _alto_fila(self, partidas: Sequence[Sequence[str]]) -> float:
        renglones = max((len(p) for p in partidas), default=1)
        return renglones * TABLA_INTERLINEA_MM + TABLA_ALTO_EXTRA_MM

    def cabecera_tabla(self) -> None:
        """Los rótulos de las columnas y el filete teal de abajo."""
        y0 = self.pluma_y - INTERLINEA_MM * 0.8
        equis = self._x_columnas()
        base = y0 + TABLA_CABECERA_ALTO_MM - 1.9
        for i, (rotulo, ancho, alineacion) in enumerate(COLUMNAS):
            if alineacion == "der":
                self._texto_der(equis[i] + ancho - TABLA_PAD_MM, base, rotulo,
                                "B", PT_TABLA_CABECERA, TEAL_OSCURO)
            else:
                self._texto(equis[i] + TABLA_PAD_MM, base, rotulo, "B",
                            PT_TABLA_CABECERA, TEAL_OSCURO)
        self._raya(MARGEN_IZQ_MM, GUIA_DER_MM, y0 + TABLA_CABECERA_ALTO_MM,
                   0.35, TEAL_MEDIO)
        self.pluma_y = y0 + TABLA_CABECERA_ALTO_MM + INTERLINEA_MM * 0.8 + 0.6

    def _banda(self, alto: float, color: tuple[int, int, int]) -> float:
        """Pinta el fondo de una fila y devuelve su borde superior."""
        y0 = self.pluma_y - INTERLINEA_MM * 0.8
        self.set_fill_color(*color)
        self.rect(MARGEN_IZQ_MM, y0, ANCHO_UTIL_MM, alto, style="F")
        return y0

    def fila_region(self, region: str, puntos: Sequence[Mapping[str, Any]]) -> None:
        """Cabecera de región con su subtotal, en banda teal lavado."""
        y0 = self._banda(TABLA_REGION_ALTO_MM, BANDA_REGION)
        base = y0 + TABLA_REGION_ALTO_MM - 1.8
        etiqueta = ETIQUETA_REGION.get(region, ETIQUETA_REGION[REGION_OTRAS])
        self._texto(MARGEN_IZQ_MM + TABLA_PAD_MM, base, etiqueta, "B", PT_TABLA,
                    TEAL_OSCURO)
        resumen = _resumen_dosis(puntos)
        derecha = _plural_puntos(len(puntos))
        if resumen:
            derecha = f"{derecha} · {resumen}"
        self._texto_der(GUIA_DER_MM - TABLA_PAD_MM, base, derecha, "B",
                        PT_TABLA, TEAL_MEDIO)
        self.pluma_y = y0 + TABLA_REGION_ALTO_MM + INTERLINEA_MM * 0.8

    def fila_punto(self, punto: Mapping[str, Any], partidas: Sequence[Sequence[str]],
                   alto: float, cebrada: bool) -> None:
        y0 = self._banda(alto, CEBRA) if cebrada else self.pluma_y - INTERLINEA_MM * 0.8
        equis = self._x_columnas()
        for i, (renglones, (_, ancho, alineacion)) in enumerate(
                zip(partidas, COLUMNAS)):
            y = y0 + TABLA_ALTO_EXTRA_MM * 0.5 + TABLA_INTERLINEA_MM - 1.0
            for renglon in renglones:
                if alineacion == "der":
                    self._texto_der(equis[i] + ancho - TABLA_PAD_MM, y, renglon,
                                    "", PT_TABLA, GRIS_DATO)
                else:
                    self._texto(equis[i] + TABLA_PAD_MM, y, renglon, "",
                                PT_TABLA, GRIS_DATO)
                y += TABLA_INTERLINEA_MM
        self.pluma_y = y0 + alto + INTERLINEA_MM * 0.8

    def tabla(self, puntos: Sequence[Mapping[str, Any]]) -> None:
        """La tabla entera, agrupada por región y **sin partir ninguna fila**.

        Una fila partida entre dos hojas en un registro de dosis es una
        invitación a leer mal: la dosis de arriba con la zona de abajo. Antes
        que eso se salta de página y se repite la cabecera de columnas.
        """
        grupos = agrupar_por_region(puntos)
        if not grupos:
            return
        self.asegurar(TABLA_CABECERA_ALTO_MM + TABLA_REGION_ALTO_MM
                      + TABLA_INTERLINEA_MM * 2)
        self.cabecera_tabla()

        cebrada = False
        for region, filas in grupos:
            preparadas = []
            for punto in filas:
                partidas = self._renglones_fila(self._celdas_fila(punto))
                preparadas.append((punto, partidas, self._alto_fila(partidas)))
            # La cabecera de la región viaja pegada a su primera fila: un
            # rótulo de región solo al pie de la hoja no dice nada.
            reserva = TABLA_REGION_ALTO_MM + (preparadas[0][2] if preparadas else 0.0)
            if self.pluma_y + reserva > CUERPO_Y1_MM:
                self.nueva_pagina()
                self.cabecera_tabla()
                cebrada = False
            self.fila_region(region, filas)
            for punto, partidas, alto in preparadas:
                if self.pluma_y + alto > CUERPO_Y1_MM:
                    self.nueva_pagina()
                    self.cabecera_tabla()
                    cebrada = False
                self.fila_punto(punto, partidas, alto, cebrada)
                cebrada = not cebrada

    def totales(self, filas: Sequence[Mapping[str, Any]]) -> None:
        """El bloque destacado del pie de la tabla: cuánto entró de cada cosa."""
        if not filas:
            return
        alto = (TOTALES_PAD_MM * 2 + TABLA_INTERLINEA_MM
                + len(filas) * TABLA_INTERLINEA_MM)
        self.espacio(INTERLINEA_MM * 0.4)
        self.asegurar(alto)
        y0 = self.pluma_y - INTERLINEA_MM * 0.8
        self.set_fill_color(*BANDA_TOTALES)
        self.rect(MARGEN_IZQ_MM, y0, ANCHO_UTIL_MM, alto, style="F")
        self._recuadro(MARGEN_IZQ_MM, y0, GUIA_DER_MM, y0 + alto, 0.25,
                       TEAL_MEDIO)

        y = y0 + TOTALES_PAD_MM + TABLA_INTERLINEA_MM - 0.8
        self._texto(MARGEN_IZQ_MM + TABLA_PAD_MM, y, "Totales por producto",
                    "B", PT_TABLA, TEAL_OSCURO)
        y += TABLA_INTERLINEA_MM
        for fila in filas:
            producto = fila["producto"]
            unidad = str(producto.get("unidad") or "").strip()
            self._texto(MARGEN_IZQ_MM + TABLA_PAD_MM, y, producto["nombre"],
                        "", PT_TABLA, GRIS_DATO)
            total = f"{formatear_dosis(fila['dosis'])} {unidad}".strip()
            self._texto_der(GUIA_DER_MM - TABLA_PAD_MM, y,
                            f"{total} en {_plural_puntos(fila['puntos'])}",
                            "B", PT_TABLA, TEAL_OSCURO)
            y += TABLA_INTERLINEA_MM
        self.pluma_y = y0 + alto + INTERLINEA_MM * 0.8

    # ----------------------------------------------------------------- firma
    def firma(self) -> None:
        """La firma escaneada, igual que en el informe (dec. 9).

        La imagen ya trae el nombre, el R.I.F., el M.P.P.S. y el COMEZU debajo
        del trazo: no se vuelven a escribir.
        """
        if not os.path.isfile(self.ruta_firma):
            raise RecursoFaltanteError(
                "Falta la firma escaneada del médico, así que el registro "
                "saldría sin firmar. Esperada en: " + str(self.ruta_firma)
            )
        self.asegurar(FIRMA_AIRE_MM + FIRMA_ALTO_MM)
        self.pluma_y += FIRMA_AIRE_MM
        self.image(self.ruta_firma, x=MARGEN_IZQ_MM, y=self.pluma_y,
                   w=FIRMA_ANCHO_MM, h=FIRMA_ALTO_MM)
        self.pluma_y += FIRMA_ALTO_MM


# =============================================================================
# 8. API PUBLICA
# =============================================================================

def normalizar_vista(vista: Any) -> str:
    """`mujer-frontal` o `hombre-frontal`. Vacío cae en la lámina de mujer."""
    texto = _normalizar(vista).replace(" ", "-")
    if not texto:
        return "mujer-frontal"
    if texto not in LAMINAS:
        raise VistaDesconocidaError(vista)
    return texto


def ruta_lamina(vista: Any, dir_laminas: str = DIR_LAMINAS_DEFECTO) -> str:
    """Ruta en disco de la lámina de esa vista. Levanta si no existe."""
    nombre = LAMINAS[normalizar_vista(vista)]
    ruta = os.path.join(dir_laminas, nombre)
    if not os.path.isfile(ruta):
        raise RecursoFaltanteError(
            f"Falta la lámina anatómica «{nombre}». Esperada en: {ruta}"
        )
    return ruta


def generar_infiltraciones(datos: Mapping[str, Any], ruta_salida: str, *,
                           ruta_logo: str = pdf_comun.RUTA_LOGO_DEFECTO,
                           dir_fuentes: str = pdf_comun.DIR_FUENTES_DEFECTO,
                           dir_laminas: str = DIR_LAMINAS_DEFECTO,
                           ruta_firma: str = pdf_comun.RUTA_FIRMA_DEFECTO) -> str:
    """Escribe el PDF del registro de infiltraciones y devuelve la ruta.

    `datos` es un dict plano — el módulo NO consulta la base de datos (§4):

        codigo           'EC-0001'   el del PACIENTE, arriba a la derecha
        fecha            '2026-08-26' | '26/08/2026' | date; si falta, hoy
        paciente_nombre  str
        paciente_edad    str         puede venir vacía
        vista            'mujer-frontal' | 'hombre-frontal'
        productos        list  {id, nombre, tipo, unidad, color, lote, caducidad}
        puntos           list  {orden, x, y, lado, zona, plantillaId,
                                productoId, dosis, notas}
                               `x` e `y` son normalizadas 0-1 sobre la lámina
        observaciones    str

    Levanta `VistaDesconocidaError` y `RecursoFaltanteError`. **No** levanta por
    cantidad de puntos: una sesión larga se lleva una segunda hoja, que es
    legítimo (el récipe frena porque su talonario tiene una sola carilla).
    """
    vista = normalizar_vista(datos.get("vista"))
    if not os.path.isfile(ruta_logo):
        raise RecursoFaltanteError(f"Falta el logo. Esperado en: {ruta_logo}")
    lamina = ruta_lamina(vista, dir_laminas)

    plantillas = cargar_plantillas(dir_laminas)
    indice_plantillas = _indice_puntos(plantillas)
    productos, indice_productos = normalizar_productos(datos.get("productos"))
    puntos = normalizar_puntos(datos.get("puntos"), indice_productos,
                                indice_plantillas)

    fecha = datos.get("fecha")
    if not str(fecha or "").strip():
        fecha = date.today().isoformat()

    doc = _Infiltraciones(ruta_logo, dir_fuentes, ruta_firma, _t(datos, "codigo"))
    doc.abrir(fecha)

    nombre = _t(datos, "paciente_nombre")
    edad = _t(datos, "paciente_edad")
    if nombre or edad:
        linea = nombre
        if edad:
            linea = f"{nombre} — {edad} años" if nombre else f"{edad} años"
        doc.campo("Paciente:", linea)
        doc.espacio(INTERLINEA_MM * 0.4)

    doc.lamina(lamina, puntos)
    doc.leyenda(productos)
    doc.nota(NOTA_LADO)
    doc.espacio(INTERLINEA_MM * 0.6)
    doc.tabla(puntos)
    doc.totales(totales_por_producto(puntos))

    observaciones = _t(datos, "observaciones")
    if observaciones:
        doc.espacio(INTERLINEA_MM * 0.6)
        doc.rotulo("Observaciones")
        doc.parrafo(observaciones)

    doc.espacio(INTERLINEA_MM * 0.6)
    doc.firma()
    doc.numerar_paginas()

    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    doc.output(ruta_salida)
    return ruta_salida


# =============================================================================
# 9. PRUEBA
# =============================================================================

if __name__ == "__main__":  # pragma: no cover
    RAIZ = pdf_comun._RAIZ

    # Sesión realista: tercio superior con toxina, contorno mandibular con
    # ácido hialurónico y un punto marcado que NO se infiltró. Las x/y salen de
    # los puntos de fábrica de `plantillas.json` pasados por la calibración de
    # la lámina de mujer, que es lo que hace la interfaz.
    PRODUCTOS = [
        {"id": "p1", "nombre": "Toxina A — marca 1", "tipo": "toxina",
         "unidad": "U", "color": "#D92B2B", "lote": "TX-7741", "caducidad": ""},
        {"id": "p3", "nombre": "AH baja densidad", "tipo": "relleno",
         "unidad": "ml", "color": "#2456C4", "lote": "AH-2210", "caducidad": ""},
    ]
    PUNTOS = [
        (1, 0.6351, 0.2109, "I", "Frontal — línea alta", "frontal-alto-i", "p1", 2, ""),
        (2, 0.3689, 0.2077, "D", "Frontal — línea alta", "frontal-alto-d", "p1", 2, ""),
        (3, 0.5845, 0.2425, "I", "Frontal — línea media medial", "frontal-med-med-i", "p1", 2, ""),
        (4, 0.4181, 0.2406, "D", "Frontal — línea media medial", "frontal-med-med-d", "p1", 2, ""),
        (5, 0.4986, 0.3681, "C", "Glabela — prócer", "procer", "p1", 4, "intramuscular"),
        (6, 0.5848, 0.3517, "I", "Glabela — corrugador", "corrugador-i", "p1", 4, ""),
        (7, 0.4132, 0.3497, "D", "Glabela — corrugador", "corrugador-d", "p1", 4, ""),
        (8, 0.7712, 0.4319, "I", "Patas de gallo — haz medio", "patas-med-i", "p1", 3, ""),
        (9, 0.2236, 0.4254, "D", "Patas de gallo — haz medio", "patas-med-d", "p1", 3, ""),
        (10, 0.7596, 0.4590, "I", "Patas de gallo — haz inferior", "patas-inf-i", "p1", 2, "intradérmico"),
        (11, 0.2340, 0.4529, "D", "Patas de gallo — haz inferior", "patas-inf-d", "p1", 2, "intradérmico"),
        (12, 0.6264, 0.7980, "I", "Línea mandibular / prejowl", "prejowl-i", "p3", 0.4, "cánula 25G"),
        (13, 0.3529, 0.7948, "D", "Línea mandibular / prejowl", "prejowl-d", "p3", 0.4, "cánula 25G"),
        (14, 0.5453, 0.7921, "I", "Mentoniano", "mentoniano-i", "", "", "marcado, no se infiltró"),
    ]
    EJEMPLO = {
        "codigo": "EC-0001",
        "fecha": "2026-08-26",
        "paciente_nombre": "María Fernanda Rodríguez Blanco",
        "paciente_edad": "38",
        "vista": "mujer-frontal",
        "productos": PRODUCTOS,
        "puntos": [
            {"orden": orden, "x": x, "y": y, "lado": lado, "zona": zona,
             "plantillaId": plantilla, "productoId": producto, "dosis": dosis,
             "notas": notas}
            for orden, x, y, lado, zona, plantilla, producto, dosis, notas in PUNTOS
        ],
        "observaciones": ("Se reserva el retoque de la cola de ceja para el "
                          "control de los quince días. La paciente refiere "
                          "buena tolerancia al procedimiento."),
    }
    print(generar_infiltraciones(
        EJEMPLO, os.path.join(RAIZ, "build", "infiltraciones_prueba.pdf")))
