# -*- coding: utf-8 -*-
"""Piezas compartidas por los tres PDF de Espacio Corporal.

Acá viven la marca y los ladrillos de dibujo que el récipe, el informe y la
historia clínica usan igual: los colores medidos sobre `referencias/Logo.jpg`,
la carga de las Lato embebidas, el logo, el código «N.º EC-0001» arriba a la
derecha, y los helpers de texto (`_texto`, `_texto_der`, `_envolver`, `_raya`).

    from app import pdf_comun

Dos niveles, a propósito:

* `Lienzo` es el mínimo común: fuentes + helpers de tinta. Lo hereda
  `pdf_recipe._Recipe`, que **calca un talonario preimpreso** y por eso maneja
  su geometría a mano, milímetro por milímetro, sin flujo automático de ningún
  tipo.
* `HojaCarta` agrega lo que necesitan los documentos nuevos (dec. 14: carta
  vertical): márgenes, membrete repetido en cada página, un cursor que baja
  solo y salto de página automático. El récipe **no** lo usa ni lo puede usar:
  su hoja es apaisada, tiene dos mitades y no admite una segunda página.

Regla que ordenó esta factorización: **la salida del récipe no cambia ni un
punto**. Todo lo que se movió acá se movió tal cual, con los mismos números y
el mismo orden de operaciones; lo que no era claramente idéntico se dejó donde
estaba. Los tests de `test_pdf_recipe.py` son la red que lo verifica.

Un caso vale la pena documentarlo porque parece duplicación y no lo es:
`pdf_recipe` conserva su propia jerarquía de errores (`RecipeError` y
compañía), porque `rutas.py` engancha manejadores de Flask a esos tipos
concretos y cada uno responde un texto distinto. `RecursoFaltanteError` de acá
es la **base** de la del récipe, así que un `except pdf_comun.RecursoFaltanteError`
atrapa a las dos y ningún manejador viejo dejó de andar. Qué clase levanta el
lienzo al faltar una fuente lo decide `_ERROR_RECURSO`, que cada documento
declara.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from typing import Any, Callable, Sequence

from fpdf import FPDF

# =============================================================================
# 1. GEOMETRIA DEL PAPEL
# =============================================================================

#: Carta vertical: 8,5 x 11 in exactos. Es el formato de la historia y de los
#: informes (dec. 14); el récipe se queda apaisado y no usa estas medidas.
CARTA_ANCHO_MM = 215.9
CARTA_ALTO_MM = 279.4

# =============================================================================
# 2. COLORES DE MARCA
# =============================================================================
# Medidos sobre `referencias/Logo.jpg` (el archivo digital limpio), no sobre el
# escaneo del talonario. Ver `build/analisis-modelo.md`, Parte B.

VERDE_LIMA = (154, 190, 15)      # #9ABE0F  símbolo, CORPORAL, arranque del ornamento
TEAL_MEDIO = (21, 127, 111)      # #157F6F  script "espacio", filetes
TEAL_OSCURO = (18, 85, 80)       # #125550  "Salud y Bienestar", títulos
GRIS_ROTULO = (74, 83, 84)       # #4A5354  rótulos, rayas, "N.º"
GRIS_DATO = (51, 58, 59)         # #333A3B  texto que escribe la app
GRIS_CORTE = (201, 201, 201)     # #C9C9C9  línea de corte punteada del récipe

#: Borde de los recuadros del informe. Es el gris del `.docx` original
#: (`#7F7F7F` a 0,25 pt, Parte B §3): lo único que se rescata de aquella
#: maqueta, porque el médico ya reconoce esa caja fina.
GRIS_RECUADRO = (127, 127, 127)
GROSOR_RECUADRO_MM = 0.09        # 0,25 pt

VERDE_LIMA_HEX = "#9ABE0F"
TEAL_MEDIO_HEX = "#157F6F"

# =============================================================================
# 3. TIPOGRAFIA
# =============================================================================

FUENTE = "Lato"
ARCHIVOS_FUENTE = {
    "": "Lato-Regular.ttf",
    "B": "Lato-Bold.ttf",
    "I": "Lato-Italic.ttf",
    "BI": "Lato-BoldItalic.ttf",
}

#: Un punto tipográfico en milímetros (25,4 / 72). Lo usa el tracking.
PT_A_MM = 0.352777778

# =============================================================================
# 4. RECURSOS
# =============================================================================

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def raiz_recursos() -> str:
    """Dónde están `recursos/logo.png`, `recursos/firma.png` y las fuentes.

    Corriendo desde el código fuente es la raíz del proyecto. Empaquetado con
    PyInstaller `--onedir` (§11.1) el `.py` vive adentro de un archivo
    comprimido y `__file__` ya no apunta a ninguna carpeta real: los datos
    agregados con `--add-data` quedan en ``sys._MEIPASS`` (para `--onedir`, la
    subcarpeta ``_internal`` que está al lado del `.exe`). No hay descompresión
    temporal ni red de por medio: son archivos en disco, al lado del ejecutable.
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _RAIZ


RUTA_LOGO_DEFECTO = os.path.join(raiz_recursos(), "recursos", "logo.png")
DIR_FUENTES_DEFECTO = os.path.join(raiz_recursos(), "recursos", "fuentes")

