# -*- coding: utf-8 -*-
"""Composicion del PDF del recipe medico — Espacio Corporal.

Calca el talonario preimpreso: UNA pagina carta apaisada (279,4 x 215,9 mm)
con dos mitades de media carta vertical (139,7 x 215,9 mm) separadas por la
linea de corte punteada. Mitad izquierda = `Rp.` (medicamentos), mitad
derecha = `Ind.` (indicaciones).

Todas las medidas salen de `build/analisis-modelo.md` (Parte A, medidas
verificadas de nuevo sobre el escaneo renderizado a 200 dpi) y los colores de
la Parte B (`referencias/Logo.jpg`, que es el archivo digital limpio).

El modulo es puro: no toca la base de datos, no lee configuracion, no escribe
nada mas que el PDF pedido.

    from app.pdf_recipe import (generar_recipe, medir_contenido,
                                ContenidoNoCabeError, NombreNoCabeError)

Decisiones del medico que este modulo obedece (no las discutas en codigo):
  1. Los renglones Dr.:/CI:/MPPS: van EN BLANCO (los llena un sello).
  2. Una sola pagina carta apaisada con las dos mitades y la linea de corte.
  3. Sin firma impresa.        4. Sin cedula ni edad del paciente.
  5. La mitad Ind. lleva las indicaciones por medicamento + un bloque libre.
  6. Sin vigencia.             8. El diagnostico NO se imprime.
  7. El codigo unico va arriba a la derecha de CADA mitad.
  9. El ornamento lateral es vectorial (Bezier + degradado), espejado.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping, Sequence

from fpdf import FPDF
from fpdf.drawing import GradientPaint, shape_linear_gradient

# =============================================================================
# 1. GEOMETRIA DE LA HOJA
# =============================================================================

PAGINA_ANCHO_MM = 279.4          # carta apaisada = 11 in
PAGINA_ALTO_MM = 215.9           # 8,5 in
MITAD_ANCHO_MM = 139.7           # media carta vertical = 5,5 in
LINEA_CORTE_X_MM = 139.70        # medida: 49,96 % del ancho del escaneo

# Guias comunes a las dos mitades (coordenadas LOCALES de cada media carta,
# origen en su esquina superior izquierda).
MARGEN_IZQ_MM = 16.4             # encabezado y cuerpo
GUIA_DER_MM = 126.4              # donde mueren las rayas, el cuerpo libre y el
                                 # codigo "N.º" (unica excepcion: la raya de la
                                 # fecha de la mitad Ind. — ver PIE_IND en §7)
MARGEN_SUP_MM = 16.0

# =============================================================================
# 2. COLORES  (Parte B del analisis — medidos sobre Logo.jpg, no sobre el escaneo)
# =============================================================================

VERDE_LIMA = (154, 190, 15)      # #9ABE0F  simbolo, CORPORAL, arranque del ornamento
TEAL_MEDIO = (21, 127, 111)      # #157F6F  script "espacio", filete y pie del ornamento
TEAL_OSCURO = (18, 85, 80)       # #125550  "Salud y Bienestar", "Rp.", "Ind."
GRIS_ROTULO = (74, 83, 84)       # #4A5354  Dr./CI/MPPS/Paciente/Fecha, rayas, "N.º"
GRIS_DATO = (51, 58, 59)         # #333A3B  texto que escribe la app (algo mas oscuro)
GRIS_CORTE = (201, 201, 201)     # #C9C9C9  linea de corte punteada

VERDE_LIMA_HEX = "#9ABE0F"
TEAL_MEDIO_HEX = "#157F6F"

# =============================================================================
# 3. TIPOGRAFIA  (Lato embebida; cap height de Lato = 0,7165 em)
# =============================================================================

FUENTE = "Lato"
_ARCHIVOS_FUENTE = {
    "": "Lato-Regular.ttf",
    "B": "Lato-Bold.ttf",
    "I": "Lato-Italic.ttf",
    "BI": "Lato-BoldItalic.ttf",
}

PT_SALUD = 12.0                  # "Salud y Bienestar" — se tracking-ea hasta 32,6 mm.
                                 # A 11 pt el ancho total daba bien pero las letras
                                 # salian chicas y el deficit se tapaba abriendo el
                                 # tracking: altura de mayuscula 2,78 mm contra los
                                 # 3,10 mm medidos sobre la "S" y la "B" del modelo.
                                 # A 12 pt la cap da 3,03 mm (12 x 0,352778 x 0,7165),
                                 # dentro del 3 %, y el char_spacing extra baja.
PT_RP = 20.0                     # "Rp." / "Ind." bold italic
                                 # (a 20 pt la "I" de "Ind." mide 5,10 mm de alto,
                                 #  que es lo medido en el modelo; a 18 pt daba 4,60)
PT_ROTULO = 12.5                 # Dr.: CI: MPPS: Paciente: Fecha:
PT_CODIGO_ROTULO = 11.0          # "N.º"
PT_CODIGO = 13.0                 # EC-2026-0001, bold
PT_DATO = 12.0                   # nombre del paciente y fecha sobre las rayas
PT_DATO_COMODO = 11.0            # piso hasta donde se achica ANTES de abreviar:
                                 # a 11 pt la mayuscula del nombre da 2,78 mm
                                 # contra los 3,20 mm del rotulo "Paciente:" que
                                 # tiene al lado, y todavia se lee parejo
PT_DATO_MIN = 9.5                # piso legible absoluto
PT_CUERPO = 11.5                 # renglon de medicamento / indicacion
PT_CUERPO_MENOR = 11.0           # dosis, cantidad, texto general

INTERLINEA_MM = 5.0              # entre renglones de un mismo item
SEPARACION_ITEM_MM = 3.4         # aire extra entre items numerados
SANGRIA_MM = 6.2                 # ancho reservado para "1." "2." ...
SEPARACION_GENERAL_MM = 7.0      # aire antes del bloque de texto libre en Ind.

# =============================================================================
# 4. BLOQUE DEL LOGO Y ENCABEZADO
# =============================================================================
# DECISION EXPLICITA — las dos mitades NO son identicas: se calca el escaneo.
#
# El §0 del analisis sugiere usar siempre las medidas de la mitad Rp. porque
# esta menos deformada, pero el escaneo muestra la mitad Ind. corrida 1,4-2,2 mm
# a la derecha de forma consistente (logo, bajada, rotulo y renglon del pie), y
# eso NO es compresion de la foto: el lockup del logo mide 21,7 mm en la mitad
# Rp. y 21,6 mm en la Ind. (0,5 % de diferencia), o sea que la escala horizontal
# es la misma en las dos y lo que cambia es la posicion. Ademas el pie ya venia
# siguiendo la geometria propia de la mitad Ind. (PIE_IND != PIE_RP): dejar el
# encabezado atado a la mitad Rp. era mezclar los dos criterios.
#
# Por eso cada mitad tiene sus propias x, todas medidas sobre el escaneo
# normalizado a 10 px/mm. Lo unico compartido es GUIA_DER_MM para el codigo
# "N.º" (decision 7 del medico: la misma guia en las dos mitades).

LOGO_X_MM = 16.4                 # mitad Rp.  — tinta medida en 16,40
LOGO_X_IND_MM = 17.8             # mitad Ind. — tinta medida en 17,90 local
LOGO_Y_MM = 15.9
LOGO_ANCHO_MM = 21.7             # lockup simbolo + "espacio CORPORAL", sin bajada
LOGO_PROPORCION = 713 / 562      # recursos/logo.png = 713 x 562 px

SALUD_TEXTO = "Salud y Bienestar"
SALUD_X_MM = 15.9                # mitad Rp.  — tinta medida en 15,90
SALUD_X_IND_MM = 18.1            # mitad Ind. — tinta medida en 18,20 local
SALUD_BASE_Y_MM = 40.1           # con PT_SALUD = 12 la "S" apoya en 40,2 igual
                                 # que en el modelo (a 11 pt la base quedaba 0,2
                                 # mm alta y no se notaba por el cuerpo chico)
SALUD_ANCHO_MM = 32.6            # medido: x 15,91 -> 48,50 en la mitad izquierda
                                 # (la Parte B decia 41,3 mm porque escalo con el
                                 #  MediaBox del escaner y no con el papel real;
                                 #  remedido sobre el escaneo normalizado da
                                 #  32,70 mm en la mitad Rp. y 32,30 en la Ind.)

RP_X_MM = 16.15                  # 0,25 mm de compensacion del prensaje de la italica
RP_X_IND_MM = 17.95              # mitad Ind. — tinta de la "I" medida en 18,30 local
RP_BASE_Y_MM = 51.9              # linea de base: en el modelo la "R" apoya en 51,7
                                 # (mitad Rp.) y la "I" en 52,4 (mitad Ind.); 51,9
                                 # es el punto medio de las dos mitades

CODIGO_ROTULO = "N.º"
CODIGO_BASE_Y_MM = 22.6          # arriba a la derecha, a la altura del logo
CODIGO_SEPARACION_MM = 1.8       # aire entre "N.º" y el codigo

# =============================================================================
# 5. CUERPO LIBRE
# =============================================================================

CUERPO_Y0_MM = 57.0
CUERPO_RP_Y1_MM = 163.5          # frena antes del bloque Dr./CI/MPPS (166,8)
CUERPO_IND_Y1_MM = 186.0         # la mitad Ind. no tiene ese bloque

# =============================================================================
# 6. BLOQUE DE COLEGIATURA  (solo mitad Rp.; queda EN BLANCO por decision medica)
# =============================================================================

COLEGIATURA_ROTULO_DER_MM = 86.2     # los rotulos se alinean a la derecha por los ":"
COLEGIATURA_RAYA_X0_MM = 86.5        # medido sobre el escaneo en filas limpias de
                                     # texto: las rayas nacen en 86,2-86,5 y casi
                                     # tocan los dos puntos del rotulo. La tabla del
                                     # analisis (88,5) no resiste la medicion.
# (rotulo, y de la raya, grosor en mm)
COLEGIATURA = (
    ("Dr.:", 170.1, 0.50),
    ("CI:", 175.2, 0.40),
    ("MPPS:", 180.6, 0.40),
)

# =============================================================================
# 7. RENGLON PACIENTE / FECHA
# =============================================================================

PIE_RAYA_Y_MM = 194.6
PIE_BASE_Y_MM = 193.8            # linea de base de los rotulos
PIE_GROSOR_PACIENTE_MM = 0.40
PIE_GROSOR_FECHA_MM = 0.50
PIE_HUECO_MM = 1.0               # aire entre "Paciente:" y el arranque de su raya
                                 # (era 1,4; se achico para ganar ancho de raya
                                 #  para el nombre — el modelo da 29,3 en la
                                 #  mitad Rp. y con 1,0 el generado da 29,1)
PIE_MARGEN_DATO_MM = 0.7         # aire entre el arranque de la raya y el dato
PIE_MARGEN_DATO_FIN_MM = 0.5     # aire entre el dato y el final de la raya
# Las cinco x de cada mitad, TODAS medidas sobre el escaneo — ninguna se deduce
# de otra (antes la "Fecha:" se colgaba del arranque de su raya y arrastraba el
# largo de la raya del paciente):
#   (x del rotulo "Paciente:", x donde MUERE su raya,
#    x del rotulo "Fecha:",    x donde ARRANCA la raya de la fecha,
#    x donde MUERE la raya de la fecha)
# En la mitad Rp. el renglon se sale a la izquierda; en la Ind. arranca mas
# adentro y su raya de fecha se estira 3,7 mm mas alla de GUIA_DER_MM: medido
# 242,8 -> 270,0/270,3 absolutos = 103,1 -> 130,3 locales (la tabla del §3.2 del
# analisis dice "raya 102,9 -> 130,1"). No es alabeo del escaneo: es un largo,
# no una posicion, y el lockup del logo mide igual en las dos mitades.
# Ojo: la guia del codigo "N.º" sigue siendo GUIA_DER_MM en las DOS mitades.
PIE_RP = (10.5, 84.1, 84.5, 98.85, GUIA_DER_MM)
PIE_IND = (14.8, 88.1, 89.5, 102.9, 130.2)

# Particulas que no se abrevian al acortar un nombre largo (ver _abreviar_nombre)
_PARTICULAS = frozenset(
    ("de", "del", "la", "las", "lo", "los", "y", "e", "da", "das", "do", "dos",
     "di", "van", "von", "san", "santa")
)

# =============================================================================
# 8. ORNAMENTO LATERAL
# =============================================================================
# Silueta calcada del escaneo a 200 dpi: para cada fila de pixeles se aislaron
# los pixeles cromaticos (saturacion > 15) del borde exterior y se anotaron los
# limites de cada trazo. Los puntos de abajo son esa medicion, en mm locales
# desde el borde EXTERIOR de la media carta. Se interpolan con Catmull-Rom
# convertido a Bezier cubica, asi la curva pasa exactamente por lo medido.

ORNAMENTO_ANCHO_MAX_MM = 11.3    # a la altura y ~ 44 mm

# Canto interno del cuerpo macizo: nace en el borde superior y muere en el
# borde exterior a y ~ 151,5 mm.
_ORN_CUERPO_BORDE = (
    (7.00, 0.0), (8.05, 5.0), (8.95, 10.0), (9.66, 15.0), (10.16, 20.0),
    (10.56, 25.0), (10.96, 30.0), (11.16, 35.0), (11.30, 44.0), (11.16, 52.0),
    (10.76, 60.0), (10.36, 65.0), (9.96, 70.0), (9.35, 75.0), (8.85, 80.0),
    (8.05, 85.0), (7.54, 90.0), (6.64, 95.0), (6.14, 100.0), (4.83, 110.0),
    (3.52, 120.0), (2.31, 130.0), (1.21, 140.0), (0.40, 150.0), (0.00, 151.5),
)

# Hoja fina secundaria: cruza por dentro del cuerpo y cierra la silueta.
# La punta nace en y ~ 70,5: en el modelo la primera fila con dos trazos es la
# y = 71 ([12,2-12,5]); en la y = 70 todavia hay uno solo.
_ORN_HOJA_EXT = (
    (12.38, 70.6), (12.52, 73.0), (12.40, 76.0), (12.07, 80.0), (11.06, 90.0),
    (10.06, 100.0),
    (9.05, 110.0), (7.74, 120.0), (6.74, 130.0), (5.83, 140.0), (4.83, 150.0),
    (3.92, 160.0), (3.22, 170.0), (2.82, 180.0), (2.92, 190.0), (3.42, 196.0),
    (3.82, 200.0), (4.35, 206.0),
)
_ORN_HOJA_INT = (
    (12.30, 71.0), (12.05, 73.0), (11.70, 76.0), (11.06, 80.0), (9.66, 90.0),
    (8.35, 100.0),
    (6.94, 110.0), (5.73, 120.0), (4.53, 130.0), (3.42, 140.0), (2.61, 150.0),
    (1.81, 160.0), (1.11, 170.0), (0.80, 176.0), (1.01, 180.0), (1.71, 190.0),
    (2.51, 196.0), (3.02, 200.0), (4.22, 206.0),
)

# Filete teal sobre el canto EXTERIOR (x = 0). En el modelo el cuerpo lleva
# filete en los dos cantos durante los primeros ~44 mm: muestreado desde el
# borde de la hoja, a y = 15 los pixeles de 0,4 a 1,0 mm dan teal y recien a
# 1,3 mm aparece el verde. Se apaga cerca de y = 45. Estos puntos son el canto
# INTERNO de esa franja (el externo es la recta x = 0).
_ORN_FILETE_EXT = (
    (0.35, 0.0), (0.65, 5.0), (0.95, 10.0), (1.15, 15.0), (1.20, 20.0),
    (1.20, 25.0), (1.10, 30.0), (0.90, 35.0), (0.60, 40.0), (0.35, 43.0),
    (0.00, 45.5),
)

# Cuna teal del angulo inferior exterior: nace en el borde exterior a y ~ 196 y
# se ensancha hasta el borde inferior de la hoja. Medida en la mitad izquierda
# del escaneo (y = 198 -> 0,6 mm; y = 206 -> 1,8; y = 214 -> 3,6). Su canto
# exterior es la recta x = 0.
_ORN_CUNA_PIE = (
    (0.00, 196.3), (0.55, 198.0), (0.90, 200.0), (1.20, 202.0), (1.50, 204.0),
    (1.85, 206.0), (2.35, 208.0), (2.70, 210.0), (3.15, 212.0), (3.55, 214.0),
    (3.95, 215.9),
)

# Filete teal del canto INTERNO del cuerpo. En el modelo no es un hilo sino una
# BANDA maciza que se ensancha hacia abajo (el cuerpo tiene tambien degradado
# lateral: se pone mas teal hacia adentro). Medido con criterio de tono
# (B > R + 8) sobre el escaneo normalizado a 10 px/mm, fila por fila:
#   y=  5 -> 1,00 mm    y= 40 -> 1,40 mm    y= 90 -> 1,80 mm
#   y= 10 -> 1,10 mm    y= 50 -> 1,40 mm    y=100 -> 1,70 mm
#   y= 20 -> 1,10 mm    y= 60 -> 1,40 mm    y=110 -> 1,90 mm
#   y= 30 -> 1,00 mm    y= 80 -> 1,50 mm
# Debajo de y ~ 115 el degradado vertical ya volvio teal a todo el cuerpo y la
# banda deja de distinguirse, asi que se mantiene en 1,90 mm hasta la punta.
# NO se resuelve con un trazo centrado sobre la curva del borde: la mitad
# exterior del trazo caeria adentro del cuerpo y la interior se derramaria al
# blanco, ensanchando la silueta (que ya esta bien: 11,3 mm de maximo a y=44).
_ORN_FILETE_INT = (
    (0.0, 1.05), (10.0, 1.10), (20.0, 1.10), (30.0, 1.05), (35.0, 1.20),
    (45.0, 1.38), (60.0, 1.40), (70.0, 1.40), (80.0, 1.50), (90.0, 1.78),
    (100.0, 1.75), (110.0, 1.90), (215.9, 1.90),
)

ORNAMENTO_GRAD_Y0_MM = 0.0       # el degradado verde->teal recorre la altura util
ORNAMENTO_GRAD_Y1_MM = 175.0     # abajo de esa altura el ornamento ya es teal pleno

# =============================================================================
# 9. RUTAS POR DEFECTO
# =============================================================================

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _raiz_recursos() -> str:
    """Dónde están `recursos/logo.png` y `recursos/fuentes/`.

    Corriendo desde el código fuente es la raíz del proyecto. Empaquetado con
    PyInstaller `--onedir` (§11.1) el `.py` vive adentro de un archivo comprimido
    y `__file__` ya no apunta a ninguna carpeta real: los datos agregados con
    `--add-data` quedan en ``sys._MEIPASS`` (para `--onedir`, la subcarpeta
    ``_internal`` que está al lado del `.exe`). No hay descompresión temporal ni
    red de por medio: son archivos en disco, al lado del ejecutable.
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _RAIZ


