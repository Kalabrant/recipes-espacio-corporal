# -*- coding: utf-8 -*-
"""Composicion del PDF de la historia clinica imprimible — Espacio Corporal.

Carta VERTICAL (dec. 14), mismo membrete que el informe (dec. 7 y 8), tantas
paginas como haga falta:

    generar_historia(datos, "historia.pdf")

El modulo es puro, como `pdf_recipe` y `pdf_informe`: recibe un dict plano y
escribe un PDF. No consulta la base ni la configuracion.

QUE IMPRIME Y POR QUE
---------------------
Sigue el papel que el medico corrigio a mano (`referencias/Historia
clinica.pdf`, Parte A del analisis), con sus rotulos y respetando lo que tacho:

  * FICHA — de la identificacion del papel quedan solo estado civil y
    ocupacion (dec. 4), mas el tipo de sangre que decidio conservar (dec. 6).
    Se fueron afiliacion, cama, residente, clinica de adscripcion, elaboro,
    tipo de interrogatorio, religion, escolaridad y origen.
  * ALERGIAS — sale destacado y arriba de todo, apenas debajo de la ficha,
    aunque el papel las tenga sepultadas al final de los antecedentes
    patologicos. Es lo unico de la historia que puede hacer daño si no se ve
    (Parte A §6), y en una hoja impresa "estar" no alcanza: tiene que saltar.
  * ANTECEDENTES FAMILIARES — el papel decia "heredo familiares"; el medico
    tacho "HEREDO".
  * ANTECEDENTES PERSONALES NO PATOLOGICOS — la alimentacion con sus
    denominadores impresos (x/3 comidas al dia, x/7 frutas y verduras…), la
    habitacion como nota libre (dec. 5) y la actividad fisica.
  * ANTECEDENTES PERSONALES PATOLOGICOS — los diez campos que sobrevivieron.
  * EVOLUCION — los mini-graficos de peso, IMC, grasa, musculo y grasa
    visceral (dec. 13 ampliada). Van ANTES de las consultas porque son el
    resumen: la tendencia en un vistazo, y recien despues el detalle visita
    por visita. Solo aparecen las metricas con dos o mas mediciones — con una
    sola no hay tendencia que mirar, hay un numero, y ese numero ya esta en
    los signos vitales de la consulta.
  * CONSULTAS — de la mas nueva a la mas vieja, que es como se lee una
    historia: primero que paso la ultima vez.
  * ORDENES DE EXAMENES y REGISTROS DE INFILTRACIONES — lo que se EMITIO
    (contrato 2.1 §7). Van al final y despues de las consultas porque no son
    la historia: son los documentos que salieron de ella. Cada uno entra en un
    renglon —fecha, cuanto y de que— y no en una ficha propia: el detalle vive
    en su PDF, que esta guardado en la carpeta del paciente. Los anulados se
    listan MARCADOS, nunca escondidos: que una orden se haya anulado es parte
    de lo que paso (mismo criterio que el Historial y que `excel.py`).

**Solo se imprime lo que tiene contenido.** Una historia recien empezada sale
en una carilla en vez de en cuatro paginas de rotulos vacios; un formulario
impreso con huecos es exactamente lo que el medico ya tenia en papel y vino a
dejar atras. Lo unico que se imprime siempre son la ficha y el titulo de
consultas (con su "todavia no hay ninguna" si esta vacia), porque su ausencia
se leeria como un error de la aplicacion.

DECISIONES DE MAQUETA
---------------------
* Sin ornamento lateral, por lo mismo que el informe: es del talonario del
  recipe y una historia se fotocopia (ver el encabezado de `pdf_informe`).
* Los signos vitales van en la tabla de recuadro fino de `pdf_comun`, con los
  rotulos LITERALES del papel (TA, F.C., F.R., Temp., TAM, Dxtx, TFG, SatO2,
  Peso, Talla, IMC) y la unidad entre parentesis. Solo salen los que tienen
  valor: seis casillas llenas se leen; once, de las cuales cinco vacias, no.
* Cada consulta imprime tambien su diagnostico y su plan, que estan en la
  misma fila de la base. Una historia impresa sin el diagnostico obliga a
  volver a la pantalla, que es justo lo que el papel viene a evitar.
* El pie dice cuando se imprimio. Esto NO es un documento numerado —no se
  guarda ni se registra, se imprime (`rutas.py` no le persiste ninguna ruta)—,
  asi que la fecha de impresion es lo unico que ubica la copia en el tiempo.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

try:  # como paquete (``from app import pdf_historia``)
    from . import pdf_comun, pdf_infiltraciones
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import pdf_comun  # type: ignore[no-redef]
    import pdf_infiltraciones  # type: ignore[no-redef]

# Atajos a lo compartido (ver la nota de `pdf_informe` sobre por que no se usa
# `from pdf_comun import ...`).
ANCHO_UTIL_MM = pdf_comun.ANCHO_UTIL_MM
GUIA_DER_MM = pdf_comun.GUIA_DER_MM
MARGEN_IZQ_MM = pdf_comun.MARGEN_IZQ_MM
INTERLINEA_MM = pdf_comun.INTERLINEA_MM
GRIS_DATO = pdf_comun.GRIS_DATO
GRIS_ROTULO = pdf_comun.GRIS_ROTULO
TEAL_MEDIO = pdf_comun.TEAL_MEDIO
TEAL_OSCURO = pdf_comun.TEAL_OSCURO
VERDE_LIMA = pdf_comun.VERDE_LIMA

TITULO = "HISTORIA CLÍNICA"

PT_TITULO = 16.0
TITULO_BASE_Y_MM = 60.0
CUERPO_HISTORIA_Y0_MM = 72.0

PT_CUERPO = 11.0
PT_SECCION = 11.5                # ANTECEDENTES FAMILIARES, CONSULTAS…
PT_CONSULTA = 11.5               # la fecha de cada visita
PT_PIE = 9.0

SANGRIA_MM = 5.0                 # los campos de una sección entran un poco
SEPARACION_SECCION_MM = 3.4
SEPARACION_CONSULTA_MM = 3.0

#: Cuántas casillas de signos vitales entran en un renglón de la tabla. Con
#: cinco, cada celda mide 35 mm: entra "120/80 mmHg" sin partirse.
SIGNOS_POR_FILA = 5


# =============================================================================
# 1. ERRORES
# =============================================================================

class HistoriaError(pdf_comun.DocumentoError):
    """Error al componer el PDF de la historia clínica."""


class RecursoFaltanteError(pdf_comun.RecursoFaltanteError, HistoriaError):
    """Falta el logo o alguna de las fuentes Lato."""


# =============================================================================
# 2. LOS CAMPOS DEL PAPEL, EN ORDEN Y CON SU ROTULO
# =============================================================================

#: `(clave en `historias`, rótulo impreso)`. El orden es el del formulario.
FAMILIARES = (
    ("fam_madre", "Madre:"),
    ("fam_padre", "Padre:"),
    ("fam_hermanos", "Hermanos:"),
    ("fam_hijos", "Hijos:"),
)

#: Alimentación: numerador que escribe el médico y denominador impreso en el
#: papel (Parte A §2.4). El denominador es fijo y va siempre, como en el
#: formulario: "3/3 comidas al día" se lee distinto que "3 comidas al día".
ALIMENTACION = (
    ("alim_comidas_dia", "Comidas al día", 3),
    ("alim_frutas_verduras", "Frutas y verduras", 7),
    ("alim_pollo", "Pollo", 7),
    ("alim_pescado", "Pescado", 7),
    ("alim_carnes_rojas", "Carnes rojas", 7),
    ("alim_carbohidratos", "Carbohidratos y lípidos", 7),
    ("alim_litros_agua", "Litros de agua al día", 2),
)

NO_PATOLOGICOS = (
    ("actividad_fisica", "Actividad física:"),
    ("habitacion", "Habitación:"),
    ("alimentacion_notas", "Notas de alimentación:"),
)

PATOLOGICOS = (
    ("cronico_degenerativos", "Crónico-degenerativos:"),
    ("alcoholismo", "Alcoholismo:"),
    ("tabaquismo", "Tabaquismo:"),
    ("toxicomanias", "Toxicomanías:"),
    ("quirurgicos", "Quirúrgicos:"),
    ("traumaticos", "Traumáticos:"),
    ("ginecologicos", "Ginecológicos:"),
    ("hospitalizaciones", "Hospitalizaciones previas:"),
    ("transfusiones", "Transfusiones:"),
    # `alergias` NO va en esta lista aunque en el papel viva acá: sube al
    # aviso destacado de arriba (ver `_alergias`). Imprimirla en los dos
    # lugares se leería como un error de la aplicación, y el aviso está tres
    # centímetros más arriba: nadie lo va a extrañar.
)

#: `(clave en `signos_vitales`, rótulo del papel con su unidad, decimales)`.
SIGNOS = (
    ("fc", "F.C. (lpm)", 0),
    ("fr", "F.R. (rpm)", 0),
    ("temperatura", "Temp. (°C)", 1),
    ("tam", "TAM (mmHg)", 0),
    ("dxtx", "Dxtx (mg/dL)", 0),
    ("tfg", "TFG (mL/min)", 0),
    ("spo2", "SatO2 (%)", 0),
    ("peso", "Peso (kg)", 1),
    ("talla", "Talla (m)", 2),
    ("imc", "IMC (kg/m²)", 1),
)

CONSULTA_TEXTOS = (
    ("motivo", "Motivo de consulta:"),
    ("examen_fisico", "Examen físico:"),
    ("evolucion", "Evolución:"),
    ("diagnostico", "Diagnóstico:"),
    ("plan", "Plan:"),
)

#: `(clave de la serie, título con su unidad, decimales)`. El orden es el que
#: pide la lectura clínica: primero peso e IMC, que es lo que el paciente y el
#: médico miran, y después la composición corporal de la balanza. La unidad va
#: en el título porque un gráfico sin unidad no se puede leer, y el IMC no
#: lleva porque no tiene: es un índice.
SERIES_EVOLUCION = (
    ("peso", "Peso (kg)", 1),
    ("imc", "IMC", 1),
    ("grasa_pct", "Grasa (%)", 1),
    ("musculo_kg", "Músculo (kg)", 1),
    ("grasa_visceral", "Grasa visceral", 0),
)

#: Con un solo punto no hay evolución: no se dibuja el gráfico.
MINIMO_PUNTOS_GRAFICO = 2

#: Dos por fila. A tres, el área de trazado bajaría de 55 mm a 30 y las fechas
#: de los extremos se tocarían; a uno, cinco métricas ocuparían dos hojas.
GRAFICOS_POR_FILA = 2
SEPARACION_GRAFICOS_MM = 8.0     # canaleta entre las dos columnas
SEPARACION_FILA_GRAFICOS_MM = 5.0


# -----------------------------------------------------------------------------
# Lo que se emitió: órdenes de exámenes e infiltraciones (contrato 2.1 §7)
# -----------------------------------------------------------------------------

#: Cuántos nombres de análisis se escriben antes de resumir con «y N más».
#: Con cuatro nombres del catálogo (unos 25 caracteres cada uno) el renglón
#: ocupa dos líneas y todavía se lee de un vistazo; con seis se convierte en un
#: párrafo, y para leer la orden entera está su PDF, que es el documento.
MAX_ANALISIS_LISTADOS = 4

#: Cómo se nombra impresa cada lámina de `pdf_infiltraciones.LAMINAS`. El
#: identificador de la columna `vista` (`mujer-frontal`) es de la base, no del
#: papel: en una historia clínica se lee «Lámina femenina, vista frontal».
LAMINAS_ROTULO = {
    "mujer-frontal": "Lámina femenina, vista frontal",
    "hombre-frontal": "Lámina masculina, vista frontal",
}

#: Separador entre los datos de un renglón emitido. El mismo interpunto que
#: usa la alimentación, con un solo espacio: acá los tramos son largos.
SEPARADOR_RENGLON = " · "


# =============================================================================
# 3. AYUDAS
# =============================================================================

def _dic(valor: Any) -> dict[str, Any]:
    """Un dict a partir de un dict, un `sqlite3.Row` o `None`.

    `rutas.py` viene de la base y sus filas son `sqlite3.Row`, que se indexa
    como un dict pero no tiene `.get`. Se convierte acá y no allá para que
    quien use el módulo no tenga que acordarse.
    """
    if valor is None:
        return {}
    if isinstance(valor, Mapping):
        return dict(valor)
    try:
        return dict(valor)  # sqlite3.Row y cualquier cosa con keys()
    except (TypeError, ValueError):
        return {}


def _t(datos: Mapping[str, Any], clave: str) -> str:
    valor = datos.get(clave)
    return "" if valor is None else str(valor).strip()


def _numero(valor: Any, decimales: int = 0) -> str:
    """El número tal como se lee en Venezuela: coma decimal, sin ceros de más."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor).strip()
    texto = f"{numero:.{decimales}f}"
    return texto.replace(".", ",")