#: Firma escaneada del médico (dec. 9). La imagen **ya trae** el nombre, el
#: R.I.F., el M.P.P.S. y el COMEZU debajo del trazo: por eso el informe no
#: vuelve a escribirlos abajo, sería decir dos veces lo mismo.
RUTA_FIRMA_DEFECTO = os.path.join(raiz_recursos(), "recursos", "firma.png")

LOGO_PROPORCION = 713 / 562      # recursos/logo.png  = 713 x 562 px
FIRMA_PROPORCION = 636 / 218     # recursos/firma.png = 636 x 218 px

#: Ancho impreso de la firma (dec. 9). En el `.docx` original medía 86,8 mm,
#: pero ahí abarcaba también el bloque de datos que hoy está adentro del PNG
#: recortado; a 73 mm el trazo mide como una firma de puño y letra sobre una
#: carta y la letra chica del pie sigue leyéndose (221 ppp).
FIRMA_ANCHO_MM = 73.0

SALUD_TEXTO = "Salud y Bienestar"
CODIGO_ROTULO = "N.º"


# =============================================================================
# 5. ERRORES
# =============================================================================

class DocumentoError(Exception):
    """Error al componer cualquiera de los PDF de la aplicación."""


class RecursoFaltanteError(DocumentoError):
    """Falta el logo, la firma o alguna de las fuentes Lato.

    `pdf_recipe.RecursoFaltanteError` hereda de esta, así que atraparla acá
    alcanza para los tres documentos.
    """


# =============================================================================
# 6. FECHAS
# =============================================================================

#: Con mayúscula inicial, como el ejemplo real de la plantilla B
#: ("Maracaibo;  07 de Junio de 2026", Parte B §1).
MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")


def _partes_fecha(valor: Any) -> tuple[int, int, int] | None:
    """`(día, mes, año)` de un date/datetime, un ISO o un `dd/mm/aaaa`."""
    if valor is None:
        return None
    if hasattr(valor, "year") and hasattr(valor, "month"):
        return int(valor.day), int(valor.month), int(valor.year)
    texto = str(valor).strip()
    try:
        if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
            return int(texto[8:10]), int(texto[5:7]), int(texto[0:4])
        if len(texto) >= 10 and texto[2] == "/" and texto[5] == "/":
            return int(texto[0:2]), int(texto[3:5]), int(texto[6:10])
    except ValueError:
        return None
    return None


def formatear_fecha(valor: Any) -> str:
    """`dd/mm/aaaa`. Acepta ISO, `dd/mm/aaaa` o un date/datetime.

    Lo que no reconoce lo devuelve tal cual: el médico puede haber escrito
    "en enero" y eso se imprime, no se rompe.
    """
    partes = _partes_fecha(valor)
    if partes is None:
        return "" if valor is None else str(valor).strip()
    dia, mes, anio = partes
    return f"{dia:02d}/{mes:02d}/{anio:04d}"


def fecha_corta(valor: Any) -> str:
    """`18/08/26` — el año en dos cifras, para los ejes de los mini-gráficos.

    En un rótulo de 7 pt debajo de un gráfico de 55 mm de ancho, los dos
    dígitos del siglo no informan nada (nadie compara una medición de 2026 con
    una de 1926) y sí empujan la fecha contra la del otro extremo.
    """
    partes = _partes_fecha(valor)
    if partes is None:
        return "" if valor is None else str(valor).strip()
    dia, mes, anio = partes
    return f"{dia:02d}/{mes:02d}/{anio % 100:02d}"


def fecha_larga(valor: Any) -> str:
    """`18 de Agosto de 2026` — el pie de la carta clínica (Parte B §1)."""
    partes = _partes_fecha(valor)
    if partes is None:
        return "" if valor is None else str(valor).strip()
    dia, mes, anio = partes
    if not 1 <= mes <= 12:
        return formatear_fecha(valor)
    return f"{dia:02d} de {MESES[mes - 1]} de {anio:04d}"


def dia_ordinal(valor: Any) -> int | None:
    """Número de día absoluto de una fecha, o `None` si no se puede leer.

    Sirve para separar los puntos de un gráfico **en proporción al tiempo**:
    dos mediciones tomadas con una semana de diferencia tienen que quedar
    juntas, y no a la misma distancia que dos separadas por medio año. Con
    puntos equiespaciados, una curva de peso miente sobre la velocidad del
    cambio, que es justo lo que el médico está mirando.
    """
    partes = _partes_fecha(valor)
    if partes is None:
        return None
    dia, mes, anio = partes
    try:
        return date(anio, mes, dia).toordinal()
    except ValueError:
        return None


# =============================================================================
# 7. LIENZO: fuentes y helpers de tinta
# =============================================================================