RUTA_LOGO_DEFECTO = os.path.join(_raiz_recursos(), "recursos", "logo.png")
DIR_FUENTES_DEFECTO = os.path.join(_raiz_recursos(), "recursos", "fuentes")


# =============================================================================
# 10. ERRORES
# =============================================================================

class RecipeError(Exception):
    """Error al componer el PDF del recipe."""


class RecursoFaltanteError(RecipeError):
    """Falta el logo o alguna de las fuentes Lato."""


class ContenidoNoCabeError(RecipeError):
    """El texto no entra en el cuerpo libre de una de las mitades.

    Trae los milimetros usados y disponibles para que la interfaz pueda decir
    algo util antes de generar (§7 de las instrucciones).
    """

    def __init__(self, mitad: str, usado_mm: float, disponible_mm: float):
        self.mitad = mitad
        self.usado_mm = usado_mm
        self.disponible_mm = disponible_mm
        sobra = usado_mm - disponible_mm
        super().__init__(
            f"El contenido de la mitad {mitad} no entra en la hoja: "
            f"ocupa {usado_mm:.1f} mm y hay {disponible_mm:.1f} mm. "
            f"Sobran {sobra:.1f} mm — sacá un renglón o acortá el texto."
        )


class NombreNoCabeError(RecipeError):
    """El nombre del paciente no entra en la raya ni abreviado.

    Un nombre de paciente cortado a la mitad en un recipe impreso es un problema
    real, no cosmetico: antes que emitirlo asi, la app frena y pide acortarlo.
    """

    def __init__(self, nombre: str, impreso: str):
        self.nombre = nombre
        self.impreso = impreso
        super().__init__(
            f"El nombre «{nombre}» no entra en la raya del paciente: "
            f"habría que imprimirlo cortado («{impreso}»). "
            f"Escribilo más corto — por ejemplo, con un solo apellido."
        )


