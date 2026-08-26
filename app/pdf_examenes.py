# -*- coding: utf-8 -*-
"""Composición del PDF de la orden de análisis — Espacio Corporal (§3 de la 2.1).

Misma hoja que el récipe: UNA página carta apaisada (279,4 x 215,9 mm) con dos
mitades de media carta vertical separadas por la línea de corte punteada. Lo
único que cambia es qué dice cada mitad:

  - Mitad izquierda, rótulo **`Solicito:`** — la lista numerada de análisis con
    su tipo de muestra a la derecha del renglón. Es la mitad que se entrega en
    el laboratorio, así que no lleva nada más.
  - Mitad derecha, rótulo **`Ind.`** — cada análisis repetido con SU MISMO
    NÚMERO y debajo su preparación; después, separado, el bloque de
    indicaciones generales. Es la que se lleva el paciente.

El módulo es **puro**: no toca la base de datos, no lee configuración y no
escribe nada más que el PDF pedido.

    from app.pdf_examenes import (generar_examenes, medir_contenido,
                                  ContenidoNoCabeError, NombreNoCabeError)

Cómo se relaciona con `pdf_recipe` (regla dura del contrato)
------------------------------------------------------------
`_OrdenExamenes` **subclasa `pdf_recipe._Recipe`** y hereda tal cual el
ornamento, la línea de corte, el encabezado, la colegiatura, el renglón
`Paciente:`/`Fecha:` y el ajuste del nombre. Acá no se copia ni un número de la
geometría del talonario: todo lo que hace falta se importa de `pdf_recipe`. Lo
único que se reescribe son `componer()` y los dos cuerpos, que es donde de
verdad cambia el documento.

`pdf_recipe` **no se toca**: su salida no cambia ni un punto y
`tests/test_pdf_recipe.py` es la red que lo verifica.

Medición del rótulo `Solicito:` (lo que pide el contrato, §3)
--------------------------------------------------------------
`Solicito:` es mucho más ancho que `Rp.`, así que se midió de verdad, con la
Lato Bold Italic embebida y a `PT_RP` (20 pt):

    ancho de «Solicito:»  = 23,79 mm   (contra 9,72 mm de «Rp.»)
    arranca en RP_X_MM    = 16,15 mm   ->  muere en 39,94 mm

Con eso no se solapa con nada:

  * el bloque «N.º EC-0001» de la derecha nace en 101,14 mm (guía derecha
    126,40 menos sus 25,26 mm de ancho): quedan **61,19 mm** de aire, y encima
    va en otra línea de base (22,60 contra 51,90);
  * el logo ocupa x 16,40 -> 38,10 pero muere en y = 33,00, y la mayúscula del
    rótulo arranca en y = 46,84 (base 51,90 menos la cap de Lato a 20 pt,
    5,06 mm): **13,84 mm** de aire vertical, con «Salud y Bienestar» (base
    40,10) en el medio y sin tocarse;
  * el primer renglón del cuerpo apoya en 60,60, muy por debajo del rótulo.

Y remedido sobre el PDF ya generado (cajas reales de los glifos, que son un
poco más altas que la cap porque incluyen ascendentes y descendentes):

    «Solicito:»          x 16,15 -> 39,94    y 44,94 -> 53,40
    logo (mitad izq.)    x 16,40 -> 38,10    y 15,90 -> 33,01   -> 11,93 mm
    «Salud y Bienestar»  x 15,90 -> 48,48    y 35,92 -> 41,00   ->  3,94 mm
    «N.º EC-0001»        x 101,13 -> 126,40  y 18,07 -> 23,58   -> 61,19 mm
    primer renglón       x 22,60 -> …        y 56,60 -> 61,46   ->  3,20 mm

O sea que **entra a PT_RP y no hubo que bajarle el cuerpo**: se usa el
`_encabezado` heredado sin tocarlo. `medidas_rotulo()` rehace esa cuenta en
caliente y `tests/test_pdf_examenes.py` la verifica, para que si algún día
cambia la fuente o la guía, el que se entere sea la suite y no el papel.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

try:  # como paquete (``from app import pdf_examenes``)
    from . import pdf_comun, pdf_recipe
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import pdf_comun  # type: ignore[no-redef]
    import pdf_recipe  # type: ignore[no-redef]

# =============================================================================
# 1. GEOMETRIA — toda importada, ninguna copiada
# =============================================================================
# Se reexportan con el mismo nombre para que la interfaz y las pruebas puedan
# pedírselas a este módulo sin tener que saber que abajo hay un récipe. Son
# **las mismas** constantes: si alguna cambia allá, cambia acá.

MARGEN_IZQ_MM = pdf_recipe.MARGEN_IZQ_MM
GUIA_DER_MM = pdf_recipe.GUIA_DER_MM
SANGRIA_MM = pdf_recipe.SANGRIA_MM
INTERLINEA_MM = pdf_recipe.INTERLINEA_MM
SEPARACION_ITEM_MM = pdf_recipe.SEPARACION_ITEM_MM
SEPARACION_GENERAL_MM = pdf_recipe.SEPARACION_GENERAL_MM
CUERPO_Y0_MM = pdf_recipe.CUERPO_Y0_MM

MITAD_ANCHO_MM = pdf_recipe.MITAD_ANCHO_MM
PAGINA_ANCHO_MM = pdf_recipe.PAGINA_ANCHO_MM
PAGINA_ALTO_MM = pdf_recipe.PAGINA_ALTO_MM

PT_CUERPO = pdf_recipe.PT_CUERPO
PT_CUERPO_MENOR = pdf_recipe.PT_CUERPO_MENOR
PT_RP = pdf_recipe.PT_RP

GRIS_DATO = pdf_recipe.GRIS_DATO

PIE_RP = pdf_recipe.PIE_RP
PIE_IND = pdf_recipe.PIE_IND

LOGO_X_MM = pdf_recipe.LOGO_X_MM
SALUD_X_MM = pdf_recipe.SALUD_X_MM
RP_X_MM = pdf_recipe.RP_X_MM
LOGO_X_IND_MM = pdf_recipe.LOGO_X_IND_MM
SALUD_X_IND_MM = pdf_recipe.SALUD_X_IND_MM
RP_X_IND_MM = pdf_recipe.RP_X_IND_MM

ALTO_DISPONIBLE_RP_MM = pdf_recipe.ALTO_DISPONIBLE_RP_MM
ALTO_DISPONIBLE_IND_MM = pdf_recipe.ALTO_DISPONIBLE_IND_MM

RUTA_LOGO_DEFECTO = pdf_recipe.RUTA_LOGO_DEFECTO
DIR_FUENTES_DEFECTO = pdf_recipe.DIR_FUENTES_DEFECTO

_RAIZ = pdf_recipe._RAIZ

#: Acepta 'dd/mm/aaaa', ISO 'aaaa-mm-dd' o un date/datetime.
_formatear_fecha = pdf_comun.formatear_fecha

# -----------------------------------------------------------------------------
# Lo propio de esta orden (no es geometría del talonario: es el reparto de la
# columna del cuerpo, que es justo lo que este módulo reescribe).
# -----------------------------------------------------------------------------

ROTULO_SOLICITO = "Solicito:"    # mitad izquierda — la que va al laboratorio
ROTULO_IND = "Ind."              # mitad derecha  — la que se lleva el paciente

#: Cómo se nombra cada mitad en los mensajes de error y en `rutas.py`. Sin los
#: dos puntos, que ahí adentro se leerían como puntuación de la frase.
MITAD_SOLICITO = "Solicito"
MITAD_IND = ROTULO_IND

#: Aire entre el nombre del análisis y su muestra, alineada a la derecha del
#: renglón. Es el mismo hueco con el que el récipe separa el medicamento de su
#: cantidad, que ocupa ese mismo lugar de la columna.
AIRE_MUESTRA_MM = 4.0


# =============================================================================
# 2. ERRORES
# =============================================================================
# Mismo molde que los del récipe: `rutas.py` engancha un manejador de Flask a
# CADA tipo y responde un texto distinto, así que la orden de exámenes necesita
# su propia familia aunque el mensaje sea el mismo. Todas cuelgan del tronco
# común (`pdf_comun.DocumentoError`), así un `except pdf_comun.DocumentoError`
# las atrapa a todas.

class ExamenesError(pdf_comun.DocumentoError):
    """Error al componer el PDF de la orden de exámenes."""


class RecursoFaltanteError(pdf_comun.RecursoFaltanteError, ExamenesError):
    """Falta el logo o alguna de las fuentes Lato."""


class ContenidoNoCabeError(ExamenesError):
    """El texto no entra en el cuerpo libre de una de las mitades.

    Trae los milímetros usados y disponibles para que la interfaz pueda decir
    algo útil antes de generar, exactamente igual que la del récipe.
    """

    def __init__(self, mitad: str, usado_mm: float, disponible_mm: float):
        self.mitad = mitad
        self.usado_mm = usado_mm
        self.disponible_mm = disponible_mm
        # El texto se pide prestado al récipe en vez de copiarlo: el contrato
        # manda "mismos mensajes", y así siguen siendo el mismo aunque alguna
        # vez se reescriba allá. La instancia auxiliar no se levanta: sólo se
        # le lee la frase ya armada.
        super().__init__(str(pdf_recipe.ContenidoNoCabeError(
            mitad, usado_mm, disponible_mm)))


class NombreNoCabeError(ExamenesError):
    """El nombre del paciente no entra en la raya ni abreviado.

    Un nombre cortado a la mitad en una orden impresa es un problema real, no
    cosmético: antes que emitirla así, la app frena y pide acortarlo.
    """

    def __init__(self, nombre: str, impreso: str):
        self.nombre = nombre
        self.impreso = impreso
        super().__init__(str(pdf_recipe.NombreNoCabeError(nombre, impreso)))


# =============================================================================
# 3. COMPOSITOR
# =============================================================================

class _OrdenExamenes(pdf_recipe._Recipe):
    """Lienzo de la orden. Uso interno: la API pública son las funciones de abajo.

    De `pdf_recipe._Recipe` hereda **toda** la geometría del talonario y sus
    métodos de dibujo: `_pintar_ornamento`, `_linea_corte`, `_encabezado`,
    `_colegiatura`, `_pie_paciente`, `_ancho_nombre_mm` y `_ajustar_nombre`.
    Acá sólo se reescriben `componer()` y los dos cuerpos.
    """

    #: Los manejadores de Flask de `rutas.py` esperan el error de los exámenes.
    _ERROR_RECURSO = RecursoFaltanteError

    # =====================================================================
    # MEDICION DEL ROTULO `Solicito:`  (ver el encabezado del módulo)
    # =====================================================================
    def medidas_rotulo(self, rotulo: str = ROTULO_SOLICITO,
                       rp_x: float = RP_X_MM, pt: float = PT_RP,
                       codigo: str = "EC-0001") -> dict[str, float]:
        """Mide el rótulo de la mitad izquierda y sus holguras, en mm.

        No es decorativo: `Solicito:` es dos veces y media más ancho que `Rp.`,
        y lo que hay que probar —midiendo, no a ojo— es que no se le monta al
        logo que tiene arriba a la izquierda ni al bloque «N.º EC-0001» de la
        derecha. Devuelve el ancho, dónde muere y las dos holguras; negativas
        significan solapamiento.
        """
        ancho = self._ancho(rotulo, "BI", pt)
        x1 = rp_x + ancho

        # Bloque «N.º EC-0001», pegado a la guía derecha (lo arma `_codigo_der`).
        ancho_codigo = (self._ancho(codigo, "B", pdf_recipe.PT_CODIGO)
                        + pdf_recipe.CODIGO_SEPARACION_MM
                        + self._ancho(pdf_recipe.CODIGO_ROTULO, "",
                                      pdf_recipe.PT_CODIGO_ROTULO))
        codigo_x0 = GUIA_DER_MM - ancho_codigo

        # Alto de mayúscula de la Lato = 0,7165 em; la base del rótulo está en
        # RP_BASE_Y_MM y el logo muere a LOGO_Y_MM + su alto.
        cap_mm = pt * pdf_comun.PT_A_MM * 0.7165
        techo_rotulo = pdf_recipe.RP_BASE_Y_MM - cap_mm
        pie_logo = (pdf_recipe.LOGO_Y_MM
                    + pdf_recipe.LOGO_ANCHO_MM / pdf_recipe.LOGO_PROPORCION)

        return {
            "ancho_mm": ancho,
            "x0_mm": rp_x,
            "x1_mm": x1,
            "codigo_x0_mm": codigo_x0,
            # Aire horizontal hasta el bloque del código y hasta la guía.
            "holgura_codigo_mm": codigo_x0 - x1,
            "holgura_guia_mm": GUIA_DER_MM - x1,
            # Aire vertical entre el pie del logo y el techo del rótulo.
            "holgura_logo_mm": techo_rotulo - pie_logo,
            "techo_rotulo_mm": techo_rotulo,
            "pie_logo_mm": pie_logo,
        }

    # =====================================================================
    # CUERPO — mitad `Solicito:`  (sólo qué se pide y en qué muestra)
    # =====================================================================
    def _cuerpo_solicito(self, ox: float, items: Sequence[Mapping[str, Any]],
                         dibujar: bool) -> float:
        """Lista numerada de análisis, con la muestra a la derecha del renglón.

        Nada más: esta mitad se entrega en el laboratorio y lo único que tiene
        que decir es qué procesar y con qué muestra. La preparación —que es lo
        que el paciente tiene que leer— va entera en la mitad `Ind.`.

        La muestra se alinea a la derecha contra `GUIA_DER_MM`, en el mismo
        lugar de la columna donde el récipe pone la cantidad a despachar.
        """
        x_num = ox + MARGEN_IZQ_MM
        x_txt = x_num + SANGRIA_MM
        x_der = ox + GUIA_DER_MM
        y = CUERPO_Y0_MM + INTERLINEA_MM * 0.72

        for i, item in enumerate(items, start=1):
            examen = str(item.get("examen", "") or "").strip()
            muestra = str(item.get("muestra", "") or "").strip()

            ancho_muestra = (self._ancho(muestra, "", PT_CUERPO_MENOR)
                             if muestra else 0.0)
            # El nombre del análisis nunca invade la columna de la muestra, ni
            # siquiera cuando se envuelve en varios renglones.
            ancho_titulo = (x_der - x_txt) - (ancho_muestra + AIRE_MUESTRA_MM
                                              if muestra else 0.0)

            partes = self._envolver(examen, ancho_titulo, "B", PT_CUERPO)
            if not partes:
                partes = [""]

            for k, texto in enumerate(partes):
                if k:
                    y += INTERLINEA_MM
                if dibujar:
                    if k == 0:
                        self._texto(x_num, y, f"{i}.", "B", PT_CUERPO, GRIS_DATO)
                        if muestra:
                            self._texto_der(x_der, y, muestra, "",
                                            PT_CUERPO_MENOR, GRIS_DATO)
                    self._texto(x_txt, y, texto, "B", PT_CUERPO, GRIS_DATO)

            y += INTERLINEA_MM + SEPARACION_ITEM_MM

        usado = y - SEPARACION_ITEM_MM - CUERPO_Y0_MM if items else 0.0
        return max(usado, 0.0)

    # =====================================================================
    # CUERPO — mitad `Ind.`  (todo lo que el paciente tiene que leer)
    # =====================================================================
    def _cuerpo_ind(self, ox: float, items: Sequence[Mapping[str, Any]],
                    generales: str, dibujar: bool) -> float:
        """Cada análisis repetido con su número y debajo su preparación.

        El número es el MISMO que en la mitad `Solicito:`, así el paciente
        empareja las dos mitades de un vistazo. No se repite la muestra: eso es
        asunto del laboratorio. Un análisis sin preparación se lista igual,
        sólo con su nombre — un hueco en la numeración se lee como un renglón
        perdido.

        `y` es siempre la línea de BASE del próximo renglón; al cerrar un
        bloque avanza una interlínea, de modo que al final `y - CUERPO_Y0_MM`
        es el alto ocupado (misma convención que `_cuerpo_solicito`).
        """
        x_num = ox + MARGEN_IZQ_MM
        x_txt = x_num + SANGRIA_MM
        x_der = ox + GUIA_DER_MM
        ancho_libre = x_der - x_txt
        y = CUERPO_Y0_MM + INTERLINEA_MM * 0.72
        hubo_algo = False

        for i, item in enumerate(items, start=1):
            examen = str(item.get("examen", "") or "").strip()
            indicaciones = str(item.get("indicaciones", "") or "").strip()

            partes = [(t, "B", PT_CUERPO)
                      for t in self._envolver(examen, ancho_libre, "B", PT_CUERPO)]
            if not partes:
                partes = [("", "B", PT_CUERPO)]
            if indicaciones:
                partes += [(t, "", PT_CUERPO_MENOR)
                           for t in self._envolver(indicaciones, ancho_libre, "",
                                                   PT_CUERPO_MENOR)]

            for k, (texto, estilo, pt) in enumerate(partes):
                if k:
                    y += INTERLINEA_MM
                if dibujar:
                    if k == 0:
                        self._texto(x_num, y, f"{i}.", "B", PT_CUERPO, GRIS_DATO)
                    self._texto(x_txt, y, texto, estilo, pt, GRIS_DATO)

            y += INTERLINEA_MM + SEPARACION_ITEM_MM
            hubo_algo = True

        if hubo_algo:
            y -= SEPARACION_ITEM_MM

        generales = str(generales or "").strip()
        if generales:
            if hubo_algo:
                y += SEPARACION_GENERAL_MM
            renglones = self._envolver(generales, x_der - x_num, "",
                                       PT_CUERPO_MENOR)
            for k, renglon in enumerate(renglones):
                if k:
                    y += INTERLINEA_MM
                if dibujar:
                    self._texto(x_num, y, renglon, "", PT_CUERPO_MENOR, GRIS_DATO)
            y += INTERLINEA_MM
            hubo_algo = True

        usado = (y - CUERPO_Y0_MM) if hubo_algo else 0.0
        return max(usado, 0.0)

    # =====================================================================
    # ARMADO COMPLETO
    # =====================================================================
    def componer(self, datos: Mapping[str, Any],
                 dibujar: bool = True) -> tuple[float, float]:
        items = list(datos.get("items") or [])
        codigo = str(datos.get("codigo", "")).strip()
        paciente = str(datos.get("paciente_nombre", "")).strip()
        fecha = _formatear_fecha(datos.get("fecha_emision", ""))
        generales = datos.get("indicaciones_generales", "")

        # El nombre se resuelve una sola vez con el ancho de la raya MÁS CORTA
        # de las dos mitades, así sale idéntico en las dos.
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

            # `Solicito:` entra a PT_RP con 61,19 mm de aire hasta el bloque
            # «N.º» y 13,84 mm hasta el pie del logo (ver el encabezado del
            # módulo y `medidas_rotulo`): no hizo falta bajarle el cuerpo, así
            # que el encabezado se usa tal como lo heredamos.
            self._encabezado(0.0, ROTULO_SOLICITO, codigo,
                             LOGO_X_MM, SALUD_X_MM, RP_X_MM)
            self._encabezado(MITAD_ANCHO_MM, ROTULO_IND, codigo,
                             LOGO_X_IND_MM, SALUD_X_IND_MM, RP_X_IND_MM)

            self._colegiatura(0.0)
            self._pie_paciente(0.0, PIE_RP, nombre, nombre_pt, fecha)
            self._pie_paciente(MITAD_ANCHO_MM, PIE_IND, nombre, nombre_pt, fecha)

        alto_solicito = self._cuerpo_solicito(0.0, items, dibujar)
        alto_ind = self._cuerpo_ind(MITAD_ANCHO_MM, items, generales, dibujar)
        return alto_solicito, alto_ind


# =============================================================================
# 4. API PUBLICA
# =============================================================================

def medir_contenido(datos: Mapping[str, Any], *,
                    ruta_logo: str = RUTA_LOGO_DEFECTO,
                    dir_fuentes: str = DIR_FUENTES_DEFECTO) -> dict[str, Any]:
    """Calcula cuánto ocupa el contenido sin escribir ningún archivo.

    La interfaz lo usa para avisar ANTES de generar. Devuelve **las mismas
    claves que el del récipe** —`rp_*` para la mitad `Solicito:` e `ind_*` para
    la `Ind.`— a propósito: así los avisos de la pantalla y el manejo del aviso
    en `rutas.py` son exactamente los mismos que ya andan.
    """
    doc = _OrdenExamenes(ruta_logo, dir_fuentes)
    alto_solicito, alto_ind = doc.componer(datos, dibujar=False)
    return {
        "entra": (alto_solicito <= ALTO_DISPONIBLE_RP_MM
                  and alto_ind <= ALTO_DISPONIBLE_IND_MM
                  and doc.estado_nombre != "truncado"),
        "rp_usado_mm": round(alto_solicito, 2),
        "rp_disponible_mm": round(ALTO_DISPONIBLE_RP_MM, 2),
        "ind_usado_mm": round(alto_ind, 2),
        "ind_disponible_mm": round(ALTO_DISPONIBLE_IND_MM, 2),
        # "completo" | "abreviado" (se acortaron los nombres del medio a
        # inicial) | "truncado" (no entra ni abreviado: se rechaza)
        "nombre_estado": doc.estado_nombre,
        "nombre_impreso": doc.nombre_impreso,
    }


def generar_examenes(datos: Mapping[str, Any], ruta_salida: str, *,
                     ruta_logo: str = RUTA_LOGO_DEFECTO,
                     dir_fuentes: str = DIR_FUENTES_DEFECTO) -> str:
    """Escribe el PDF de la orden de análisis y devuelve la ruta de salida.

    `datos` es un dict plano — el módulo NO consulta la base de datos:

        codigo                 str   'EC-0001'  (el del PACIENTE; se imprime
                                     igual en las dos mitades)
        fecha_emision          str|date  '26/08/2026' o '2026-08-26'
        paciente_nombre        str
        items                  list[dict] con:
            examen             str   (sale en las DOS mitades, mismo número)
            muestra            str   (sólo en la mitad `Solicito:`, a la
                                      derecha del renglón; puede ir vacía)
            indicaciones       str   (la preparación de ESE análisis; sólo en
                                      la mitad `Ind.`; puede ir vacía — el
                                      análisis se lista igual, con su número)
        indicaciones_generales str   texto libre al pie de la mitad `Ind.`

    Levanta `ContenidoNoCabeError` si el cuerpo no entra en alguna mitad,
    `NombreNoCabeError` si el nombre del paciente no entra ni abreviado, y
    `RecursoFaltanteError` si falta el logo o alguna Lato. Nunca desborda la
    hoja ni achica el cuerpo del texto.
    """
    if not os.path.isfile(ruta_logo):
        raise RecursoFaltanteError(f"Falta el logo. Esperado en: {ruta_logo}")

    doc = _OrdenExamenes(ruta_logo, dir_fuentes)
    alto_solicito, alto_ind = doc.componer(datos, dibujar=True)

    if alto_solicito > ALTO_DISPONIBLE_RP_MM:
        raise ContenidoNoCabeError(MITAD_SOLICITO, alto_solicito,
                                   ALTO_DISPONIBLE_RP_MM)
    if alto_ind > ALTO_DISPONIBLE_IND_MM:
        raise ContenidoNoCabeError(MITAD_IND, alto_ind, ALTO_DISPONIBLE_IND_MM)
    if doc.estado_nombre == "truncado":
        raise NombreNoCabeError(str(datos.get("paciente_nombre", "")).strip(),
                                doc.nombre_impreso)

    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    doc.output(ruta_salida)
    return ruta_salida


# =============================================================================
# 5. PRUEBA
# =============================================================================

if __name__ == "__main__":
    EJEMPLO = {
        "codigo": "EC-0001",
        "fecha_emision": "26/08/2026",
        "paciente_nombre": "María Fernanda Rodríguez Blanco",
        "items": [
            {"examen": "Hematología completa",
             "muestra": "Sangre",
             "indicaciones": "No requiere ayuno."},
            {"examen": "Glicemia en ayunas",
             "muestra": "Sangre",
             "indicaciones": "Ayuno de 8 a 12 horas."},
            {"examen": "Perfil lipídico completo",
             "muestra": "Sangre",
             "indicaciones": "Ayuno de 12 horas. No ingerir alcohol las 24 "
                             "horas previas."},
            {"examen": "TSH",
             "muestra": "Sangre",
             "indicaciones": "No requiere ayuno."},
            {"examen": "Examen de orina (uroanálisis)",
             "muestra": "Orina",
             "indicaciones": "Primera orina de la mañana, chorro medio, previo "
                             "aseo genital."},
            {
                # Caso sin preparación: en la mitad Ind. tiene que salir igual,
                # con su número, aunque no arrastre ningún renglón debajo.
                "examen": "Grupo sanguíneo y factor Rh",
                "muestra": "Sangre",
                "indicaciones": "",
            },
        ],
        "indicaciones_generales": (
            "Traer los resultados al control del 5 de septiembre. Presentar "
            "esta orden en el laboratorio y conservar la mitad derecha, que "
            "es la que dice cómo prepararse para cada estudio."
        ),
    }

    destino = os.path.join(_RAIZ, "build", "examenes_prueba.pdf")
    print(medir_contenido(EJEMPLO))
    print(generar_examenes(EJEMPLO, destino))