class Lienzo(FPDF):
    """FPDF con las Lato cargadas y los helpers de texto de la marca.

    Todos los helpers trabajan con la **línea de base** del texto (`self.text`)
    y no con celdas: es lo que permitió calcar el talonario al décimo de
    milímetro, y en los documentos nuevos evita las sorpresas de altura de
    línea de `multi_cell`.
    """

    #: Qué error levanta si falta un recurso. Cada documento pone el suyo para
    #: que `rutas.py` siga distinguiendo de dónde vino el problema.
    _ERROR_RECURSO: type[Exception] = RecursoFaltanteError

    def __init__(self, dir_fuentes: str, *, orientacion: str = "P") -> None:
        super().__init__(orientation=orientacion, unit="mm", format="Letter")
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)
        self.set_compression(True)
        self._cargar_fuentes(dir_fuentes)

    # -- recursos ----------------------------------------------------------
    def _cargar_fuentes(self, dir_fuentes: str) -> None:
        for estilo, archivo in ARCHIVOS_FUENTE.items():
            ruta = os.path.join(dir_fuentes, archivo)
            if not os.path.isfile(ruta):
                raise self._ERROR_RECURSO(
                    f"Falta la fuente {archivo}. Esperada en: {ruta}"
                )
            self.add_font(FUENTE, estilo, ruta)

    # -- helpers de texto --------------------------------------------------
    def _ancho(self, texto: str, estilo: str, pt: float) -> float:
        self.set_font(FUENTE, estilo, pt)
        return self.get_string_width(texto)

    def _envolver(self, texto: str, ancho_mm: float, estilo: str,
                  pt: float) -> list[str]:
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
                            if (self.get_string_width(trozo + caracter) > ancho_mm
                                    and trozo):
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

    def _envolver_colgante(self, texto: str, ancho_primero: float,
                           ancho_resto: float, estilo: str,
                           pt: float) -> list[str]:
        """Como `_envolver`, pero el primer renglón tiene otro ancho.

        Es lo que necesita un «Rótulo: valor» de varias líneas: la primera
        arranca después del rótulo y las que siguen vuelven casi al margen,
        con una sangría chica. Alinearlas debajo del valor —que es lo que sale
        si se usa un ancho único— empuja el texto media hoja a la derecha
        cuando el rótulo es largo, y se lee peor que el papel.
        """
        self.set_font(FUENTE, estilo, pt)
        renglones: list[str] = []
        for parrafo in str(texto).replace("\r\n", "\n").split("\n"):
            palabras = [p for p in parrafo.split(" ") if p]
            if not palabras:
                renglones.append("")
                continue
            actual = ""
            for palabra in palabras:
                limite = ancho_primero if not renglones else ancho_resto
                tanteo = palabra if not actual else f"{actual} {palabra}"
                if self.get_string_width(tanteo) <= limite:
                    actual = tanteo
                    continue
                if actual:
                    renglones.append(actual)
                    actual = ""
                    limite = ancho_resto
                # Palabra sola más ancha que la columna: se corta duro, igual
                # que en `_envolver` (un correo largo, una URL).
                trozos = self._envolver(palabra, limite, estilo, pt)
                self.set_font(FUENTE, estilo, pt)
                renglones.extend(trozos[:-1])
                actual = trozos[-1] if trozos else ""
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

    def _texto_centrado(self, x0: float, x1: float, base_y: float, texto: str,
                        estilo: str, pt: float,
                        color: tuple[int, int, int]) -> float:
        """Centrado **de verdad**, midiendo el texto.

        La plantilla `.docx` lo hacía empujando el título con unos setenta
        espacios en blanco (Parte B §1), que es lo que se rompe apenas cambia
        la fuente. Acá se mide y se centra.
        """
        ancho = self._ancho(texto, estilo, pt)
        self._texto(x0 + (x1 - x0 - ancho) / 2.0, base_y, texto, estilo, pt, color)
        return ancho

    def _texto_a_ancho(self, x: float, base_y: float, texto: str, estilo: str,
                       pt: float, color: tuple[int, int, int],
                       ancho_mm: float) -> None:
        """Escribe `texto` estirando el interletrado hasta ocupar `ancho_mm`.

        Es lo que hace el talonario con "Salud y Bienestar": mismo cuerpo que
        el resto pero tracking apenas abierto para llegar al ancho del logo.
        """
        natural = self._ancho(texto, estilo, pt)
        huecos = max(len(texto) - 1, 1)
        # set_char_spacing trabaja en puntos tipograficos
        extra_pt = (ancho_mm - natural) / huecos / PT_A_MM
        self.set_char_spacing(extra_pt)
        self._texto(x, base_y, texto, estilo, pt, color)
        self.set_char_spacing(0)

    # -- volver sobre una página ya escrita --------------------------------
    def _ir_a_pagina(self, numero: int) -> None:
        """Se para en una página **ya escrita** para agregarle algo (el pie).

        Y le avisa a fpdf2 que tiene que volver a declarar la fuente.

        Por qué hace falta: fpdf2 lleva la cuenta de la fuente vigente **por
        documento y no por página**. `text()` escribe el operador `Tf` en el
        contenido de la hoja solo la primera vez que se usa una fuente
        (`current_font_is_set_on_page`) y después confía en que sigue puesta;
        `set_font` ni siquiera entra si le vuelven a pedir lo mismo. Mover
        `self.page` a mano —que es lo que hace la numeración de páginas— la
        biblioteca no lo ve.

        Sin esto, el pie de la página 1 sale bien (ahí la fuente sí cambia y
        se declara) y el de todas las que siguen se dibuja con **el cuerpo de
        letra que haya quedado escrito en ESA hoja**: 11 pt en una historia,
        10,5 o 9,5 pt en un informe. Como el ancho para alinearlo a la derecha
        se midió con el cuerpo correcto, «Página 2 de 3» terminaba hasta 5 mm
        afuera de la guía derecha, y más grande que el de la primera hoja.

        Se le borra el cuerpo vigente —ningún helper de este módulo llama a
        `set_font` sin decir el tamaño— y de paso se baja la bandera que usa
        fpdf2 ≥ 2.7.5; con cualquiera de las dos alcanza, y así el arreglo no
        depende de la versión de la biblioteca.
        """
        self.page = numero
        self.font_size_pt = 0.0
        self.current_font_is_set_on_page = False

    # -- helpers de trazo --------------------------------------------------
    def _raya(self, x0: float, x1: float, y: float, grosor: float,
              color: tuple[int, int, int] = GRIS_ROTULO) -> None:
        self.set_draw_color(*color)
        self.set_line_width(grosor)
        self.line(x0, y, x1, y)

    def _recuadro(self, x0: float, y0: float, x1: float, y1: float,
                  grosor: float = GROSOR_RECUADRO_MM,
                  color: tuple[int, int, int] = GRIS_RECUADRO) -> None:
        """La caja fina gris de las plantillas de informe (Parte B §3)."""
        self.set_draw_color(*color)
        self.set_line_width(grosor)
        self.rect(x0, y0, x1 - x0, y1 - y0, style="D")

    # -- bloques de marca ---------------------------------------------------
    def _logo(self, ruta: str, x: float, y: float, ancho_mm: float) -> float:
        """Pega el lockup «símbolo + espacio CORPORAL». Devuelve su alto."""
        alto = ancho_mm / LOGO_PROPORCION
        self.image(ruta, x=x, y=y, w=ancho_mm, h=alto)
        return alto

    def _codigo_der(self, x_der: float, base_y: float, codigo: str, *,
                    pt_codigo: float, pt_rotulo: float, separacion: float,
                    color: tuple[int, int, int] = GRIS_ROTULO) -> float:
        """«N.º EC-0001» pegado a la guía derecha (dec. 7).

        El código es el **del paciente** y es el mismo en todo lo que se le
        imprime: récipe, informe e historia. Devuelve el ancho total ocupado.
        """
        ancho_cod = self._texto_der(x_der, base_y, codigo, "B", pt_codigo, color)
        ancho_rot = self._texto_der(x_der - ancho_cod - separacion, base_y,
                                    CODIGO_ROTULO, "", pt_rotulo, color)
        return ancho_cod + separacion + ancho_rot