# =============================================================================
# 11. UTILIDADES DE CURVAS
# =============================================================================

def _catmull_abierto(puntos: Sequence[tuple[float, float]]):
    """Convierte una polilinea en tramos Bezier cubicos que pasan por los puntos.

    Devuelve una lista de (c1, c2, destino). Catmull-Rom uniforme con los
    extremos duplicados (tangentes naturales en las puntas).
    """
    p = [puntos[0], *puntos, puntos[-1]]
    tramos = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        tramos.append((c1, c2, p2))
    return tramos


def _interpolar(tabla: Sequence[tuple[float, float]], y: float) -> float:
    """Interpola linealmente una tabla (y, valor) ordenada por y."""
    if y <= tabla[0][0]:
        return tabla[0][1]
    if y >= tabla[-1][0]:
        return tabla[-1][1]
    for (y0, v0), (y1, v1) in zip(tabla, tabla[1:]):
        if y <= y1:
            return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
    return tabla[-1][1]


def _desplazar_adentro(puntos: Sequence[tuple[float, float]],
                       tabla: Sequence[tuple[float, float]]):
    """Corre una curva hacia el interior de la hoja, con ancho variable por fila.

    El desplazamiento es HORIZONTAL a proposito: lo que se mide en el escaneo es
    el ancho de la banda teal fila por fila, no su espesor perpendicular.
    Se recorta en x = 0 (el filo del papel) para que la banda no salga de la hoja
    cuando el cuerpo ya es mas angosto que el ancho de la banda.
    """
    return [(max(0.0, x - _interpolar(tabla, y)), y) for x, y in puntos]