def _tension(signos: Mapping[str, Any]) -> str:
    """`120/80`, que es como el médico la escribe y como la pide el papel."""
    sistolica = _numero(signos.get("ta_sistolica"))
    diastolica = _numero(signos.get("ta_diastolica"))
    if sistolica and diastolica:
        return f"{sistolica}/{diastolica}"
    return sistolica or diastolica


def _casillas_signos(signos: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Las casillas con valor, en el orden del papel. Las vacías no salen."""
    casillas: list[tuple[str, str]] = []
    tension = _tension(signos)
    if tension:
        casillas.append(("TA (mmHg)", tension))
    for clave, rotulo, decimales in SIGNOS:
        valor = _numero(signos.get(clave), decimales)
        if valor:
            casillas.append((rotulo, valor))
    return casillas


def _alimentacion(historia: Mapping[str, Any]) -> str:
    """`Comidas al día 2/3 · Frutas y verduras 4/7 · …`, solo lo cargado."""
    partes = []
    for clave, rotulo, denominador in ALIMENTACION:
        valor = _numero(historia.get(clave))
        if valor:
            partes.append(f"{rotulo} {valor}/{denominador}")
    return "   ·   ".join(partes)


def _hay_algo(datos: Mapping[str, Any], claves: Iterable[str]) -> bool:
    return any(_t(datos, clave) for clave in claves)


def _puntos_serie(bruta: Any) -> list[tuple[str, float, int | None]]:
    """`(etiqueta, valor, ordinal)` de una serie de `/evolucion`.

    Descarta lo que no es un número —una medición que el médico dejó a medias
    llega con `null` y no es un cero, es un dato que no está— y ordena por
    fecha si todas se pudieron leer. El endpoint ya devuelve cronológico, pero
    el módulo no tiene por qué confiar: una serie desordenada no falla, dibuja
    una madeja, que es peor.
    """
    puntos: list[tuple[str, float, int | None]] = []
    for cruda in bruta or ():
        punto = _dic(cruda)
        try:
            valor = float(punto.get("valor"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        fecha = punto.get("fecha")
        puntos.append((pdf_comun.fecha_corta(fecha), valor,
                       pdf_comun.dia_ordinal(fecha)))
    if all(orden is not None for _, _, orden in puntos):
        puntos.sort(key=lambda p: p[2])  # type: ignore[arg-type,return-value]
    return puntos


def _series_evolucion(datos: Mapping[str, Any]) -> list[tuple[str, list, int]]:
    """Las métricas que tienen tendencia que mostrar, en el orden del papel.

    Acepta tanto `datos["evolucion"] = {"series": {...}}` —la respuesta cruda
    de `GET /api/pacientes/<id>/evolucion`— como el diccionario de series
    pelado, así quien llama no tiene que desenvolver nada.
    """
    crudo = _dic(datos.get("evolucion"))
    if "series" in crudo:
        crudo = _dic(crudo.get("series"))
    series = []
    for clave, titulo, decimales in SERIES_EVOLUCION:
        puntos = _puntos_serie(crudo.get(clave))
        if len(puntos) >= MINIMO_PUNTOS_GRAFICO:
            series.append((titulo, puntos, decimales))
    return series


def _filas(bruta: Any) -> list[dict[str, Any]]:
    """Las filas de una lista de `sqlite3.Row` o de dicts, sin las vacías."""
    filas = [_dic(cruda) for cruda in bruta or ()]
    return [fila for fila in filas if fila]


def _analisis_de(examen: Mapping[str, Any]) -> list[str]:
    """Los nombres de los análisis de una orden, sin importar cómo llegaron.

    Se aceptan las tres formas en que la orden circula por la aplicación, para
    que quien llame no tenga que traducir nada:

      * `analisis` como **lista** — lo que devuelve
        `basedatos.analisis_por_examen` para cada `examen_id`;
      * `analisis` como **texto separado por comas** — lo que arma
        `rutas._json_examen` para el historial y la pantalla;
      * `items` con un dict por renglón — la forma del dict de entrada de
        `pdf_examenes.generar_examenes` (contrato §3).
    """
    bruto: Any = examen.get("analisis")
    if bruto is None:
        bruto = [_dic(item).get("examen") for item in examen.get("items") or ()]
    crudos: Iterable[Any] = bruto.split(",") if isinstance(bruto, str) else bruto
    return [nombre for nombre in (str(n or "").strip() for n in crudos or ())
            if nombre]


def _resumen_analisis(nombres: Sequence[str]) -> str:
    """`Hematología completa, Urea, TSH, VDRL y 3 más`."""
    if len(nombres) <= MAX_ANALISIS_LISTADOS:
        return ", ".join(nombres)
    faltan = len(nombres) - MAX_ANALISIS_LISTADOS
    return f"{', '.join(nombres[:MAX_ANALISIS_LISTADOS])} y {faltan} más"


def _entero(valor: Any) -> int:
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def _lamina(vista: Any) -> str:
    """El nombre impreso de la lámina. Una vista desconocida no rompe nada.

    A propósito NO se usa `pdf_infiltraciones.normalizar_vista`, que levanta
    `VistaDesconocidaError`: la historia clínica es una impresión de todo lo
    que hay y no puede quedarse sin salir porque una fila vieja traiga una
    vista que ya no está en el catálogo de láminas.
    """
    clave = str(vista or "").strip().lower()
    return LAMINAS_ROTULO.get(clave) or clave or "Lámina sin identificar"


def _totales_infiltracion(registro: Mapping[str, Any]
                          ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(puntos numerados, totales por producto)` de una sesión de mapeo.

    Los totales **no se recalculan acá**: se piden a
    `pdf_infiltraciones.totales_por_producto`, que es el mismo que imprime el
    PDF del registro. Si alguna vez cambia el criterio —hoy un punto sin
    producto o con dosis cero no suma— la historia lo hereda sola, y las dos
    hojas siguen diciendo el mismo número, que es lo único que importa cuando
    el médico las compara.

    Para eso hay que resolver antes el `productoId` de cada punto, y se hace
    con las mismas dos funciones que usa `generar_infiltraciones`, sin índice
    de plantillas: acá no se dibuja la lámina, así que la región de cada punto
    da igual y `zona`/`lado` ya vienen en la fila.
    """
    _, indice = pdf_infiltraciones.normalizar_productos(registro.get("productos"))
    puntos = pdf_infiltraciones.normalizar_puntos(registro.get("puntos"),
                                                   indice, {})
    return puntos, pdf_infiltraciones.totales_por_producto(puntos)


def _resumen_productos(totales: Sequence[Mapping[str, Any]]) -> str:
    """`Toxina A — marca 1: 24 U · Ácido hialurónico: 1,5 ml`."""
    partes = []
    for total in totales:
        producto = _dic(total.get("producto"))
        nombre = str(producto.get("nombre") or "").strip() or "Producto"
        dosis = pdf_infiltraciones.formatear_dosis(total.get("dosis") or 0)
        unidad = str(producto.get("unidad") or "").strip()
        partes.append(f"{nombre}: {dosis} {unidad}".strip())
    return SEPARADOR_RENGLON.join(partes)


# =============================================================================
# 4. COMPOSITOR
# =============================================================================

class _Historia(pdf_comun.HojaCarta):
    """Lienzo de la historia. La API pública es `generar_historia`."""

    _ERROR_RECURSO = RecursoFaltanteError

    # ---------------------------------------------------------------- título
    def abrir(self) -> None:
        self.nueva_pagina()
        self._texto_centrado(MARGEN_IZQ_MM, GUIA_DER_MM, TITULO_BASE_Y_MM,
                             TITULO, "B", PT_TITULO, TEAL_OSCURO)
        self.pluma_y = CUERPO_HISTORIA_Y0_MM

    # --------------------------------------------------------------- sección
    def seccion(self, titulo: str) -> None:
        """Título de sección con su filete: es la marca del papel."""
        self.espacio(SEPARACION_SECCION_MM)
        self.asegurar(INTERLINEA_MM * 2.6)
        self._texto(MARGEN_IZQ_MM, self.pluma_y, titulo, "B", PT_SECCION,
                    TEAL_OSCURO)
        self._raya(MARGEN_IZQ_MM, GUIA_DER_MM, self.pluma_y + 1.4, 0.25,
                   TEAL_MEDIO)
        self.pluma_y += INTERLINEA_MM + 1.2

    def campos(self, datos: Mapping[str, Any],
               definicion: Sequence[tuple[str, str]]) -> bool:
        """Escribe los campos con contenido. Devuelve si escribió alguno."""
        escribio = False
        for clave, rotulo in definicion:
            valor = _t(datos, clave)
            if valor:
                self.campo(rotulo, valor, sangria=SANGRIA_MM)
                escribio = True
        return escribio

    def tabla_signos(self, signos: Mapping[str, Any]) -> None:
        """Los signos vitales del papel, compactos y sin casillas vacías."""
        casillas = _casillas_signos(signos)
        if not casillas:
            return
        fraccion = 1.0 / SIGNOS_POR_FILA
        for inicio in range(0, len(casillas), SIGNOS_POR_FILA):
            fila = casillas[inicio:inicio + SIGNOS_POR_FILA]
            # La última fila incompleta no se estira: las celdas de todas las
            # filas miden igual y la tabla se lee como una grilla.
            celdas = [(rotulo, valor, fraccion) for rotulo, valor in fila]
            faltan = SIGNOS_POR_FILA - len(fila)
            celdas += [("", "", fraccion)] * faltan
            self.fila_recuadro(celdas)

    # ---------------------------------------------------------------- pie
    def pie_impresion(self, cuando: Any) -> None:
        """«Historia impresa el … · Espacio Corporal» al pie de cada hoja.

        Se vuelve a cada página con `_ir_a_pagina` y no moviendo `self.page` a
        secas: fpdf2 no ve el salto y el pie de la hoja 2 en adelante saldría
        con el cuerpo de letra que quedó en esa hoja (ver `pdf_comun`).
        """
        texto = ("Historia impresa el "
                 f"{pdf_comun.formatear_fecha(cuando)} · Espacio Corporal")
        actual = self.page
        for numero in range(1, actual + 1):
            self._ir_a_pagina(numero)
            self._texto(MARGEN_IZQ_MM, pdf_comun.PIE_BASE_Y_MM, texto, "",
                        PT_PIE, GRIS_ROTULO)
        self._ir_a_pagina(actual)


# =============================================================================
# 5. LAS SECCIONES
# =============================================================================

def _ficha(doc: _Historia, paciente: Mapping[str, Any],
           historia: Mapping[str, Any]) -> None:
    """La ficha de identificación: lo que quedó del papel (dec. 4 y 6)."""
    doc.fila_recuadro([
        ("Nombre", _t(paciente, "nombre"), 0.52),
        ("C.I.", _t(paciente, "cedula"), 0.24),
        ("Fecha de nacimiento",
         pdf_comun.formatear_fecha(paciente.get("fecha_nacimiento")), 0.24),
    ])
    edad = _t(paciente, "edad")
    doc.fila_recuadro([
        ("Edad", f"{edad} años" if edad else "", 0.20),
        ("Sexo", _t(paciente, "sexo"), 0.16),
        ("Teléfono", _t(paciente, "telefono"), 0.32),
        ("Tipo de sangre", _t(historia, "tipo_sangre"), 0.32),
    ])
    if _hay_algo(historia, ("estado_civil", "ocupacion")):
        doc.fila_recuadro([
            ("Estado civil", _t(historia, "estado_civil"), 0.50),
            ("Ocupación", _t(historia, "ocupacion"), 0.50),
        ])


#: Ancho de la barra verde lima que marca el aviso de alergias.
BARRA_ALERGIAS_MM = 1.8


def _alergias(doc: _Historia, historia: Mapping[str, Any]) -> None:
    """El aviso de alergias, arriba y destacado (Parte A §6).

    Va con una barra verde lima al costado: en una hoja impresa a un solo
    color de texto, "estar" no alcanza. Es lo único de la historia que puede
    hacer daño si no se ve, y por eso sube desde el final de los antecedentes
    patológicos —donde lo tiene el papel— hasta debajo de la ficha.
    """
    alergias = _t(historia, "alergias")
    if not alergias:
        return
    doc.espacio(SEPARACION_SECCION_MM)
    x = MARGEN_IZQ_MM + BARRA_ALERGIAS_MM + 2.6
    ancho_rot = doc._ancho("ALERGIAS: ", "B", PT_CUERPO)
    renglones = doc._envolver_colgante(
        alergias, GUIA_DER_MM - x - ancho_rot,
        GUIA_DER_MM - x - pdf_comun.SANGRIA_COLGANTE_MM, "B", PT_CUERPO)
    # El bloque entero se reserva de una vez para que la barra y el texto
    # queden sí o sí en la misma hoja (`y0` se toma DESPUÉS del salto).
    doc.asegurar(INTERLINEA_MM * len(renglones))
    y0 = doc.pluma_y - 3.6
    for i, renglon in enumerate(renglones):
        doc.asegurar(INTERLINEA_MM)
        if i == 0:
            doc._texto(x, doc.pluma_y, "ALERGIAS:", "B", PT_CUERPO, TEAL_OSCURO)
            doc._texto(x + ancho_rot, doc.pluma_y, renglon, "B", PT_CUERPO,
                       GRIS_DATO)
        else:
            doc._texto(x + pdf_comun.SANGRIA_COLGANTE_MM, doc.pluma_y, renglon,
                       "B", PT_CUERPO, GRIS_DATO)
        doc.pluma_y += INTERLINEA_MM
    doc.set_fill_color(*VERDE_LIMA)
    doc.rect(MARGEN_IZQ_MM, y0, BARRA_ALERGIAS_MM, doc.pluma_y - y0 - 1.4,
             style="F")


def _antecedentes(doc: _Historia, historia: Mapping[str, Any]) -> None:
    if _hay_algo(historia, (c for c, _ in FAMILIARES)):
        doc.seccion("ANTECEDENTES FAMILIARES")
        doc.campos(historia, FAMILIARES)

    alimentacion = _alimentacion(historia)
    if alimentacion or _hay_algo(historia, (c for c, _ in NO_PATOLOGICOS)):
        doc.seccion("ANTECEDENTES PERSONALES NO PATOLÓGICOS")
        if alimentacion:
            doc.campo("Alimentación:", alimentacion, sangria=SANGRIA_MM)
        doc.campos(historia, NO_PATOLOGICOS)

    if _hay_algo(historia, (c for c, _ in PATOLOGICOS)):
        doc.seccion("ANTECEDENTES PERSONALES PATOLÓGICOS")
        doc.campos(historia, PATOLOGICOS)

    notas = _t(historia, "notas_generales")
    if notas:
        doc.seccion("NOTAS")
        doc.parrafo(notas, x=MARGEN_IZQ_MM + SANGRIA_MM)


def _evolucion(doc: _Historia, series: Sequence[tuple[str, list, int]]) -> None:
    """Los mini-gráficos de las métricas con dos o más mediciones (dec. 13).

    Si no hay ninguna, no se imprime **nada**: ni el título. Un rótulo
    «EVOLUCIÓN» seguido de hoja en blanco se lee como que la aplicación perdió
    los gráficos, y el 90 % de los pacientes recién empezados no tiene dos
    mediciones de nada.
    """
    if not series:
        return

    ancho = ((ANCHO_UTIL_MM - SEPARACION_GRAFICOS_MM * (GRAFICOS_POR_FILA - 1))
             / GRAFICOS_POR_FILA)
    alto = pdf_comun.alto_mini_grafico()

    # El título y la primera fila van juntos sí o sí: se reserva todo el
    # bloque antes de escribir el rótulo, así `seccion()` no lo deja colgado
    # al pie de una hoja con los gráficos en la siguiente.
    doc.asegurar(INTERLINEA_MM * 2.6 + SEPARACION_SECCION_MM + alto)
    doc.seccion("EVOLUCIÓN")

    for inicio in range(0, len(series), GRAFICOS_POR_FILA):
        fila = series[inicio:inicio + GRAFICOS_POR_FILA]
        # Un mini-gráfico partido entre dos hojas no es un gráfico.
        doc.asegurar(alto)
        techo = doc.pluma_y - INTERLINEA_MM * 0.8
        for columna, (titulo, puntos, decimales) in enumerate(fila):
            doc.mini_grafico(
                MARGEN_IZQ_MM + columna * (ancho + SEPARACION_GRAFICOS_MM),
                techo, ancho, titulo,
                [(etiqueta, valor) for etiqueta, valor, _ in puntos],
                posiciones=[orden for _, _, orden in puntos],
                formato=lambda valor, d=decimales: _numero(valor, d))
        doc.pluma_y = techo + alto + SEPARACION_FILA_GRAFICOS_MM


def _consultas(doc: _Historia, consultas: Sequence[Mapping[str, Any]]) -> None:
    """La línea de tiempo, de la visita más nueva a la más vieja."""
    doc.seccion("CONSULTAS")
    if not consultas:
        doc.parrafo("Todavía no hay consultas registradas para este paciente.",
                    color=GRIS_ROTULO, x=MARGEN_IZQ_MM + SANGRIA_MM)
        return

    for indice, cruda in enumerate(consultas):
        consulta = _dic(cruda)
        # El renglón de la fecha no puede quedar solo al pie de una hoja.
        # Cuatro interlíneas es lo que mide la fecha (5,6 mm) más la primera
        # fila de signos vitales (11,7 mm): con tres, la fecha entraba y la
        # tabla no, y la visita arrancaba con el encabezado en una hoja y los
        # datos en la siguiente.
        doc.asegurar(INTERLINEA_MM * 4)
        if indice:
            doc.espacio(SEPARACION_CONSULTA_MM)
            doc._raya(MARGEN_IZQ_MM, GUIA_DER_MM, doc.pluma_y - 3.2, 0.15,
                      pdf_comun.GRIS_RECUADRO)
        doc._texto(MARGEN_IZQ_MM, doc.pluma_y,
                   pdf_comun.formatear_fecha(consulta.get("fecha")), "B",
                   PT_CONSULTA, TEAL_OSCURO)
        doc.pluma_y += INTERLINEA_MM + 0.6

        signos = _dic(consulta.get("signos"))
        if not signos:
            # `basedatos.listar_consultas` ya trae los signos aplanados en la
            # misma fila, así que la consulta sirve de fuente si no vino el
            # subdiccionario: quien llama no tiene que rearmar nada.
            signos = consulta
        doc.tabla_signos(signos)
        doc.campos(consulta, CONSULTA_TEXTOS)


#: Lo que hay que reservar para que el título de una sección de documentos no
#: quede solo al pie: el filete y su aire (`seccion`) más los dos renglones que
#: mide el primer asiento cuando su resumen se parte en dos líneas.
RESERVA_SECCION_MM = (INTERLINEA_MM * 2.6 + SEPARACION_SECCION_MM
                      + INTERLINEA_MM * 2)


def _asiento(doc: _Historia, fecha: Any, partes: Sequence[str],
             anulado: Any, marca: str) -> None:
    """Un documento emitido en un renglón: «14/08/2026: … · … · …».

    La marca de anulación va **primera**, antes de la fecha y de todo lo
    demás. Un renglón que termina en «ANULADA» se lee entero antes de saber
    que no vale; uno que empieza con la marca, no. Es el mismo criterio con el
    que las alergias suben al principio de la hoja: lo que cambia cómo se lee
    el resto va antes que el resto.
    """
    escritas = [str(parte).strip() for parte in partes if str(parte).strip()]
    if anulado:
        escritas.insert(0, marca)
    if not escritas:
        return
    rotulo = pdf_comun.formatear_fecha(fecha) or "Sin fecha"
    doc.campo(f"{rotulo}:", SEPARADOR_RENGLON.join(escritas),
              sangria=SANGRIA_MM)


def _examenes(doc: _Historia, examenes: Any) -> None:
    """Las órdenes de análisis del paciente (contrato 2.1 §7).

    Sin ninguna orden no se imprime **nada**, ni el título: mismo criterio que
    los antecedentes vacíos y que la sección EVOLUCIÓN. Un rótulo «ÓRDENES DE
    EXÁMENES» seguido de blanco se lee como que la aplicación las perdió.
    """
    filas = _filas(examenes)
    if not filas:
        return
    doc.asegurar(RESERVA_SECCION_MM)
    doc.seccion("ÓRDENES DE EXÁMENES")
    for examen in filas:
        nombres = _analisis_de(examen)
        cantidad = len(nombres) or _entero(examen.get("cantidad_items"))
        partes = []
        if cantidad:
            # «análisis» es igual en singular y en plural: no hay que elegir.
            partes.append(f"{cantidad} análisis")
        partes.append(_resumen_analisis(nombres))
        _asiento(doc, examen.get("fecha_emision"), partes,
                 examen.get("anulado"), "ANULADA")


def _infiltraciones(doc: _Historia, registros: Any) -> None:
    """Los registros de infiltraciones del paciente (contrato 2.1 §7).

    De cada sesión salen la lámina sobre la que se marcó, cuántos puntos se
    infiltraron y el total por producto. El total es el mismo que imprime el
    PDF del registro porque sale de la misma función (ver
    `_totales_infiltracion`); el mapa, las zonas y las notas de cada punto
    viven en ese PDF, que está guardado en la carpeta del paciente.
    """
    filas = _filas(registros)
    if not filas:
        return
    doc.asegurar(RESERVA_SECCION_MM)
    doc.seccion("REGISTROS DE INFILTRACIONES")
    for registro in filas:
        puntos, totales = _totales_infiltracion(registro)
        cantidad = len(puntos)
        partes = [
            _lamina(registro.get("vista")),
            "1 punto" if cantidad == 1 else f"{cantidad} puntos",
            _resumen_productos(totales),
        ]
        _asiento(doc, registro.get("fecha"), partes,
                 registro.get("anulado"), "ANULADO")


# =============================================================================
# 6. API PUBLICA
# =============================================================================

def generar_historia(datos: Mapping[str, Any], ruta_salida: str, *,
                     ruta_logo: str = pdf_comun.RUTA_LOGO_DEFECTO,
                     dir_fuentes: str = pdf_comun.DIR_FUENTES_DEFECTO) -> str:
    """Escribe el PDF de la historia y devuelve la ruta de salida.

    `datos` es un dict plano — el módulo NO consulta la base de datos:

        codigo       str   'EC-0001', el código del paciente (dec. 1)
        paciente     dict  nombre, cedula, fecha_nacimiento, edad, sexo,
                           telefono                     (tabla `pacientes`)
        historia     dict  la fila de `historias`: estado civil, ocupación,
                           tipo de sangre, antecedentes familiares, los siete
                           numeradores de alimentación, habitación, actividad
                           física, los patológicos y las notas
        consultas    list  filas de `consultas`, **ya ordenadas de la más
                           nueva a la más vieja**. Cada una puede traer sus
                           signos vitales en la clave `signos` o aplanados en
                           la misma fila, que es como los devuelve
                           `basedatos.listar_consultas`
        evolucion    dict  OPCIONAL. Lo que devuelve
                           `GET /api/pacientes/<id>/evolucion`: `{"series":
                           {"peso": [{"fecha", "valor"}, …], "imc": […],
                           "grasa_pct": […], "musculo_kg": […],
                           "grasa_visceral": […]}}`. También se acepta el
                           diccionario de series pelado. Cada métrica con dos
                           o más mediciones sale como un mini-gráfico en la
                           sección EVOLUCIÓN; si ninguna llega a dos, la
                           sección entera no aparece
        examenes     list  OPCIONAL. Las órdenes de exámenes del paciente, de
                           la más nueva a la más vieja (contrato 2.1 §7). De
                           cada una se leen `fecha_emision`, `anulado` y los
                           nombres de los análisis, que pueden venir en
                           `analisis` como lista —lo que devuelve
                           `basedatos.analisis_por_examen`—, en `analisis`
                           como texto separado por comas —lo que arma
                           `rutas._json_examen`— o en `items`. Sin órdenes, la
                           sección entera no aparece
        infiltraciones list OPCIONAL. Los registros de infiltraciones, de la
                           más nueva a la más vieja, tal como los devuelve
                           `basedatos.infiltracion_a_dict`: `fecha`, `vista`,
                           `anulado` y `productos`/`puntos` ya parseados. Sin
                           registros, la sección entera no aparece
        fecha        str   la fecha de impresión que va al pie; si falta, hoy

    Acepta `sqlite3.Row` en lugar de dict en `paciente`, `historia` y en cada
    consulta: se convierten solos.

    Nunca levanta por contenido largo: la historia crece con las visitas y para
    eso es multipágina, con el membrete repetido en cada hoja.
    """
    if not os.path.isfile(ruta_logo):
        raise RecursoFaltanteError(f"Falta el logo. Esperado en: {ruta_logo}")

    paciente = _dic(datos.get("paciente"))
    historia = _dic(datos.get("historia"))
    consultas = list(datos.get("consultas") or ())
    codigo = str(datos.get("codigo") or paciente.get("codigo") or "").strip()
    cuando = datos.get("fecha") or date.today().isoformat()

    doc = _Historia(ruta_logo, dir_fuentes, codigo)
    doc.abrir()
    _ficha(doc, paciente, historia)
    _alergias(doc, historia)
    _antecedentes(doc, historia)
    _evolucion(doc, _series_evolucion(datos))
    _consultas(doc, consultas)
    # Los documentos emitidos van al final y en este orden: primero lo que se
    # pidió (las órdenes), después lo que se hizo (las infiltraciones).
    _examenes(doc, datos.get("examenes"))
    _infiltraciones(doc, datos.get("infiltraciones"))
    doc.pie_impresion(cuando)
    doc.numerar_paginas()

    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    doc.output(ruta_salida)
    return ruta_salida


# =============================================================================
# 7. PRUEBA
# =============================================================================
# `py -3 app/pdf_historia.py` regenera `build/historia_prueba.pdf`, que es la
# muestra que se mira en pantalla antes de tocar la maqueta. Misma convención
# que `pdf_recipe` y `pdf_informe`.

if __name__ == "__main__":  # pragma: no cover
    #: Las mediciones de la paciente ejemplo: seis meses de control, bajando.
    _FECHAS = ("2026-02-12", "2026-03-20", "2026-06-07", "2026-07-18",
               "2026-08-18")

    def _serie(valores):
        return [{"fecha": f, "valor": v} for f, v in zip(_FECHAS, valores)]

    EJEMPLO = {
        "codigo": "EC-0001",
        "fecha": "2026-08-18",
        "paciente": {
            "nombre": "María Pérez",
            "cedula": "11222333",
            "fecha_nacimiento": "1966-03-12",
            "edad": 60,
            "sexo": "F",
            "telefono": "0414-6123456",
        },
        "historia": {
            "estado_civil": "Casada",
            "ocupacion": "Docente",
            "tipo_sangre": "O+",
            "fam_madre": "Hipertensión arterial, diabetes mellitus tipo 2",
            "fam_padre": "Cardiopatía isquémica, fallecido a los 71 años",
            "fam_hermanos": "Hermana con hipotiroidismo",
            "fam_hijos": "Dos hijos sanos",
            "alim_comidas_dia": 3,
            "alim_frutas_verduras": 4,
            "alim_pollo": 1,
            "alim_pescado": 6,
            "alim_carnes_rojas": 1,
            "alim_carbohidratos": 5,
            "alim_litros_agua": 1,
            "actividad_fisica": "Caminata 30 minutos, tres veces por semana",
            "habitacion": "Vivienda propia, de bloque, con servicios de agua y "
                          "electricidad; conviven cuatro personas.",
            "cronico_degenerativos": "Dislipidemia desde 2024",
            "alcoholismo": "Niega",
            "tabaquismo": "Niega",
            "toxicomanias": "Niega",
            "quirurgicos": "Cesárea (2001)",
            "traumaticos": "Niega",
            "ginecologicos": "GII PII CI. Menopausia a los 51 años.",
            "hospitalizaciones": "Ninguna en los últimos diez años",
            "transfusiones": "Niega",
            "alergias": "Penicilina (rash generalizado, 2019). Sulfas.",
            "notas_generales": "Paciente colaboradora, acude acompañada por su "
                               "hija.",
        },
        "evolucion": {"series": {
            "peso": _serie((84.6, 83.1, 80.1, 79.3, 78.4)),
            "imc": _serie((33.9, 33.3, 32.1, 31.8, 31.4)),
            "grasa_pct": _serie((42.1, 41.4, 39.8, 39.1, 38.3)),
            "musculo_kg": _serie((44.2, 44.5, 45.0, 45.2, 45.6)),
            "grasa_visceral": _serie((12, 12, 11, 11, 10)),
        }},
        "consultas": [
            {"fecha": "2026-08-18",
             "motivo": "Control de peso y revisión de perfil lipídico.",
             "examen_fisico": "Consciente, orientada, hidratada. Cardiopulmonar "
                              "sin alteraciones. Abdomen blando, depresible, no "
                              "doloroso.",
             "evolucion": "Refiere mejoría del descanso nocturno. Peso estable "
                          "respecto del control previo.",
             "diagnostico": "Dislipidemia mixta. Sobrepeso grado I.",
             "plan": "Dieta hipocalórica, actividad física progresiva, control "
                     "en ocho semanas.",
             "ta_sistolica": 130, "ta_diastolica": 85, "fc": 78, "fr": 16,
             "temperatura": 36.6, "spo2": 97, "peso": 78.4, "talla": 1.58,
             "imc": 31.4},
            {"fecha": "2026-06-07",
             "motivo": "Aumento de peso progresivo y somnolencia diurna.",
             "examen_fisico": "Obesidad de predominio abdominal. Resto sin "
                              "hallazgos.",
             "evolucion": "Primera consulta.",
             "diagnostico": "Sobrepeso. Descartar dislipidemia.",
             "plan": "Perfil lipídico, glicemia, TSH.",
             "ta_sistolica": 140, "ta_diastolica": 90, "fc": 84, "peso": 80.1,
             "talla": 1.58, "imc": 32.1},
        ],
        "examenes": [
            {"fecha_emision": "2026-08-18", "anulado": 0, "analisis": [
                "Perfil lipídico completo", "Glicemia en ayunas",
                "Hemoglobina glicosilada (HbA1c)", "TSH", "Creatinina",
                "TGO (AST)", "TGP (ALT)"]},
            {"fecha_emision": "2026-06-07", "anulado": 1,
             "analisis": ["Hematología completa", "Urea"]},
        ],
        "infiltraciones": [
            {"fecha": "2026-07-18", "vista": "mujer-frontal", "anulado": 0,
             "productos": [
                 {"id": "p1", "nombre": "Toxina A — marca 1", "unidad": "U",
                  "color": "#D92B2B"},
                 {"id": "p2", "nombre": "Ácido hialurónico", "unidad": "ml",
                  "color": "#157F6F"}],
             "puntos": [
                 {"orden": 1, "x": 0.42, "y": 0.23, "lado": "I",
                  "zona": "Frontal — línea media medial", "productoId": "p1",
                  "dosis": 4},
                 {"orden": 2, "x": 0.58, "y": 0.23, "lado": "D",
                  "zona": "Frontal — línea media medial", "productoId": "p1",
                  "dosis": 4},
                 {"orden": 3, "x": 0.50, "y": 0.31, "lado": "C",
                  "zona": "Glabela — prócer", "productoId": "p1", "dosis": 6},
                 {"orden": 4, "x": 0.38, "y": 0.55, "lado": "I",
                  "zona": "Surco nasogeniano", "productoId": "p2",
                  "dosis": 0.5}]},
        ],
    }

    print(generar_historia(
        EJEMPLO,
        os.path.join(pdf_comun._RAIZ, "build", "historia_prueba.pdf")))