# =============================================================================
# 8. HOJA CARTA VERTICAL: membrete, cursor y salto de página
# =============================================================================
# El récipe no pasa por acá (ver el encabezado del módulo). Esto es para la
# historia y los informes, que son documentos de largo libre: un informe de
# tres páginas es legítimo, no un error.

MARGEN_IZQ_MM = 20.0
MARGEN_DER_MM = 20.0
GUIA_DER_MM = CARTA_ANCHO_MM - MARGEN_DER_MM      # 195,9
ANCHO_UTIL_MM = GUIA_DER_MM - MARGEN_IZQ_MM       # 175,9

#: Membrete: el mismo lockup del récipe, agrandado a la proporción de la hoja
#: entera. En la media carta el logo mide 21,7 mm sobre 139,7 de ancho; acá
#: 26 mm sobre 215,9 es apenas más discreto, que es lo que pide una carta.
LOGO_X_MM = MARGEN_IZQ_MM
LOGO_Y_MM = 16.0
LOGO_ANCHO_MM = 26.0

SALUD_BASE_Y_MM = 43.0
SALUD_PT = 11.5
SALUD_ANCHO_MM = 39.0            # 1,5 x el ancho del logo, como en el talonario

CODIGO_BASE_Y_MM = 22.6          # misma altura relativa que en el récipe
CODIGO_PT = 13.0
CODIGO_ROTULO_PT = 11.0
CODIGO_SEPARACION_MM = 1.8

#: Filete teal bajo el membrete. En el récipe la marca se cierra con el
#: ornamento lateral; acá no hay ornamento (ver `pdf_informe`), así que el
#: filete es lo que le da pie al encabezado y separa la carta de su membrete.
FILETE_Y_MM = 48.5
FILETE_GROSOR_MM = 0.6

CUERPO_Y0_MM = 58.0              # primera línea de base del cuerpo
CUERPO_Y1_MM = 262.0             # último renglón antes del pie de página
PIE_BASE_Y_MM = 270.0

INTERLINEA_MM = 5.0
PT_CUERPO = 11.0
PT_ROTULO = 11.0

#: Sangría francesa de los campos «Rótulo: valor» de varias líneas.
SANGRIA_COLGANTE_MM = 4.0

#: Celdas de las tablas de recuadro fino: rótulo chico arriba, valor debajo.
PT_ROTULO_CELDA = 8.5
CELDA_PAD_MM = 1.8               # aire interno
CELDA_ROTULO_ALTO_MM = 3.8       # lo que baja el rótulo antes del valor