def _catmull_cerrado(puntos: Sequence[tuple[float, float]]):
    """Igual que `_catmull_abierto` pero el anillo se cierra sobre si mismo."""
    n = len(puntos)
    tramos = []
    for i in range(n):
        p0 = puntos[(i - 1) % n]
        p1 = puntos[i]
        p2 = puntos[(i + 1) % n]
        p3 = puntos[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        tramos.append((c1, c2, p2))
    return tramos


# =============================================================================
# 12. COMPOSITOR
# =============================================================================

class _Recipe(FPDF):
    """Lienzo del recipe. Uso interno: la API publica son las funciones de abajo."""

    def __init__(self, ruta_logo: str, dir_fuentes: str):
        # "Letter" apaisada = 279,4 x 215,9 mm exactos (11 x 8,5 in)
        super().__init__(orientation="L", unit="mm", format="Letter")
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)
        self.set_compression(True)
        self.ruta_logo = ruta_logo
        self.estado_nombre = "completo"   # completo | abreviado | truncado
        self.nombre_impreso = ""
        self._cargar_fuentes(dir_fuentes)

    # -- recursos ----------------------------------------------------------
    def _cargar_fuentes(self, dir_fuentes: str) -> None:
        for estilo, archivo in _ARCHIVOS_FUENTE.items():
            ruta = os.path.join(dir_fuentes, archivo)
            if not os.path.isfile(ruta):
                raise RecursoFaltanteError(
                    f"Falta la fuente {archivo}. Esperada en: {ruta}"
                )
            self.add_font(FUENTE, estilo, ruta)

    # -- helpers de texto --------------------------------------------------
    def _ancho(self, texto: str, estilo: str, pt: float) -> float:
        self.set_font(FUENTE, estilo, pt)
        return self.get_string_width(texto)

    def _envolver(self, texto: str, ancho_mm: float, estilo: str, pt: float) -> list[str]:
        """Parte `texto` en renglones que entren en `ancho_mm`."""
        self.set_font(FUENTE, estilo, pt)
        renglones: list[str] = []
        for parrafo in str(texto).replace("\r\n", "\n").split("\n"):
            palabras = [p for p in parrafo.split(" ") if p]
            if not palabras:
                renglones.append("")
                continue
            actual = ""
            for palabra in palabras:
                tanteo = palabra if not actual else f"{actual} {palabra}"
                if self.get_string_width(tanteo) <= ancho_mm or not actual:
                    if self.get_string_width(tanteo) > ancho_mm and not actual:
                        # palabra sola mas ancha que la columna: se corta duro
                        trozo = ""
                        for caracter in palabra:
                            if self.get_string_width(trozo + caracter) > ancho_mm and trozo:
                                renglones.append(trozo)
                                trozo = caracter
                            else:
                                trozo += caracter
                        actual = trozo
                    else:
                        actual = tanteo
                else:
                    renglones.append(actual)
                    actual = palabra
            renglones.append(actual)
        return renglones

    def _texto(self, x: float, base_y: float, texto: str, estilo: str, pt: float,
               color: tuple[int, int, int]) -> float:
        self.set_font(FUENTE, estilo, pt)
        self.set_text_color(*color)
        self.text(x, base_y, texto)
        return self.get_string_width(texto)

    def _texto_der(self, x_der: float, base_y: float, texto: str, estilo: str,
                   pt: float, color: tuple[int, int, int]) -> float:
        ancho = self._ancho(texto, estilo, pt)
        self._texto(x_der - ancho, base_y, texto, estilo, pt, color)
        return ancho

    def _texto_a_ancho(self, x: float, base_y: float, texto: str, estilo: str,
                       pt: float, color: tuple[int, int, int], ancho_mm: float) -> None:
        """Escribe `texto` estirando el interletrado hasta ocupar `ancho_mm`.

        Es lo que hace el talonario con "Salud y Bienestar": mismo cuerpo que el
        resto pero tracking apenas abierto para llegar al ancho del logo.
        """
        natural = self._ancho(texto, estilo, pt)
        huecos = max(len(texto) - 1, 1)
        # set_char_spacing trabaja en puntos tipograficos
        extra_pt = (ancho_mm - natural) / huecos / 0.352777778
        self.set_char_spacing(extra_pt)
        self._texto(x, base_y, texto, estilo, pt, color)
        self.set_char_spacing(0)

    # -- helpers de trazo --------------------------------------------------
    def _raya(self, x0: float, x1: float, y: float, grosor: float,
              color: tuple[int, int, int] = GRIS_ROTULO) -> None:
        self.set_draw_color(*color)
        self.set_line_width(grosor)
        self.line(x0, y, x1, y)

    # =====================================================================
    # ORNAMENTO
    # =====================================================================
    def _pintar_ornamento(self, espejo: bool) -> None:
        """Dibuja la onda lateral sobre el borde exterior de una mitad.

        `espejo=False` -> borde izquierdo de la hoja (mitad Rp.).
        `espejo=True`  -> borde derecho de la hoja (mitad Ind.), en espejo.

        El degradado verde->teal es un shading nativo de PDF aplicado al path
        (fpdf2 2.8 lo soporta via GradientPaint), asi que no hace falta recortar
        bandas: la transicion sale continua y sin costuras al imprimir.
        """
        def X(x: float) -> float:
            return (PAGINA_ANCHO_MM - x) if espejo else x

        def pintura():
            return GradientPaint(shape_linear_gradient(
                X(0.0), ORNAMENTO_GRAD_Y0_MM, X(0.0), ORNAMENTO_GRAD_Y1_MM,
                [(0.0, VERDE_LIMA_HEX), (1.0, TEAL_MEDIO_HEX)],
            ))

        # --- cuerpo macizo -------------------------------------------------
        borde = [(X(x), y) for x, y in _ORN_CUERPO_BORDE]
        with self.new_path() as path:
            path.style.fill_color = pintura()
            path.style.stroke_color = None
            path.move_to(X(0.0), 0.0)
            path.line_to(*borde[0])
            for c1, c2, destino in _catmull_abierto(borde):
                path.curve_to(c1[0], c1[1], c2[0], c2[1], destino[0], destino[1])
            path.close()

        # --- banda teal sobre el canto interno ------------------------------
        # Es un ANILLO RELLENO, no un trazo: canto exterior = la misma curva del
        # borde del cuerpo (asi no hay costura ni se ensancha la silueta), canto
        # interior = esa curva corrida hacia adentro segun `_ORN_FILETE_INT`.
        adentro = [(X(x), y) for x, y in
                   _desplazar_adentro(_ORN_CUERPO_BORDE, _ORN_FILETE_INT)]
        with self.new_path() as path:
            path.style.fill_color = "#%02X%02X%02X" % TEAL_MEDIO
            path.style.stroke_color = None
            path.move_to(*borde[0])
            for c1, c2, destino in _catmull_abierto(borde):
                path.curve_to(c1[0], c1[1], c2[0], c2[1], destino[0], destino[1])
            vuelta = list(reversed(adentro))
            path.line_to(*vuelta[0])
            for c1, c2, destino in _catmull_abierto(vuelta):
                path.curve_to(c1[0], c1[1], c2[0], c2[1], destino[0], destino[1])
            path.close()

        # --- filete teal sobre el canto exterior (primeros ~45 mm) ----------
        franja = [(X(x), y) for x, y in _ORN_FILETE_EXT]
        with self.new_path() as path:
            path.style.fill_color = "#%02X%02X%02X" % TEAL_MEDIO
            path.style.stroke_color = None
            path.move_to(X(0.0), _ORN_FILETE_EXT[0][1])
            path.line_to(*franja[0])
            for c1, c2, destino in _catmull_abierto(franja):
                path.curve_to(c1[0], c1[1], c2[0], c2[1], destino[0], destino[1])
            path.close()

        # --- hoja fina secundaria ------------------------------------------
        anillo = [(X(x), y) for x, y in _ORN_HOJA_EXT]
        anillo += [(X(x), y) for x, y in reversed(_ORN_HOJA_INT)]
        with self.new_path() as path:
            path.style.fill_color = pintura()
            path.style.stroke_color = None
            path.move_to(*anillo[0])
            for c1, c2, destino in _catmull_cerrado(anillo):
                path.curve_to(c1[0], c1[1], c2[0], c2[1], destino[0], destino[1])
            path.close()

        # --- cuna del angulo inferior exterior ------------------------------
        cuna = [(X(x), y) for x, y in _ORN_CUNA_PIE]
        with self.new_path() as path:
            path.style.fill_color = "#%02X%02X%02X" % TEAL_MEDIO
            path.style.stroke_color = None
            path.move_to(*cuna[0])
            for c1, c2, destino in _catmull_abierto(cuna):
                path.curve_to(c1[0], c1[1], c2[0], c2[1], destino[0], destino[1])
            path.line_to(X(0.0), PAGINA_ALTO_MM)
            path.close()

    # =====================================================================
    # LINEA DE CORTE
    # =====================================================================
    def _linea_corte(self) -> None:
        self.set_draw_color(*GRIS_CORTE)
        # El trazo del modelo abarca 0,7 mm de ancho; descontando el desenfoque
        # del escaneo (~0,3 mm) el original anda en 0,4-0,5 mm. Con 0,25 mm la
        # marca de corte salia perceptiblemente mas tenue que la del talonario
        # (decil oscuro #E1E1E1 contra #C3C3C3 del modelo).
        self.set_line_width(0.45)
        # Los guiones del modelo son muy irregulares (0,4 a 5,0 mm), asi que lo
        # que hay que igualar es el RELLENO: medido en una franja limpia
        # (y = 105 a 155) da 61-67 % con huecos de 1,2-1,6 mm. 2,2/1,4 da 61 %.
        # El 1,1/1,6 anterior daba 41 %, que es lo que sale si se promedia toda
        # la columna incluyendo los tramos donde la foto perdio la linea.
        self.set_dash_pattern(dash=2.0, gap=1.6)
        self.line(LINEA_CORTE_X_MM, 0.1, LINEA_CORTE_X_MM, PAGINA_ALTO_MM - 1.2)
        self.set_dash_pattern()

    # =====================================================================
    # ENCABEZADO DE UNA MITAD
    # =====================================================================
    def _encabezado(self, ox: float, rotulo: str, codigo: str,
                    logo_x: float, salud_x: float, rp_x: float) -> None:
        """Encabezado de una mitad.

        Las tres x llegan por parametro porque las dos mitades del talonario no
        registran igual: la Ind. esta corrida 1,4-2,2 mm a la derecha (ver §4).
        """
        alto_logo = LOGO_ANCHO_MM / LOGO_PROPORCION
        self.image(self.ruta_logo, x=ox + logo_x, y=LOGO_Y_MM,
                   w=LOGO_ANCHO_MM, h=alto_logo)

        self._texto_a_ancho(ox + salud_x, SALUD_BASE_Y_MM, SALUD_TEXTO,
                            "", PT_SALUD, TEAL_OSCURO, SALUD_ANCHO_MM)

        self._texto(ox + rp_x, RP_BASE_Y_MM, rotulo, "BI", PT_RP, TEAL_OSCURO)

        # Codigo unico, arriba a la derecha, sobre la guia de las rayas.
        ancho_cod = self._texto_der(ox + GUIA_DER_MM, CODIGO_BASE_Y_MM,
                                    codigo, "B", PT_CODIGO, GRIS_ROTULO)
        self._texto_der(ox + GUIA_DER_MM - ancho_cod - CODIGO_SEPARACION_MM,
                        CODIGO_BASE_Y_MM, CODIGO_ROTULO, "", PT_CODIGO_ROTULO,
                        GRIS_ROTULO)

    # =====================================================================
    # PIE: colegiatura y renglon paciente / fecha
    # =====================================================================
    def _colegiatura(self, ox: float) -> None:
        """Los tres renglones del sello. Van EN BLANCO por decision del medico."""
        for rotulo, y_raya, grosor in COLEGIATURA:
            self._texto_der(ox + COLEGIATURA_ROTULO_DER_MM, y_raya - 0.3,
                            rotulo, "", PT_ROTULO, GRIS_ROTULO)
            self._raya(ox + COLEGIATURA_RAYA_X0_MM, ox + GUIA_DER_MM,
                       y_raya, grosor)

    def _ancho_nombre_mm(self, geometria: tuple[float, ...]) -> float:
        """Ancho util para el nombre del paciente sobre su raya, en mm."""
        pac_x, pac_raya_x1 = geometria[0], geometria[1]
        ancho_rot = self._ancho("Paciente:", "", PT_ROTULO)
        raya_x0 = pac_x + ancho_rot + PIE_HUECO_MM
        return (pac_raya_x1 - raya_x0
                - PIE_MARGEN_DATO_MM - PIE_MARGEN_DATO_FIN_MM)

    def _pie_paciente(self, ox: float,
                      geometria: tuple[float, float, float, float, float],
                      nombre: str, nombre_pt: float, fecha: str) -> None:
        pac_x, pac_raya_x1, fec_x, fecha_raya_x0, fecha_raya_x1 = geometria

        ancho_rot = self._texto(ox + pac_x, PIE_BASE_Y_MM, "Paciente:", "",
                                PT_ROTULO, GRIS_ROTULO)
        raya_pac_x0 = ox + pac_x + ancho_rot + PIE_HUECO_MM
        raya_pac_x1 = ox + pac_raya_x1

        self._texto(ox + fec_x, PIE_BASE_Y_MM, "Fecha:", "", PT_ROTULO, GRIS_ROTULO)

        raya_fec_x0 = ox + fecha_raya_x0
        raya_fec_x1 = ox + fecha_raya_x1
        self._raya(raya_pac_x0, raya_pac_x1, PIE_RAYA_Y_MM, PIE_GROSOR_PACIENTE_MM)
        self._raya(raya_fec_x0, raya_fec_x1, PIE_RAYA_Y_MM, PIE_GROSOR_FECHA_MM)

        # Datos escritos sobre las rayas
        base_dato = PIE_RAYA_Y_MM - 1.1
        # El nombre llega ya resuelto (texto y cuerpo) para que las dos mitades
        # lo impriman identico, aunque sus rayas no midan exactamente igual.
        self._texto(raya_pac_x0 + PIE_MARGEN_DATO_MM, base_dato, nombre, "",
                    nombre_pt, GRIS_DATO)
        ancho_fecha = self._ancho(fecha, "", PT_DATO)
        self._texto(raya_fec_x0 + (raya_fec_x1 - raya_fec_x0 - ancho_fecha) / 2.0,
                    base_dato, fecha, "", PT_DATO, GRIS_DATO)

    # -- nombre del paciente ------------------------------------------------
    @staticmethod
    def _abreviar_nombre(nombre: str) -> str:
        """Abrevia los nombres de pila del medio, dejando intactos los apellidos.

        Convencion hispana: las dos ultimas palabras son los apellidos y la
        primera es el nombre de pila. Lo del medio se reduce a inicial:
        "María Fernanda Rodríguez Blanco" -> "María F. Rodríguez Blanco".
        Con tres palabras o menos no hay nada del medio: devuelve el original.
        Las particulas ("de", "la", "los"...) quedan enteras: abreviarlas no
        ahorra nada y vuelve el nombre ilegible ("Juan D. L. Cruz").
        """
        palabras = nombre.split()
        if len(palabras) < 4:
            return nombre
        medio = [p if p.lower() in _PARTICULAS or not p[:1].isalpha()
                 else f"{p[0].upper()}."
                 for p in palabras[1:-2]]
        return " ".join([palabras[0], *medio, *palabras[-2:]])

    def _ajustar_nombre(self, nombre: str, ancho_mm: float
                        ) -> tuple[str, float, str]:
        """Encaja el nombre del paciente en `ancho_mm`.

        Devuelve `(texto a imprimir, cuerpo en pt, estado)`, donde estado es
        `"completo"`, `"abreviado"` o `"truncado"`. El orden importa: primero se
        baja el cuerpo hasta un piso COMODO, recien despues se abrevian los
        nombres del medio, y el corte con puntos suspensivos es el ultimo
        recurso — un nombre de paciente truncado en un recipe impreso es un
        problema real, no cosmetico, y por eso `generar_recipe()` lo rechaza.
        """
        nombre = str(nombre).strip()
        if not nombre:
            return "", PT_DATO, "completo"

        def encoger(texto: str, piso: float) -> float | None:
            pt = PT_DATO
            while self._ancho(texto, "", pt) > ancho_mm:
                pt -= 0.25
                if pt < piso:
                    return None
            return pt

        # 1. Nombre completo, sin bajar de un cuerpo comodo de leer.
        pt = encoger(nombre, PT_DATO_COMODO)
        if pt is not None:
            return nombre, pt, "completo"

        # 2. Nombre completo hasta el piso legible: un nombre entero chico
        #    vale mas que uno abreviado grande — es un dato de identificacion
        #    y no se altera mientras entre legible.
        pt = encoger(nombre, PT_DATO_MIN)
        if pt is not None:
            return nombre, pt, "completo"

        # 3. Recien ahora se abrevian los nombres del medio.
        corto = self._abreviar_nombre(nombre)
        if corto != nombre:
            for piso in (PT_DATO_COMODO, PT_DATO_MIN):
                pt = encoger(corto, piso)
                if pt is not None:
                    return corto, pt, "abreviado"

        # 4. Ultimo recurso.
        texto, pt = corto, PT_DATO_MIN
        while texto and self._ancho(texto + "…", "", pt) > ancho_mm:
            texto = texto[:-1]
        return texto + "…", pt, "truncado"

    # =====================================================================
    # CUERPO — mitad Rp.
    # =====================================================================
    def _cuerpo_rp(self, ox: float, items: Sequence[Mapping[str, Any]],
                   dibujar: bool) -> float:
        x_num = ox + MARGEN_IZQ_MM
        x_txt = x_num + SANGRIA_MM
        x_der = ox + GUIA_DER_MM
        y = CUERPO_Y0_MM + INTERLINEA_MM * 0.72

        for i, item in enumerate(items, start=1):
            medicamento = str(item.get("medicamento", "")).strip()
            presentacion = str(item.get("presentacion", "")).strip()
            cantidad = str(item.get("cantidad", "")).strip()
            dosis = str(item.get("dosis", "")).strip()

            ancho_cant = self._ancho(cantidad, "", PT_CUERPO_MENOR) if cantidad else 0.0
            ancho_titulo = (x_der - x_txt) - (ancho_cant + 4.0 if cantidad else 0.0)
            ancho_libre = x_der - x_txt

            # El titulo es "medicamento — presentacion" en una sola linea; si no
            # entra, la presentacion baja a su propio renglon en redonda (asi no
            # queda una raya suelta al principio de un renglon).
            if medicamento and presentacion:
                junto = self._envolver(f"{medicamento} — {presentacion}",
                                       ancho_titulo, "B", PT_CUERPO)
                if len(junto) == 1:
                    partes = [(junto[0], "B", PT_CUERPO)]
                else:
                    partes = [(t, "B", PT_CUERPO)
                              for t in self._envolver(medicamento, ancho_titulo,
                                                      "B", PT_CUERPO)]
                    partes += [(t, "", PT_CUERPO_MENOR)
                               for t in self._envolver(presentacion, ancho_libre,
                                                       "", PT_CUERPO_MENOR)]
            else:
                texto = medicamento or presentacion
                partes = [(t, "B", PT_CUERPO)
                          for t in self._envolver(texto, ancho_titulo, "B", PT_CUERPO)]
            if not partes:
                partes = [("", "B", PT_CUERPO)]

            if dosis:
                partes += [(t, "", PT_CUERPO_MENOR)
                           for t in self._envolver(dosis, ancho_libre, "",
                                                   PT_CUERPO_MENOR)]

            for k, (texto, estilo, pt) in enumerate(partes):
                if k:
                    y += INTERLINEA_MM
                if dibujar:
                    if k == 0:
                        self._texto(x_num, y, f"{i}.", "B", PT_CUERPO, GRIS_DATO)
                        if cantidad:
                            self._texto_der(x_der, y, cantidad, "",
                                            PT_CUERPO_MENOR, GRIS_DATO)
                    self._texto(x_txt, y, texto, estilo, pt, GRIS_DATO)

            y += INTERLINEA_MM + SEPARACION_ITEM_MM

        usado = y - SEPARACION_ITEM_MM - CUERPO_Y0_MM if items else 0.0
        return max(usado, 0.0)

    # =====================================================================
    # CUERPO — mitad Ind.
    # =====================================================================
    def _cuerpo_ind(self, ox: float, items: Sequence[Mapping[str, Any]],
                    generales: str, dibujar: bool) -> float:
        x_num = ox + MARGEN_IZQ_MM
        x_txt = x_num + SANGRIA_MM
        x_der = ox + GUIA_DER_MM
        y = CUERPO_Y0_MM + INTERLINEA_MM * 0.72
        hubo_algo = False

        for i, item in enumerate(items, start=1):
            texto = str(item.get("indicaciones", "") or "").strip()
            if not texto:
                continue
            hubo_algo = True
            renglones = self._envolver(texto, x_der - x_txt, "", PT_CUERPO)
            if dibujar:
                self._texto(x_num, y, f"{i}.", "B", PT_CUERPO, GRIS_DATO)
                self._texto(x_txt, y, renglones[0], "", PT_CUERPO, GRIS_DATO)
            for extra in renglones[1:]:
                y += INTERLINEA_MM
                if dibujar:
                    self._texto(x_txt, y, extra, "", PT_CUERPO, GRIS_DATO)
            y += INTERLINEA_MM + SEPARACION_ITEM_MM

        if hubo_algo:
            y -= SEPARACION_ITEM_MM

        generales = str(generales or "").strip()
        if generales:
            if hubo_algo:
                y += SEPARACION_GENERAL_MM
            else:
                y -= INTERLINEA_MM
            renglones = self._envolver(generales, x_der - x_num, "", PT_CUERPO_MENOR)
            for k, renglon in enumerate(renglones):
                if k:
                    y += INTERLINEA_MM
                if dibujar:
                    self._texto(x_num, y, renglon, "", PT_CUERPO_MENOR, GRIS_DATO)
            y += INTERLINEA_MM
            hubo_algo = True

        usado = (y - INTERLINEA_MM - CUERPO_Y0_MM) if hubo_algo else 0.0
        return max(usado, 0.0)

    # =====================================================================
    # ARMADO COMPLETO
    # =====================================================================
    def componer(self, datos: Mapping[str, Any], dibujar: bool = True) -> tuple[float, float]:
        items = list(datos.get("items") or [])
        codigo = str(datos.get("codigo", "")).strip()
        paciente = str(datos.get("paciente_nombre", "")).strip()
        fecha = _formatear_fecha(datos.get("fecha_emision", ""))
        generales = datos.get("indicaciones_generales", "")

        # El nombre se resuelve una sola vez con el ancho de la raya MAS CORTA
        # de las dos mitades, asi sale identico en las dos.
        ancho_nombre = min(self._ancho_nombre_mm(PIE_RP),
                           self._ancho_nombre_mm(PIE_IND))
        nombre, nombre_pt, self.estado_nombre = self._ajustar_nombre(
            paciente, ancho_nombre)
        self.nombre_impreso = nombre

        self.add_page()

        if dibujar:
            self._pintar_ornamento(espejo=False)
            self._pintar_ornamento(espejo=True)
            self._linea_corte()

            self._encabezado(0.0, "Rp.", codigo,
                             LOGO_X_MM, SALUD_X_MM, RP_X_MM)
            self._encabezado(MITAD_ANCHO_MM, "Ind.", codigo,
                             LOGO_X_IND_MM, SALUD_X_IND_MM, RP_X_IND_MM)

            self._colegiatura(0.0)
            self._pie_paciente(0.0, PIE_RP, nombre, nombre_pt, fecha)
            self._pie_paciente(MITAD_ANCHO_MM, PIE_IND, nombre, nombre_pt, fecha)

        alto_rp = self._cuerpo_rp(0.0, items, dibujar)
        alto_ind = self._cuerpo_ind(MITAD_ANCHO_MM, items, generales, dibujar)
        return alto_rp, alto_ind


