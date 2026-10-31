# -*- coding: utf-8 -*-
"""Composicion del PDF del informe medico — Espacio Corporal.

Carta VERTICAL (215,9 x 279,4 mm, dec. 14), membrete de Espacio Corporal
(dec. 8), firma escaneada al pie (dec. 9) y dos tipos de informe (dec. 10):

    generar_informe({"tipo": "clinico", ...}, "salida.pdf")

  * ``clinico``      — la carta en prosa que el medico usa todos los dias
                       (plantilla B del analisis, Parte B §1).
  * ``aseguradora``  — el formulario por campos que pide el seguro
                       (plantilla A: Nº de poliza, prestacion sanitaria,
                       antecedentes, motivo, diagnostico, evolucion).

El modulo es puro, como `pdf_recipe`: recibe un dict plano, escribe un PDF y
no toca la base de datos ni la configuracion.

QUE SE ARREGLO DE LAS PLANTILLAS `.docx` (y por que no es capricho)
-------------------------------------------------------------------
Las dos plantillas de referencia no son de Espacio Corporal: salieron de un
formulario de AXA Seguros con el membrete de otra clinica pegado encima
(Parte B §0). Se rehizo con la marca propia (dec. 7 y 8) y de paso se
corrigieron tres defectos MEDIDOS del original, ninguno de los cuales era una
decision de diseño:

1. **La firma se caia sola a una segunda hoja.** En la plantilla A el PDF sale
   de dos paginas y la segunda trae unicamente la firma. Aca la firma va
   pegada al ultimo bloque de contenido, en la MISMA pagina (ver `_firma`).
2. **Los recuadros eran de alto fijo** y el texto largo los desbordaba. Aca
   crecen con el contenido, y si hace falta se continuan en la pagina
   siguiente sin perder ni un renglon.
3. **El titulo estaba "centrado" con unos setenta espacios en blanco.** Aca se
   mide y se centra de verdad (`_texto_centrado`).

DECISIONES DE MAQUETA (a validar con el revisor)
------------------------------------------------
* **Sin ornamento lateral.** El ornamento vectorial es del *talonario* del
  recipe: nace del papel preimpreso, se apoya en el filo de la media carta y
  su curva esta calcada de ese escaneo a 200 dpi. Un informe medico es una
  carta limpia que a veces se fotocopia, se escanea y se manda a una
  aseguradora; una banda de tinta de 11 mm en el filo se corta al fotocopiar y
  se come tinta en cada copia. La marca se sostiene igual con el logo, el
  lockup "Salud y Bienestar", el filete teal bajo el membrete y el codigo
  "N.º" arriba a la derecha, que son las cuatro señas del recipe. Si el
  revisor prefiere el ornamento, se agrega en `pdf_comun.HojaCarta._membrete`
  espejado como en la mitad Rp.: la funcion que lo dibuja ya esta escrita.
* **"INFORME MEDICO" va acentuado: «INFORME MÉDICO».** En las dos plantillas
  esta sin tilde, pero eso es un tipeo del `.docx` (el analisis lo anota como
  "asi, sin tilde"), no un rotulo que alguien exija literal. Lo mismo con
  "Nombre del Medico" -> "Nombre del Médico". El RESTO de los rotulos de la
  plantilla A se respeta al pie de la letra, parentesis incluidos, porque esos
  si podrian ser exigencia de la aseguradora (Parte B §6, pregunta 16).
* **El titulo va en Lato bold, teal oscuro y centrado**, no en 12 pt negro
  como el `.docx`: es el mismo teal de "Rp." en el recipe.
* **Multipagina permitida.** Un informe largo es legitimo; el recipe frena
  porque el talonario tiene UNA hoja preimpresa, aca no. Las paginas que
  siguen repiten el membrete y llevan "Pagina 2 de 3" al pie, para que una
  hoja suelta se pueda devolver a su lugar.
* **La firma no repite la colegiatura debajo.** `recursos/firma.png` ya trae
  el nombre, el R.I.F., el M.P.P.S. y el COMEZU impresos bajo el trazo, y los
  mismos numeros estan arriba en la cabecera del medico. Escribirlos una
  tercera vez seria ruido.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Mapping

try:  # como paquete (``from app import pdf_informe``)
    from . import pdf_comun
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import pdf_comun  # type: ignore[no-redef]

# Atajos a lo compartido. Se toman del modulo (y no con `from pdf_comun
# import ...`) porque `pdf_comun` se resuelve de dos formas distintas segun
# como se cargue la app —paquete o `app/` en el sys.path—, igual que en
# `rutas.py`.
ANCHO_UTIL_MM = pdf_comun.ANCHO_UTIL_MM
GUIA_DER_MM = pdf_comun.GUIA_DER_MM
MARGEN_IZQ_MM = pdf_comun.MARGEN_IZQ_MM
INTERLINEA_MM = pdf_comun.INTERLINEA_MM
GRIS_DATO = pdf_comun.GRIS_DATO
GRIS_ROTULO = pdf_comun.GRIS_ROTULO
GRIS_RECUADRO = pdf_comun.GRIS_RECUADRO
TEAL_MEDIO = pdf_comun.TEAL_MEDIO
TEAL_OSCURO = pdf_comun.TEAL_OSCURO

# =============================================================================
# 1. TIPOS DE INFORME
# =============================================================================

#: Los mismos dos que acepta `basedatos.crear_informe` (dec. 10).
TIPO_CLINICO = "clinico"
TIPO_ASEGURADORA = "aseguradora"
TIPOS = (TIPO_CLINICO, TIPO_ASEGURADORA)

TITULO = "INFORME MÉDICO"

# =============================================================================
# 2. MEDIDAS
# =============================================================================

PT_TITULO = 16.0                 # "INFORME MÉDICO", bold, centrado
TITULO_BASE_Y_MM = 60.0
CUERPO_INFORME_Y0_MM = 72.0      # primera linea de base debajo del titulo

PT_CUERPO = 11.0
PT_ROTULO_BLOQUE = 10.5          # los rotulos largos de la plantilla A
PT_PIE = 9.5

#: Aire interno de los cajones. Es el mismo de las celdas de `fila_recuadro`
#: (que vive en `pdf_comun` porque la historia tambien la usa).
CELDA_PAD_MM = pdf_comun.CELDA_PAD_MM

#: Alto minimo de los cajones de la plantilla A, en renglones — o sea: como se
#: ve un cajon VACIO. El original reservaba 4 renglones (7 para el motivo)
#: porque eran cajas de alto fijo y todo tenia que entrar ahi adentro; las de
#: aca crecen con el texto, asi que el minimo ya no cumple esa funcion y
#: guardarlo alto solo empuja la firma a una segunda hoja sin necesidad —
#: justamente lo que se vino a arreglar. Con estos valores un informe real
#: (los cuatro campos escritos, como el de `build/`) entra en UNA pagina.
MINIMO_CAJON = 2
MINIMO_CAJON_MOTIVO = 4

FIRMA_ANCHO_MM = pdf_comun.FIRMA_ANCHO_MM
FIRMA_ALTO_MM = FIRMA_ANCHO_MM / pdf_comun.FIRMA_PROPORCION   # ~25,0 mm
FIRMA_AIRE_MM = 6.0

# -- paginas de anexo (dec. 12 y Parte C §5) ---------------------------------
# La legibilidad manda: lo medido dice que el informe de la bascula se lee
# impreso a pagina completa carta vertical (~136 ppp efectivos) y NO se lee en
# media carta. Por eso estas paginas usan un membrete compacto —solo el rotulo
# de seccion y el codigo del paciente— en vez del membrete entero: cada
# milimetro que se le saca al encabezado se lo gana la imagen.
ANEXO_ROTULO_BASE_Y_MM = 15.0
ANEXO_FILETE_Y_MM = 17.5
ANEXO_IMG_Y0_MM = 23.0
ANEXO_IMG_Y1_MM = 254.0
ANEXO_PIE_BASE_Y_MM = 260.5
ANEXO_TITULO = "ANEXOS"


# =============================================================================
# 3. ERRORES
# =============================================================================

class InformeError(pdf_comun.DocumentoError):
    """Error al componer el PDF del informe."""


class TipoDesconocidoError(InformeError):
    """El tipo de informe no es `clinico` ni `aseguradora`."""

    def __init__(self, tipo: Any):
        self.tipo = tipo
        super().__init__(
            f"No existe el tipo de informe «{tipo}». Elegí «Informe médico» "
            "(clinico) o «Informe para la aseguradora» (aseguradora)."
        )


class RecursoFaltanteError(pdf_comun.RecursoFaltanteError, InformeError):
    """Falta el logo, la firma o alguna de las fuentes Lato."""


class AnexoNoEncontradoError(InformeError):
    """Se pidió anexar una imagen que no está en el disco (dec. 12).

    Se corta ANTES de escribir el PDF: un informe al que le falta el anexo que
    el médico marcó es peor que un informe que no salió, porque nadie se da
    cuenta hasta que ya lo entregó.
    """

    def __init__(self, ruta: Any, numero: int):
        self.ruta = str(ruta)
        self.numero = numero
        super().__init__(
            f"No encuentro la imagen del anexo {numero}. Fijate que siga en su "
            "carpeta —si la moviste o la borraste, volvé a adjuntarla desde la "
            f"historia— y generá el informe de nuevo. (La buscaba en: {ruta})"
        )


class AnexoNoEsImagenError(InformeError):
    """El anexo es un PDF (o algo que no se puede pegar en una página).

    Dec. 11 acepta PDF entre los anexos de la historia, pero un PDF no se
    incrusta como imagen: se entrega aparte, con su propio grapado.
    """

    def __init__(self, ruta: Any, numero: int):
        self.ruta = str(ruta)
        self.numero = numero
        super().__init__(
            f"El anexo {numero} es un {os.path.splitext(str(ruta))[1].lstrip('.').upper() or 'archivo'} "
            "y no se puede pegar adentro del informe. Destildalo de los anexos "
            "e imprimilo aparte, junto con el informe."
        )


# =============================================================================
# 4. AYUDAS DE TEXTO
# =============================================================================

def _t(datos: Mapping[str, Any], clave: str, defecto: str = "") -> str:
    """Un campo del dict, ya recortado. Nunca `None`."""
    valor = datos.get(clave)
    if valor is None:
        return defecto
    texto = str(valor).strip()
    return texto if texto else defecto


#: Extensiones que fpdf2 sabe pegar en una página.
_IMAGENES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def frase_inicial(sexo: Any, edad: Any, motivo: str = "",
                  antecedentes: str = "") -> str:
    """La primera frase del informe clínico, autoarmada (dec. 10).

    Es la fórmula literal del ejemplo real (Parte B §1):

        "Se trata de paciente femenino de 60 años de edad, quien consulta por
         presentar aumento de peso progresivo con antecedentes de dislipidemia
         y trastornos del sueño."

    La devuelve para que la pantalla la ponga en el recuadro **y el médico la
    edite**: dec. 10 dice explícitamente que es editable, así que este módulo
    no la usa por su cuenta ni la impone si el cuerpo llegó escrito.
    """
    letra = str(sexo or "").strip()[:1].upper()
    genero = "femenino" if letra == "F" else "masculino" if letra == "M" else ""
    partes = ["Se trata de paciente"]
    if genero:
        partes.append(genero)
    try:
        anios = int(str(edad).strip())
    except (TypeError, ValueError):
        anios = None
    if anios is not None:
        partes.append(f"de {anios} años de edad")
    frase = " ".join(partes)
    motivo = str(motivo or "").strip().rstrip(".")
    if motivo:
        frase += f", quien consulta por presentar {motivo}"
    antecedentes = str(antecedentes or "").strip().rstrip(".")
    if antecedentes:
        frase += f" con antecedentes de {antecedentes}"
    return frase + "."


# =============================================================================
# 5. COMPOSITOR
# =============================================================================

class _Informe(pdf_comun.HojaCarta):
    """Lienzo del informe. La API pública son las funciones de abajo."""

    _ERROR_RECURSO = RecursoFaltanteError

    def __init__(self, ruta_logo: str, dir_fuentes: str, ruta_firma: str,
                 codigo: str = "") -> None:
        super().__init__(ruta_logo, dir_fuentes, codigo)
        self.ruta_firma = ruta_firma

    # ---------------------------------------------------------------- título
    def _titulo(self) -> None:
        self._texto_centrado(MARGEN_IZQ_MM, GUIA_DER_MM, TITULO_BASE_Y_MM,
                             TITULO, "B", PT_TITULO, TEAL_OSCURO)
        self.pluma_y = CUERPO_INFORME_Y0_MM

    def abrir(self) -> None:
        """Primera página: membrete + título."""
        self.nueva_pagina()
        self._titulo()

    # ---------------------------------------------------------------- cajones
    def cajon(self, rotulo: str, valor: str, minimo: int = MINIMO_CAJON) -> None:
        """Rótulo suelto arriba y, debajo, el recuadro con lo que se escribió.

        Es la forma de la plantilla A, con la diferencia que importa: el cajón
        **crece** con el contenido en vez de desbordarse, y si el texto es tan
        largo que no entra en lo que queda de hoja, sigue en la siguiente sin
        perder un renglón (el cajón se corta y se vuelve a abrir arriba).
        """
        self.asegurar(INTERLINEA_MM * (2 + minimo))
        self.parrafo(rotulo, estilo="", pt=PT_ROTULO_BLOQUE, color=TEAL_OSCURO)

        ancho = ANCHO_UTIL_MM - 2 * CELDA_PAD_MM
        renglones = self._envolver(valor or "", ancho, "", PT_CUERPO)
        renglones = [r for r in renglones if r.strip()] or [""]

        i = 0
        while True:
            self.asegurar(INTERLINEA_MM * 2)
            y0 = self.pluma_y - INTERLINEA_MM * 0.8
            caben = max(int((pdf_comun.CUERPO_Y1_MM - self.pluma_y)
                            // INTERLINEA_MM), 1)
            trozo = renglones[i:i + caben]
            # El mínimo del formulario se respeta salvo que no quepa: nunca se
            # deja crecer la caja por debajo del pie de la hoja.
            alto_renglones = min(max(len(trozo), minimo if i == 0 else 1), caben)
            y = self.pluma_y
            for renglon in trozo:
                self._texto(MARGEN_IZQ_MM + CELDA_PAD_MM, y, renglon, "",
                            PT_CUERPO, GRIS_DATO)
                y += INTERLINEA_MM
            alto = (CELDA_PAD_MM + alto_renglones * INTERLINEA_MM
                    + CELDA_PAD_MM * 0.6)
            self._recuadro(MARGEN_IZQ_MM, y0, GUIA_DER_MM, y0 + alto)
            self.pluma_y = y0 + alto + INTERLINEA_MM * 0.9
            i += len(trozo)
            if i >= len(renglones):
                break
            self.nueva_pagina()

    # ---------------------------------------------------------------- firma
    def firma(self, cierre: str = "", *, rotulo: str = "") -> None:
        """El cierre (ciudad y fecha, o «Firma del facultativo») y la firma.

        Van juntos y en la MISMA página a propósito: en el `.docx` original la
        firma se caía sola a la hoja 2 y eso no era diseño, era un defecto
        (Parte B §1). Se reserva de una vez el alto del cierre más el de la
        imagen, así nunca queda una hoja con nada más que la rúbrica.
        """
        if not os.path.isfile(self.ruta_firma):
            raise RecursoFaltanteError(
                "Falta la firma escaneada del médico, así que el informe "
                "saldría sin firmar. Esperada en: " + str(self.ruta_firma)
            )
        renglones = (1 if cierre else 0) + (1 if rotulo else 0)
        self.asegurar(INTERLINEA_MM * renglones + FIRMA_AIRE_MM + FIRMA_ALTO_MM)
        if cierre:
            self._texto(MARGEN_IZQ_MM, self.pluma_y, cierre, "", PT_CUERPO,
                        GRIS_DATO)
            self.pluma_y += INTERLINEA_MM
        if rotulo:
            self._texto(MARGEN_IZQ_MM, self.pluma_y, rotulo, "",
                        PT_ROTULO_BLOQUE, TEAL_OSCURO)
            self.pluma_y += INTERLINEA_MM
        self.pluma_y += FIRMA_AIRE_MM
        self.image(self.ruta_firma, x=MARGEN_IZQ_MM, y=self.pluma_y,
                   w=FIRMA_ANCHO_MM, h=FIRMA_ALTO_MM)
        self.pluma_y += FIRMA_ALTO_MM

    # ---------------------------------------------------------------- anexos
    def pagina_anexo(self, numero: int, ruta: str, tipo: str, fecha: Any) -> None:
        """Una página completa con la imagen del anexo (dec. 12, Parte C §5).

        Membrete compacto: solo «ANEXOS» a la izquierda y el código del
        paciente a la derecha. Lo medido manda — el informe de la báscula tiene
        renglones de 6 px y solo se lee impreso a página entera —, así que el
        encabezado cede el espacio y la imagen se lleva 232 mm de alto.
        """
        self.add_page()
        self._texto(MARGEN_IZQ_MM, ANEXO_ROTULO_BASE_Y_MM, ANEXO_TITULO, "B",
                    PT_ROTULO_BLOQUE, TEAL_OSCURO)
        if self.codigo:
            self._codigo_der(GUIA_DER_MM, ANEXO_ROTULO_BASE_Y_MM, self.codigo,
                             pt_codigo=11.0, pt_rotulo=9.5, separacion=1.5)
        self._raya(MARGEN_IZQ_MM, GUIA_DER_MM, ANEXO_FILETE_Y_MM, 0.4, TEAL_MEDIO)

        caja_alto = ANEXO_IMG_Y1_MM - ANEXO_IMG_Y0_MM
        ancho_px, alto_px = pdf_comun.medidas_imagen(ruta)
        ancho, alto = pdf_comun.encajar(ancho_px, alto_px, ANCHO_UTIL_MM, caja_alto)
        x = MARGEN_IZQ_MM + (ANCHO_UTIL_MM - ancho) / 2.0
        y = ANEXO_IMG_Y0_MM + (caja_alto - alto) / 2.0
        self.image(ruta, x=x, y=y, w=ancho, h=alto)

        pie = f"Anexo {numero}"
        tipo = str(tipo or "").strip()
        fecha_texto = pdf_comun.formatear_fecha(fecha)
        detalle = ", ".join(p for p in (tipo, fecha_texto) if p)
        if detalle:
            pie = f"{pie} — {detalle}"
        self._texto_centrado(MARGEN_IZQ_MM, GUIA_DER_MM, ANEXO_PIE_BASE_Y_MM,
                             pie, "", PT_PIE, GRIS_ROTULO)
        self.pluma_y = pdf_comun.CUERPO_Y1_MM   # esta página ya está completa


# =============================================================================
# 6. LOS DOS CUERPOS
# =============================================================================

def _cabecera_medico(doc: _Informe, datos: Mapping[str, Any], *,
                     con_fecha: bool) -> None:
    """La tabla del médico. Rótulos de la plantilla A (Parte B §1)."""
    doc.fila_recuadro([
        ("Nombre del Médico", _t(datos, "medico_nombre"), 0.50),
        ("COMEZU", _t(datos, "medico_comezu"), 0.25),
        ("MPPS", _t(datos, "medico_mpps"), 0.25),
    ])
    especialidad = _t(datos, "medico_especialidad")
    if con_fecha:
        doc.fila_recuadro([
            ("Especialidad", especialidad, 0.50),
            ("Fecha del Informe", pdf_comun.formatear_fecha(datos.get("fecha")), 0.50),
        ])
    elif especialidad:
        doc.fila_recuadro([("Especialidad", especialidad, 1.0)])


def _cuerpo_clinico(doc: _Informe, datos: Mapping[str, Any]) -> None:
    """La carta clínica en prosa (plantilla B).

    Orden literal del ejemplo real: paciente con su C.I., el párrafo narrativo,
    "Diagnóstico:", "Tratamiento indicado:", y al pie la ciudad con la fecha
    larga y la firma.
    """
    _cabecera_medico(doc, datos, con_fecha=False)
    doc.espacio(INTERLINEA_MM * 0.8)

    nombre = _t(datos, "paciente_nombre")
    cedula = _t(datos, "paciente_cedula")
    if nombre or cedula:
        # El ejemplo real dice «María  Perez , C.I. 11222333»: los espacios de
        # más son tipeo del `.docx`, no un rótulo que haya que respetar.
        linea = nombre + (f", C.I. {cedula}" if cedula else "")
        doc.parrafo(linea, estilo="B", pt=PT_CUERPO, color=GRIS_DATO)
        doc.espacio(INTERLINEA_MM * 0.6)

    doc.parrafo(_t(datos, "cuerpo"))

    diagnostico = _t(datos, "diagnostico")
    if diagnostico:
        doc.espacio(INTERLINEA_MM * 0.6)
        doc.rotulo("Diagnóstico:")
        doc.parrafo(diagnostico, x=MARGEN_IZQ_MM + 8.0)

    tratamiento = _t(datos, "tratamiento")
    if tratamiento:
        doc.espacio(INTERLINEA_MM * 0.6)
        doc.rotulo("Tratamiento indicado:")
        doc.parrafo(tratamiento, x=MARGEN_IZQ_MM + 8.0)

    doc.espacio(INTERLINEA_MM * 1.4)
    ciudad = _t(datos, "ciudad")
    larga = pdf_comun.fecha_larga(datos.get("fecha"))
    cierre = "; ".join(p for p in (ciudad, larga) if p)
    doc.firma(cierre)


def _cuerpo_aseguradora(doc: _Informe, datos: Mapping[str, Any]) -> None:
    """El formulario de la aseguradora (plantilla A), con sus rótulos literales.

    Los rótulos largos van tal cual estaban, paréntesis incluidos: si la
    aseguradora los exige así, la app no puede haberlos "mejorado" (Parte B §6,
    pregunta 16).
    """
    _cabecera_medico(doc, datos, con_fecha=True)
    doc.espacio(INTERLINEA_MM * 0.6)

    doc.rotulo("Datos de la prestación", pt=PT_ROTULO_BLOQUE + 0.5)
    doc.fila_recuadro([
        ("Nombre del Paciente", _t(datos, "paciente_nombre"), 0.50),
        ("Nº de póliza", _t(datos, "numero_poliza"), 0.50),
    ])
    doc.fila_recuadro([
        ("Prestación sanitaria", _t(datos, "prestacion_sanitaria"), 1.0),
    ])
    doc.espacio(INTERLINEA_MM * 0.6)

    doc.cajon(
        "Antecedentes patológicos del paciente "
        "(indicar fecha de inicio de la patología)",
        _t(datos, "antecedentes"),
    )
    doc.cajon(
        "Motivo de la consulta y/o ingreso (indicar la fecha de inicio de la "
        "enfermedad de los síntomas y del diagnóstico.)",
        _t(datos, "motivo_consulta"), minimo=MINIMO_CAJON_MOTIVO,
    )
    doc.cajon("Diagnóstico", _t(datos, "diagnostico"))
    doc.cajon("Evolución", _t(datos, "evolucion"))

    doc.espacio(INTERLINEA_MM * 0.4)
    doc.firma("", rotulo="Firma del facultativo")


_CUERPOS = {
    TIPO_CLINICO: _cuerpo_clinico,
    TIPO_ASEGURADORA: _cuerpo_aseguradora,
}


# =============================================================================
# 7. API PUBLICA
# =============================================================================

def normalizar_tipo(tipo: Any) -> str:
    """`clinico` o `aseguradora`; vacío cae en `clinico` (dec. 10: es el diario)."""
    texto = str(tipo or "").strip().lower() or TIPO_CLINICO
    if texto not in TIPOS:
        raise TipoDesconocidoError(tipo)
    return texto


def _validar_anexos(anexos: Any) -> list[dict[str, Any]]:
    """Revisa los anexos ANTES de dibujar nada.

    Si falta un archivo o alguien marcó un PDF, se corta acá: mejor no emitir
    el informe que emitirlo sin el anexo que el médico creía estar mandando.
    """
    limpios: list[dict[str, Any]] = []
    for numero, anexo in enumerate(anexos or (), start=1):
        if isinstance(anexo, (str, os.PathLike)):
            anexo = {"ruta": anexo}
        if not isinstance(anexo, Mapping):
            continue
        ruta = str(anexo.get("ruta") or "").strip()
        if not ruta or not os.path.isfile(ruta):
            raise AnexoNoEncontradoError(ruta, numero)
        if os.path.splitext(ruta)[1].lower() not in _IMAGENES:
            raise AnexoNoEsImagenError(ruta, numero)
        limpios.append({
            "ruta": ruta,
            "tipo": str(anexo.get("tipo") or "").strip(),
            "fecha": anexo.get("fecha"),
        })
    return limpios


def generar_informe(datos: Mapping[str, Any], ruta_salida: str, *,
                    ruta_logo: str = pdf_comun.RUTA_LOGO_DEFECTO,
                    dir_fuentes: str = pdf_comun.DIR_FUENTES_DEFECTO,
                    ruta_firma: str = pdf_comun.RUTA_FIRMA_DEFECTO) -> str:
    """Escribe el PDF del informe y devuelve la ruta de salida.

    `datos` es un dict plano — el módulo NO consulta la base de datos:

        tipo                  'clinico' | 'aseguradora'   (dec. 10)
        codigo                'EC-0001'  el del PACIENTE, arriba a la derecha
        fecha                 '2026-08-18' o '18/08/2026' o un date; si falta,
                              hoy
        paciente_nombre       str
        paciente_cedula       str        (C.I., solo en el clínico)
        medico_nombre         str  \\
        medico_especialidad   str   |    de Configuración (dec. 9)
        medico_comezu         str   |
        medico_mpps           str  /
        ciudad                str        'Maracaibo' (pie del clínico)

        clínico
        cuerpo                str        el párrafo en prosa
        diagnostico           str
        tratamiento           str

        aseguradora
        numero_poliza         str
        prestacion_sanitaria  str
        antecedentes          str
        motivo_consulta       str
        diagnostico           str
        evolucion             str

        anexos                list       OPT-IN (dec. 12). Cada uno es un dict
                                         {ruta, tipo, fecha} —o una ruta
                                         suelta—; sale una página completa por
                                         imagen, al final.

    Levanta `TipoDesconocidoError`, `AnexoNoEncontradoError`,
    `AnexoNoEsImagenError` y `RecursoFaltanteError`. **No** levanta por
    contenido largo: un informe de tres páginas es legítimo (a diferencia del
    récipe, que tiene una hoja preimpresa y no más).
    """
    tipo = normalizar_tipo(datos.get("tipo"))
    anexos = _validar_anexos(datos.get("anexos"))
    if not os.path.isfile(ruta_logo):
        raise RecursoFaltanteError(f"Falta el logo. Esperado en: {ruta_logo}")

    datos = dict(datos)
    if not str(datos.get("fecha") or "").strip():
        datos["fecha"] = date.today().isoformat()

    doc = _Informe(ruta_logo, dir_fuentes, ruta_firma, _t(datos, "codigo"))
    doc.abrir()
    _CUERPOS[tipo](doc, datos)
    for numero, anexo in enumerate(anexos, start=1):
        doc.pagina_anexo(numero, anexo["ruta"], anexo["tipo"], anexo["fecha"])
    doc.numerar_paginas()

    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    doc.output(ruta_salida)
    return ruta_salida


# =============================================================================
# 8. PRUEBA
# =============================================================================

if __name__ == "__main__":  # pragma: no cover
    RAIZ = pdf_comun._RAIZ
    MEDICO = {
        "medico_nombre": "Dr. Eleazar Shiera Bastidas",
        "medico_especialidad": "Medicina Interna",
        "medico_comezu": "7414",
        "medico_mpps": "34846",
        "ciudad": "Maracaibo",
    }
    CLINICO = dict(MEDICO, **{
        "tipo": "clinico",
        "codigo": "EC-0001",
        "fecha": "2026-08-18",
        "paciente_nombre": "María Pérez",
        "paciente_cedula": "11222333",
        "cuerpo": frase_inicial("F", 60, "aumento de peso progresivo",
                                "dislipidemia y trastornos del sueño"),
        "diagnostico": "Dislipidemia",
        "tratamiento": "Se indican exámenes pertinentes diagnósticos",
    })
    print(generar_informe(CLINICO,
                          os.path.join(RAIZ, "build", "informe_prueba_clinico.pdf")))