# -----------------------------------------------------------------------------
# 8.1 MINI-GRAFICOS DE EVOLUCION (dec. 13 ampliada)
# -----------------------------------------------------------------------------
# Un mini-gráfico de línea, vectorial, dibujado con las primitivas de fpdf2
# (`line` y `circle`): nada de imágenes, nada de matplotlib, nada de red — la
# aplicación no suma dependencias (§ prohibiciones del proyecto). Como es
# vectorial, se imprime nítido a cualquier tamaño y pesa unos pocos cientos de
# bytes por gráfico, no los 40 KB de un PNG.
#
# La forma es la de un *small multiple*: varios gráficos chiquitos, iguales
# entre sí, uno por métrica. En una historia clínica eso vale más que un solo
# gráfico grande con cinco curvas encimadas, porque las unidades no son
# comparables (kg contra % contra un índice sin unidad) y superponerlas obliga
# a cinco escalas o a normalizar, que es exactamente donde un gráfico clínico
# empieza a mentir. Cada métrica con su escala propia, ajustada a sus mínimo y
# máximo: lo que se lee es **la forma de la tendencia**, y por eso los extremos
# del eje Y van rotulados — sin ellos, una variación de 300 gramos se vería
# igual de dramática que una de veinte kilos.

GRAFICO_TITULO_MM = 3.0          # del borde superior del bloque a la base del título
#: Del título al techo del trazado. Tienen que ser suficientes: el rótulo del
#: máximo del eje Y queda a la izquierda pero a la MISMA altura que el techo, y
#: con menos aire se le monta al título, que es más ancho que la columna de
#: rótulos.
GRAFICO_AIRE_TITULO_MM = 2.8
GRAFICO_TRAMA_ALTO_MM = 24.0     # alto del área de trazado
GRAFICO_FECHAS_MM = 3.6          # del piso del trazado a la base de las fechas
GRAFICO_COLA_MM = 1.2            # aire al pie del bloque

#: Ancho reservado a la izquierda para los rótulos del eje Y, y a la derecha
#: para el valor de la última medición en negrita.
GRAFICO_ETIQUETA_MM = 12.0
GRAFICO_VALOR_MM = 16.0
GRAFICO_AIRE_ETIQUETA_MM = 1.6   # entre el rótulo del eje Y y el eje
GRAFICO_AIRE_VALOR_MM = 2.0      # entre el último punto y su valor

GRAFICO_PT_TITULO = 8.5
GRAFICO_PT_EJE = 7.0
GRAFICO_PT_VALOR = 8.0

GRAFICO_GROSOR_MM = 0.4          # la línea de datos
GRAFICO_GROSOR_EJE_MM = 0.15
GRAFICO_GROSOR_GRILLA_MM = 0.1
GRAFICO_PUNTO_R_MM = 0.65
#: A partir de acá los puntos se achican para que no se toquen entre sí: con
#: cuarenta mediciones en 55 mm quedan a 1,4 mm uno de otro.
GRAFICO_PUNTOS_APRETADOS = 14
GRAFICO_PUNTO_R_CHICO_MM = 0.45


def alto_mini_grafico(alto_trama: float = GRAFICO_TRAMA_ALTO_MM) -> float:
    """Alto total que ocupa un mini-gráfico: título + trazado + fechas."""
    return (GRAFICO_TITULO_MM + GRAFICO_AIRE_TITULO_MM + alto_trama
            + GRAFICO_FECHAS_MM + GRAFICO_COLA_MM)


def _abscisas(px0: float, px1: float, cantidad: int,
              posiciones: Sequence[Any] | None = None) -> list[float]:
    """Dónde cae en X cada punto, en proporción al tiempo si se puede.

    `posiciones` son valores numéricos crecientes (los ordinales de las fechas,
    ver `dia_ordinal`). Si faltan, si vienen incompletos o si todas las
    mediciones cayeron el mismo día —caso en que la proporción no está
    definida—, se reparten equiespaciados, que es lo único razonable que queda.
    """
    if cantidad <= 0:
        return []
    if cantidad == 1:
        return [(px0 + px1) / 2.0]
    if posiciones is not None and len(posiciones) == cantidad:
        try:
            crudas = [float(p) for p in posiciones]
        except (TypeError, ValueError):
            crudas = []
        if crudas and max(crudas) > min(crudas):
            bajo, alto = min(crudas), max(crudas)
            return [px0 + (p - bajo) / (alto - bajo) * (px1 - px0)
                    for p in crudas]
    paso = (px1 - px0) / (cantidad - 1)
    return [px0 + i * paso for i in range(cantidad)]