# =============================================================================
# 13. API PUBLICA
# =============================================================================

ALTO_DISPONIBLE_RP_MM = CUERPO_RP_Y1_MM - CUERPO_Y0_MM
ALTO_DISPONIBLE_IND_MM = CUERPO_IND_Y1_MM - CUERPO_Y0_MM


def _formatear_fecha(valor: Any) -> str:
    """Acepta 'dd/mm/aaaa', ISO 'aaaa-mm-dd' o un date/datetime."""
    if valor is None:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor).strip()
    if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
        return f"{texto[8:10]}/{texto[5:7]}/{texto[0:4]}"
    return texto


def medir_contenido(datos: Mapping[str, Any], *,
                    ruta_logo: str = RUTA_LOGO_DEFECTO,
                    dir_fuentes: str = DIR_FUENTES_DEFECTO) -> dict[str, Any]:
    """Calcula cuanto ocupa el contenido sin escribir ningun archivo.

    La interfaz lo usa para avisar ANTES de generar (§7 de las instrucciones).
    Devuelve un dict con `entra` (bool) y los milimetros usados y disponibles
    de cada mitad.
    """
    doc = _Recipe(ruta_logo, dir_fuentes)
    alto_rp, alto_ind = doc.componer(datos, dibujar=False)
    return {
        "entra": (alto_rp <= ALTO_DISPONIBLE_RP_MM
                  and alto_ind <= ALTO_DISPONIBLE_IND_MM
                  and doc.estado_nombre != "truncado"),
        "rp_usado_mm": round(alto_rp, 2),
        "rp_disponible_mm": round(ALTO_DISPONIBLE_RP_MM, 2),
        "ind_usado_mm": round(alto_ind, 2),
        "ind_disponible_mm": round(ALTO_DISPONIBLE_IND_MM, 2),
        # "completo" | "abreviado" (se acortaron los nombres del medio a inicial)
        # | "truncado" (no entra ni abreviado: generar_recipe lo rechaza)
        "nombre_estado": doc.estado_nombre,
        "nombre_impreso": doc.nombre_impreso,
    }