class HojaCarta(Lienzo):
    """Carta vertical con membrete repetido y un cursor que baja solo.

    Uso: `nueva_pagina()` una vez y después `parrafo`, `rotulo`, `espacio`…
    Cuando el cursor pasa de `CUERPO_Y1_MM` se abre una página nueva **con el
    membrete puesto**, así una hoja suelta de un informe largo sigue diciendo
    de quién es y qué código de paciente lleva.
    """

    def __init__(self, ruta_logo: str, dir_fuentes: str, codigo: str = "") -> None:
        super().__init__(dir_fuentes, orientacion="P")
        self.ruta_logo = ruta_logo
        self.codigo = str(codigo or "").strip()
        self.pluma_y = CUERPO_Y0_MM

    # -- membrete ----------------------------------------------------------
    def _membrete(self) -> None:
        """Logo + "Salud y Bienestar" + «N.º EC-0001» + filete (dec. 7 y 8).

        Es Espacio Corporal, no la Unidad Médico Quirúrgica de las plantillas
        `.docx` de referencia (dec. 8).
        """
        self._logo(self.ruta_logo, LOGO_X_MM, LOGO_Y_MM, LOGO_ANCHO_MM)
        self._texto_a_ancho(LOGO_X_MM - 0.5, SALUD_BASE_Y_MM, SALUD_TEXTO,
                            "", SALUD_PT, TEAL_OSCURO, SALUD_ANCHO_MM)
        if self.codigo:
            self._codigo_der(GUIA_DER_MM, CODIGO_BASE_Y_MM, self.codigo,
                             pt_codigo=CODIGO_PT, pt_rotulo=CODIGO_ROTULO_PT,
                             separacion=CODIGO_SEPARACION_MM)
        self._raya(MARGEN_IZQ_MM, GUIA_DER_MM, FILETE_Y_MM,
                   FILETE_GROSOR_MM, TEAL_MEDIO)

    def nueva_pagina(self) -> None:
        self.add_page()
        self._membrete()
        self.pluma_y = CUERPO_Y0_MM

    # -- cursor ------------------------------------------------------------
    def asegurar(self, alto_mm: float) -> None:
        """Abre página nueva si lo que sigue no entra en lo que queda."""
        if self.page == 0:
            self.nueva_pagina()
        elif self.pluma_y + alto_mm > CUERPO_Y1_MM:
            self.nueva_pagina()

    def espacio(self, alto_mm: float) -> None:
        """Aire vertical. Nunca abre página sola: un hueco al pie no vale una hoja."""
        self.pluma_y += alto_mm

    def parrafo(self, texto: str, *, estilo: str = "", pt: float = PT_CUERPO,
                color: tuple[int, int, int] = GRIS_DATO,
                x: float = MARGEN_IZQ_MM, ancho: float | None = None,
                interlinea: float = INTERLINEA_MM) -> None:
        """Escribe texto envuelto, cortando de página cuando hace falta."""
        texto = str(texto or "").strip()
        if not texto:
            return
        ancho = ANCHO_UTIL_MM - (x - MARGEN_IZQ_MM) if ancho is None else ancho
        for renglon in self._envolver(texto, ancho, estilo, pt):
            self.asegurar(interlinea)
            self._texto(x, self.pluma_y, renglon, estilo, pt, color)
            self.pluma_y += interlinea

    def rotulo(self, texto: str, *, pt: float = PT_ROTULO,
               color: tuple[int, int, int] = TEAL_OSCURO) -> None:
        """Rótulo de sección: bold teal. Se pega a lo que viene abajo."""
        # 2,2 interlíneas de reserva: un rótulo solo al pie de la hoja, con su
        # contenido en la página siguiente, es peor que un renglón desperdiciado.
        self.asegurar(INTERLINEA_MM * 2.2)
        self._texto(MARGEN_IZQ_MM, self.pluma_y, texto, "B", pt, color)
        self.pluma_y += INTERLINEA_MM

    def campo(self, rotulo: str, valor: str, *, pt: float = PT_CUERPO,
              sangria: float = 0.0) -> None:
        """«Rótulo: valor» con el rótulo en negrita y el valor envuelto.

        El primer renglón arranca después del rótulo; los que siguen vuelven al
        margen del campo con una sangría chica (sangría francesa), así el valor
        no se va media hoja a la derecha cuando el rótulo es largo.
        """
        valor = str(valor or "").strip()
        if not valor:
            return
        x = MARGEN_IZQ_MM + sangria
        ancho_rot = self._ancho(f"{rotulo} ", "B", pt)
        renglones = self._envolver_colgante(
            valor, GUIA_DER_MM - x - ancho_rot,
            GUIA_DER_MM - x - SANGRIA_COLGANTE_MM, "", pt)
        for i, renglon in enumerate(renglones):
            self.asegurar(INTERLINEA_MM)
            if i == 0:
                self._texto(x, self.pluma_y, rotulo, "B", pt, TEAL_OSCURO)
                self._texto(x + ancho_rot, self.pluma_y, renglon, "", pt,
                            GRIS_DATO)
            else:
                self._texto(x + SANGRIA_COLGANTE_MM, self.pluma_y, renglon, "",
                            pt, GRIS_DATO)
            self.pluma_y += INTERLINEA_MM

    # -- tablas de recuadro fino -------------------------------------------
    def _alto_celda(self, rotulo: str, valor: str, ancho: float) -> float:
        renglones = self._envolver(valor or "", ancho - 2 * CELDA_PAD_MM,
                                   "", PT_CUERPO) or [""]
        alto = CELDA_PAD_MM + (CELDA_ROTULO_ALTO_MM if rotulo else 0.0)
        return alto + len(renglones) * INTERLINEA_MM + CELDA_PAD_MM * 0.6

    def fila_recuadro(self, celdas: Sequence[tuple[str, str, float]]) -> None:
        """Una fila de celdas con recuadro fino gris, que crece con el texto.

        `celdas` es ``(rótulo, valor, fracción del ancho)``. El rótulo va
        chiquito arriba y el valor debajo, igual que en las plantillas de
        informe — lo que cambia es que acá la caja se estira si el valor no
        entra en un renglón (en el `.docx` era de alto fijo y se desbordaba).

        La usan la cabecera del médico y los datos de la prestación del
        informe, y la ficha y los signos vitales de la historia.
        """
        anchos = [max(f, 0.0) * ANCHO_UTIL_MM for _, _, f in celdas]
        alto = max((self._alto_celda(r, v, a)
                    for (r, v, _), a in zip(celdas, anchos)), default=0.0)
        if alto <= 0.0:
            return
        self.asegurar(alto)
        y0 = self.pluma_y - INTERLINEA_MM * 0.8
        self._recuadro(MARGEN_IZQ_MM, y0, GUIA_DER_MM, y0 + alto)

        x = MARGEN_IZQ_MM
        for (rotulo, valor, _), ancho in zip(celdas, anchos):
            if x > MARGEN_IZQ_MM + 0.01:
                self.set_draw_color(*GRIS_RECUADRO)
                self.set_line_width(GROSOR_RECUADRO_MM)
                self.line(x, y0, x, y0 + alto)
            y = self.pluma_y
            if rotulo:
                self._texto(x + CELDA_PAD_MM, y, rotulo, "", PT_ROTULO_CELDA,
                            GRIS_ROTULO)
                y += CELDA_ROTULO_ALTO_MM
            for renglon in self._envolver(valor or "", ancho - 2 * CELDA_PAD_MM,
                                          "", PT_CUERPO):
                self._texto(x + CELDA_PAD_MM, y, renglon, "", PT_CUERPO, GRIS_DATO)
                y += INTERLINEA_MM
            x += ancho
        self.pluma_y = y0 + alto + INTERLINEA_MM * 0.8

    # -- mini-gráficos -----------------------------------------------------
    def mini_grafico(self, x: float, y: float, ancho: float, titulo: str,
                     puntos: Sequence[tuple[str, float]], *,
                     posiciones: Sequence[Any] | None = None,
                     alto_trama: float = GRAFICO_TRAMA_ALTO_MM,
                     formato: Callable[[float], str] | None = None) -> float:
        """Dibuja un gráfico de línea chiquito y devuelve el alto que ocupó.

        `x`, `y` son la esquina **superior izquierda** del bloque y `ancho` lo
        que puede ocupar de lado a lado. `puntos` es ``(etiqueta, valor)`` en
        orden cronológico; de las etiquetas solo se imprimen la primera y la
        última, que es lo que ubica al lector en el tiempo sin llenar de texto
        un gráfico de cinco centímetros. `posiciones` separa los puntos en
        proporción al tiempo (ver `_abscisas`).

        **No mueve `pluma_y` ni abre página**: el que llama decide dónde va y
        reserva el lugar con `asegurar(alto_mini_grafico())` antes de dibujar.
        Es a propósito — los gráficos se acomodan de a dos por fila y eso lo
        sabe el documento, no el ladrillo.

        Todo lo que dibuja queda dentro de la caja `(x, y, ancho, alto)`,
        incluido el valor final en negrita, que se corre hacia adentro si no
        entra a la derecha del último punto.
        """
        formato = formato or (lambda v: f"{v:.1f}".replace(".", ","))
        datos: list[tuple[str, float]] = []
        for etiqueta, valor in puntos:
            try:
                datos.append((str(etiqueta or ""), float(valor)))
            except (TypeError, ValueError):
                continue
        alto = alto_mini_grafico(alto_trama)
        if not datos:
            return 0.0

        self._texto(x, y + GRAFICO_TITULO_MM, titulo, "B", GRAFICO_PT_TITULO,
                    TEAL_OSCURO)

        techo = y + GRAFICO_TITULO_MM + GRAFICO_AIRE_TITULO_MM
        piso = techo + alto_trama
        px0 = x + GRAFICO_ETIQUETA_MM
        px1 = x + ancho - GRAFICO_VALOR_MM
        if px1 <= px0:            # caja imposible: mejor el título solo
            return alto

        valores = [v for _, v in datos]
        minimo, maximo = min(valores), max(valores)
        rango = maximo - minimo

        def altura(valor: float) -> float:
            """Y del valor. Serie plana: la línea va por el medio del cuadro."""
            if rango <= 0:
                return techo + alto_trama / 2.0
            return piso - (valor - minimo) / rango * alto_trama

        equis = _abscisas(px0, px1, len(datos), posiciones)

        # Grilla al techo y a media altura, y los dos ejes. La grilla es
        # apenas más clara que el papel: tiene que dejarse ver cuando se la
        # busca y desaparecer cuando se mira la curva.
        self._raya(px0, px1, techo, GRAFICO_GROSOR_GRILLA_MM, GRIS_CORTE)
        self._raya(px0, px1, techo + alto_trama / 2.0,
                   GRAFICO_GROSOR_GRILLA_MM, GRIS_CORTE)
        self._raya(px0, px1, piso, GRAFICO_GROSOR_EJE_MM, GRIS_ROTULO)
        self.set_draw_color(*GRIS_ROTULO)
        self.set_line_width(GRAFICO_GROSOR_EJE_MM)
        self.line(px0, techo, px0, piso)

        # Extremos del eje Y. Sin ellos el gráfico no dice nada: media curva
        # de bajada puede ser medio kilo o veinte.
        x_etiqueta = px0 - GRAFICO_AIRE_ETIQUETA_MM
        if rango > 0:
            self._texto_der(x_etiqueta, techo + 1.0, formato(maximo), "",
                            GRAFICO_PT_EJE, GRIS_ROTULO)
            self._texto_der(x_etiqueta, piso + 1.0, formato(minimo), "",
                            GRAFICO_PT_EJE, GRIS_ROTULO)
        else:
            self._texto_der(x_etiqueta, altura(minimo) + 1.0, formato(minimo),
                            "", GRAFICO_PT_EJE, GRIS_ROTULO)

        # La línea y sus puntos.
        self.set_draw_color(*TEAL_MEDIO)
        self.set_line_width(GRAFICO_GROSOR_MM)
        for i in range(1, len(datos)):
            self.line(equis[i - 1], altura(valores[i - 1]),
                      equis[i], altura(valores[i]))
        radio = (GRAFICO_PUNTO_R_MM if len(datos) <= GRAFICO_PUNTOS_APRETADOS
                 else GRAFICO_PUNTO_R_CHICO_MM)
        self.set_fill_color(*TEAL_MEDIO)
        for punto_x, valor in zip(equis, valores):
            self.circle(punto_x, altura(valor), radio, style="F")

        # Primera y última fecha.
        base_fechas = piso + GRAFICO_FECHAS_MM
        self._texto(px0, base_fechas, datos[0][0], "", GRAFICO_PT_EJE,
                    GRIS_ROTULO)
        if len(datos) > 1 and datos[-1][0] != datos[0][0]:
            self._texto_der(px1, base_fechas, datos[-1][0], "",
                            GRAFICO_PT_EJE, GRIS_ROTULO)

        # El valor de la última medición, en negrita, pegado a su punto: es el
        # dato que el médico busca primero y el único que va a leer en voz
        # alta frente al paciente.
        ultimo = formato(valores[-1])
        ancho_ultimo = self._ancho(ultimo, "B", GRAFICO_PT_VALOR)
        self._texto(min(px1 + GRAFICO_AIRE_VALOR_MM, x + ancho - ancho_ultimo),
                    min(max(altura(valores[-1]) + 1.0, techo + 1.0), piso + 1.0),
                    ultimo, "B", GRAFICO_PT_VALOR, TEAL_OSCURO)
        return alto

    # -- pie ---------------------------------------------------------------
    def numerar_paginas(self) -> None:
        """«Página 2 de 3» al pie, solo si el documento tiene más de una.

        Se hace al final, cuando ya se sabe el total, volviendo a cada página
        con `_ir_a_pagina` (que es `self.page` **más** el aviso a fpdf2 de que
        vuelva a declarar la fuente; ver ahí por qué). En un informe entregado
        a una aseguradora, saber que faltan hojas es la diferencia entre un
        trámite y un reclamo.
        """
        total = self.page
        if total < 2:
            return
        actual = self.page
        for numero in range(1, total + 1):
            self._ir_a_pagina(numero)
            self._texto_der(GUIA_DER_MM, PIE_BASE_Y_MM,
                            f"Página {numero} de {total}", "", 8.5, GRIS_ROTULO)
        self._ir_a_pagina(actual)


# =============================================================================
# 9. IMAGENES
# =============================================================================

def medidas_imagen(ruta: str) -> tuple[int, int]:
    """`(ancho, alto)` en píxeles. Levanta `RecursoFaltanteError` si no está.

    Usa Pillow, que ya es dependencia (la usa `rutas.py` para el logo). Si por
    lo que sea no estuviera, se devuelve una proporción vertical razonable
    antes que romper el documento: la imagen se pegaría igual, apenas menos
    ajustada a la caja.
    """
    if not os.path.isfile(ruta):
        raise RecursoFaltanteError(
            f"No encuentro el archivo de la imagen. Lo buscaba en: {ruta}"
        )
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow es dependencia de la app
        return (909, 1280)
    try:
        with Image.open(ruta) as imagen:
            return (int(imagen.size[0]), int(imagen.size[1]))
    except Exception as err:
        raise RecursoFaltanteError(
            f"No pude leer la imagen «{os.path.basename(ruta)}»: no parece un "
            f"archivo de imagen válido. ({type(err).__name__})"
        ) from err


def encajar(ancho_px: int, alto_px: int, ancho_mm: float,
            alto_mm: float) -> tuple[float, float]:
    """Tamaño impreso que entra en la caja conservando la proporción."""
    if ancho_px <= 0 or alto_px <= 0:
        return ancho_mm, alto_mm
    escala = min(ancho_mm / ancho_px, alto_mm / alto_px)
    return ancho_px * escala, alto_px * escala


def catmull_abierto(puntos: Sequence[tuple[float, float]]):
    """Convierte una polilínea en tramos Bézier cúbicos que pasan por los puntos.

    Vive acá porque es geometría pura y no tiene nada de récipe, pero hoy la
    usa **solo** el ornamento del talonario.
    """
    p = [puntos[0], *puntos, puntos[-1]]
    tramos = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        tramos.append((c1, c2, p2))
    return tramos


def catmull_cerrado(puntos: Sequence[tuple[float, float]]):
    """Igual que `catmull_abierto` pero el anillo se cierra sobre sí mismo."""
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