def generar_recipe(datos: Mapping[str, Any], ruta_salida: str, *,
                   ruta_logo: str = RUTA_LOGO_DEFECTO,
                   dir_fuentes: str = DIR_FUENTES_DEFECTO) -> str:
    """Escribe el PDF del recipe y devuelve la ruta de salida.

    `datos` es un dict plano — el modulo NO consulta la base de datos:

        codigo                 str   'EC-2026-0001'
        fecha_emision          str|date  '14/08/2026' o '2026-08-14'
        paciente_nombre        str
        items                  list[dict] con:
            medicamento        str
            presentacion       str
            cantidad           str
            dosis              str
            indicaciones       str   (puede ir vacia: ese numero no sale en Ind.)
        indicaciones_generales str   texto libre al pie de la mitad Ind.

    Levanta `ContenidoNoCabeError` si el cuerpo no entra en alguna mitad,
    `NombreNoCabeError` si el nombre del paciente no entra ni abreviado, y
    `RecursoFaltanteError` si falta el logo o alguna Lato. Nunca desborda la
    hoja ni achica el cuerpo del texto.
    """
    if not os.path.isfile(ruta_logo):
        raise RecursoFaltanteError(f"Falta el logo. Esperado en: {ruta_logo}")

    doc = _Recipe(ruta_logo, dir_fuentes)
    alto_rp, alto_ind = doc.componer(datos, dibujar=True)

    if alto_rp > ALTO_DISPONIBLE_RP_MM:
        raise ContenidoNoCabeError("Rp.", alto_rp, ALTO_DISPONIBLE_RP_MM)
    if alto_ind > ALTO_DISPONIBLE_IND_MM:
        raise ContenidoNoCabeError("Ind.", alto_ind, ALTO_DISPONIBLE_IND_MM)
    if doc.estado_nombre == "truncado":
        raise NombreNoCabeError(str(datos.get("paciente_nombre", "")).strip(),
                                doc.nombre_impreso)

    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    doc.output(ruta_salida)
    return ruta_salida


# =============================================================================
# 14. PRUEBA
# =============================================================================

if __name__ == "__main__":
    EJEMPLO = {
        "codigo": "EC-2026-0001",
        "fecha_emision": "14/08/2026",
        "paciente_nombre": "María Fernanda Rodríguez Blanco",
        "items": [
            {
                "medicamento": "Amoxicilina / Ácido clavulánico 875/125 mg",
                "presentacion": "Tabletas recubiertas",
                "cantidad": "14 tabletas",
                "dosis": "1 tableta vía oral cada 12 horas durante 7 días.",
                "indicaciones": "Tomar con las comidas para reducir la molestia "
                                "estomacal. Completar los 7 días aunque los "
                                "síntomas cedan antes.",
            },
            {
                "medicamento": "Ibuprofeno 400 mg",
                "presentacion": "Comprimidos",
                "cantidad": "20 comprimidos",
                "dosis": "1 comprimido cada 8 horas, sólo si hay dolor o fiebre "
                         "mayor de 38 °C.",
                "indicaciones": "No tomar en ayunas. Suspender si aparece ardor "
                                "estomacal y avisar a la consulta.",
            },
            {
                "medicamento": "Loratadina 10 mg",
                "presentacion": "Tabletas",
                "cantidad": "10 tabletas",
                "dosis": "1 tableta diaria en la noche por 10 días.",
                "indicaciones": "Puede dar somnolencia: preferible tomarla antes "
                                "de dormir.",
            },
        ],
        "indicaciones_generales": (
            "Reposo relativo por 48 horas. Abundantes líquidos (2 a 3 litros al "
            "día). Evitar bebidas alcohólicas mientras dure el tratamiento. "
            "Control en consulta dentro de 8 días, o antes si aparece fiebre "
            "que no cede, dificultad para respirar o dolor en el pecho."
        ),
    }

    destino = os.path.join(_RAIZ, "build", "pdf_prueba.pdf")
    print(medir_contenido(EJEMPLO))
    print(generar_recipe(EJEMPLO, destino))
