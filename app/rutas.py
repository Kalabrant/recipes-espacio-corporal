# -*- coding: utf-8 -*-
"""Endpoints Flask de la app de récipes (§7-A de las instrucciones).

Todo es local: el servidor escucha en `127.0.0.1` con un puerto libre que
elige `main.py`, y la interfaz que lo consume vive en `app/web/`. **Ninguna
ruta sale a internet** (§2.1): no hay CDN, ni fuentes remotas, ni telemetría.

Contrato de la API (JSON UTF-8; los errores son
``{"error": "qué hacer"}`` con estado 4xx/5xx):

    Nuevo récipe (§7-A)
    GET  /api/sugerencias/pacientes?q=
    GET  /api/sugerencias/medicamentos?q=
    GET  /api/sugerencias/dosis?medicamento_id=&q=
    GET  /api/sugerencias/indicaciones?q=
    GET  /api/sugerencias/diagnosticos?q=
    POST /api/medir           {paciente_nombre, items, indicaciones_generales}
    POST /api/vista-previa    (mismo cuerpo que /api/recipes)
    POST /api/recipes         -> {"codigo", "ruta_pdf", "aviso"?}

    Historial (§7-B)
    GET  /api/recipes?q=&desde=&hasta=  -> {"resultados": [...], "aviso"?}
    GET  /api/recipes/<id>/pdf          -> el MISMO archivo guardado
    POST /api/recipes/<id>/abrir        -> lo abre para reimprimir
    POST /api/recipes/<id>/anular       {motivo} -> el récipe actualizado

    Configuración (§7-C, §10)
    GET  /api/config          -> datos del médico, prefijo, PIN, tutorial, versión
    POST /api/config          -> los guarda (incluido {tutorial_visto})
    GET  /api/config/logo     -> el logo que hoy se imprime (para verlo)
    POST /api/config/logo     multipart "archivo" (PNG/JPG)
    POST /api/config/pin      {pin_nuevo, pin_actual}
    POST /api/pin/verificar   {pin} -> {"ok": bool}
    POST /api/respaldo        -> {"archivo", "tamano_kb"}
    POST /api/abrir-carpeta   -> abre la carpeta de datos en el Explorador

    GET  /                    index.html, y los estáticos desde app/web/

Los mensajes de error dicen qué hacer, no qué falló (§7, "Diseño").

**El PIN no es un middleware.** El backend solo dice si hay PIN
(``/api/config`` → ``pin_activo``) y si el que escribieron es el correcto
(``/api/pin/verificar``). El bloqueo es una pantalla del lado de la interfaz:
§10 lo define como "una barrera contra el que pasa frente a la computadora",
no como seguridad fuerte, y la API escucha solo en 127.0.0.1 con un puerto al
azar. Poner sesiones y cookies acá daría una sensación de seguridad que no
existe (quien tenga la máquina tiene el `recipes.db`) a cambio de complicar
todos los pedidos.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from flask import Flask, g, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

try:  # como paquete (``from app import rutas``)
    from . import basedatos, codigos, excel, pdf_recipe, respaldo
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import basedatos  # type: ignore[no-redef]
    import codigos  # type: ignore[no-redef]
    import excel  # type: ignore[no-redef]
    import pdf_recipe  # type: ignore[no-redef]
    import respaldo  # type: ignore[no-redef]


# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

def _raiz_recursos() -> Path:
    """Raíz de los archivos empaquetados (interfaz, logo, fuentes).

    Desde el código fuente es la raíz del proyecto (donde viven `app/`,
    `recursos/`, `build/`). Congelado con PyInstaller `--onedir` (§11.1), los
    datos de `--add-data` viven en ``sys._MEIPASS`` —la carpeta ``_internal``
    al lado del `.exe`—, porque el `.py` ya no es un archivo suelto en disco.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


#: Raíz del proyecto (donde viven `app/`, `recursos/`, `build/`).
RAIZ_PROYECTO = _raiz_recursos()

#: Carpeta de la interfaz. La escribe otro módulo del equipo; acá solo se sirve.
#: Congelada queda en ``_internal\\web`` (el `--add-data` de `app/web` → `web`).
DIR_WEB = (RAIZ_PROYECTO / "web" if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent / "web")

#: Máximo de caracteres del nombre del paciente dentro del nombre de archivo (§4).
MAX_NOMBRE_ARCHIVO = 60

#: Válvula de seguridad contra cuerpos absurdos. **No es un tope de producto**:
#: §7 pide "sin tope fijo", y quien avisa de verdad es `medir_contenido`, que
#: rechaza mucho antes por espacio en la hoja.
MAX_ITEMS = 200

#: Recorte defensivo de los textos libres, para que un pegado accidental de
#: media enciclopedia no llegue a la base ni al medidor del PDF.
MAX_TEXTO_CORTO = 300
MAX_TEXTO_LARGO = 2000

#: Código de relleno de la vista previa (§6.2: un formulario abandonado no
#: quema un número, así que la previa no pide ninguno).
#:
#: El contrato lo escribe ``EC-␣␣␣␣-␣␣␣␣`` con U+2423 (el símbolo de espacio
#: abierto). Lato no trae ese glifo —se verificó sobre `recursos/fuentes/`— y
#: saldría un hueco mudo en el PDF, así que se rellena con guiones bajos, que
#: sí están en la fuente y se leen igual de claro: "acá va a ir un número".
RELLENO_CODIGO = "____"

#: Versión que se muestra en Configuración. Se sube a mano al empaquetar (§11).
VERSION_APP = "1.0.0"

#: Máximo de resultados del Historial (§7-B). Buscar es para encontrar uno, no
#: para leer la base entera: si no aparece, se afina la búsqueda o las fechas.
LIMITE_HISTORIAL = 200

_RE_FECHA_SIMPLE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------
# Configuración: qué clave de `config` guarda cada campo (§5, §7-C)
# --------------------------------------------------------------------------

#: Campo de la API -> clave en la tabla `config`. Las claves llevan el
#: prefijo `medico_` porque `config` es una bolsa clave/valor compartida con
#: el prefijo del código, el hash del PIN y la fecha del último respaldo.
CAMPOS_MEDICO: dict[str, str] = {
    "nombre": "medico_nombre",
    "especialidad": "medico_especialidad",
    "mpps": "medico_mpps",
    "colegio": "medico_colegio",
    "rif": "medico_rif",
    "direccion": "medico_direccion",
    "telefonos": "medico_telefonos",
}

#: Largo máximo de cada campo del médico. Son renglones de encabezado, no
#: párrafos; el recorte evita que un pegado accidental rompa el PDF.
MAX_CAMPO_MEDICO = 200

#: Marca de que el registro Excel quedó desactualizado porque estaba abierto.
#: Se limpia sola en el próximo guardado o anulación que sí pueda escribirlo (§9).
CLAVE_EXCEL_PENDIENTE = "excel_pendiente"

#: Marca de que el médico ya vio el tutorial de primer uso. Vale ``"1"`` una vez
#: que lo terminó **o** lo saltó; ausente o vacía significa "todavía no".
#:
#: Vive en `config` y no en el navegador (`localStorage`) a propósito: la ventana
#: es pywebview y su almacenamiento local es una carpeta de perfil que se puede
#: recrear en cualquier reinstalación o cambio de versión del WebView. El tutorial
#: volvería a aparecer solo, y para el médico eso se lee como que la app se rompió.
#: En `config` la marca viaja con sus datos, entra en el respaldo y se restaura con
#: ellos.
CLAVE_TUTORIAL = "tutorial_visto"

#: Aviso genérico si el Excel falla por algo que no es "está abierto".
AVISO_EXCEL_GENERICO = (
    "El récipe se guardó, pero no se pudo actualizar el registro de Excel. "
    "Se vuelve a intentar solo en el próximo récipe."
)


# --------------------------------------------------------------------------
# Logo (§7-C)
# --------------------------------------------------------------------------

#: Ancho mínimo aceptable del logo, en píxeles. El lockup se imprime a 21,7 mm
#: de ancho (ver `build/analisis-modelo.md`): 350 px ahí son ~410 ppp, que es
#: nitidez de imprenta. Por debajo de eso se ven los dientes en el papel, y el
#: PDF no tiene cómo inventar los píxeles que faltan.
ANCHO_MINIMO_LOGO = 350

#: Tope del archivo subido. Un logo son unos cientos de KB; 20 MB es holgado
#: y evita que un arrastre equivocado (un video, un PSD) se cargue en memoria.
MAX_BYTES_LOGO = 20 * 1024 * 1024

FORMATOS_LOGO = ("PNG", "JPEG")

#: Umbrales de la limpieza de fondo de `build/analisis-modelo.md` §5.3.
#:
#: `build/preparar_recursos.py` hace esto mismo, pero **no se importa**: ese
#: script es un paso de preparación que se corre a mano y está escrito con
#: NumPy, que no es una dependencia de la app (§3) y no se empaqueta. Importarlo
#: metería NumPy adentro del instalador para limpiar una imagen por año. Acá
#: van los dos mismos umbrales, aplicados con las primitivas de Pillow.
UMBRAL_NEUTRALIZAR = 242
UMBRAL_BLANCO = 252


# --------------------------------------------------------------------------
# PIN (§10)
# --------------------------------------------------------------------------

#: Clave de `config` con el hash del PIN. Vacía o ausente = sin PIN.
CLAVE_PIN = "pin_hash"

#: Formato guardado: ``pbkdf2$iteraciones$sal_hex$hash_hex``. Las iteraciones
#: viajan adentro para poder subirlas mañana sin dejar afuera a los PIN viejos.
ALGORITMO_PIN = "pbkdf2"
ITERACIONES_PIN = 200_000
BYTES_SAL_PIN = 16

_RE_PIN = re.compile(r"^[0-9]{4,6}$")

#: Demora fija de la verificación. §10 dice explícitamente que el PIN no es
#: seguridad fuerte, así que no hay bloqueo por intentos —dejar al médico
#: afuera de sus propios récipes sería peor que el riesgo—, pero media
#: segundo alcanza para que probar los diez mil PIN de cuatro dígitos a mano
#: deje de ser un rato y pase a ser una tarde.
DEMORA_VERIFICAR_PIN = 0.5


# --------------------------------------------------------------------------
# Errores
# --------------------------------------------------------------------------

class ErrorEntrada(ValueError):
    """Lo que mandó la interfaz no alcanza para seguir. Se responde 400.

    El texto del error se le muestra tal cual al médico: tiene que decirle
    qué hacer ("Escribí el nombre del paciente"), no qué falló adentro.
    """

    estado = 400


class _NoEncontrado(ErrorEntrada):
    """Lo que se pidió no está (récipe borrado de la lista, PDF movido). 404.

    Hereda de `ErrorEntrada` para reusar el mismo manejador: el texto sigue
    siendo una instrucción para el médico, lo único que cambia es el estado.
    """

    estado = 404


# --------------------------------------------------------------------------
# Nombre del archivo PDF (§4)
# --------------------------------------------------------------------------

#: Caracteres que Windows no admite en un nombre de archivo.
_PROHIBIDOS_WINDOWS = r'<>:"/\|?*'

#: Nombres de dispositivo reservados por Windows (no pueden ser un archivo).
_RESERVADOS_WINDOWS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{n}" for n in range(1, 10)),
    *(f"LPT{n}" for n in range(1, 10)),
}

_NO_ALFANUMERICO = re.compile(r"[^A-Za-z0-9\-]+")
_GUIONES = re.compile(r"-{2,}")


def sanitizar_nombre_archivo(nombre: str | None, maximo: int = MAX_NOMBRE_ARCHIVO) -> str:
    """Convierte el nombre del paciente en un pedazo de nombre de archivo seguro (§4).

    Reglas, en este orden:

    1. Se sacan los acentos y la eñe (``Núñez`` -> ``Nunez``): §4 pide nombres
       sin tildes, y así el archivo se copia entre máquinas sin sorpresas de
       codificación.
    2. Se eliminan los caracteres que Windows prohíbe (``<>:"/\\|?*``), los de
       control y cualquier otro signo raro; todo lo que no sea letra ASCII,
       dígito o guion se vuelve guion. Los espacios pasan a guion.
    3. El guion bajo también se vuelve guion: ``_`` es el separador de los tres
       campos del nombre de archivo (código, paciente, fecha) y dejarlo adentro
       del nombre haría ambiguo el archivo al leerlo.
    4. Se recorta a `maximo` caracteres (60 por defecto, §4) y se limpian los
       guiones y puntos de los extremos —Windows no tolera un nombre terminado
       en punto ni en espacio—.
    5. Si después de todo eso no queda nada (un nombre escrito solo con signos,
       o en un alfabeto no latino), se devuelve ``Paciente``: el récipe se emite
       igual, el nombre real vive en la base y adentro del PDF.

    No adivina cuál es el apellido ni reordena nada: el archivo conserva el
    orden y las mayúsculas que escribió el médico. El ejemplo ``PEREZ-Juan``
    de §4 sale solo cuando el médico escribe "PEREZ Juan".
    """
    texto = basedatos.limpiar(nombre)
    if not texto:
        return "Paciente"

    # 1. Sin acentos ni eñes.
    descompuesto = unicodedata.normalize("NFD", texto)
    ascii_puro = "".join(c for c in descompuesto if not unicodedata.combining(c))

    # 2 y 3. Solo letras ASCII, dígitos y guiones.
    for prohibido in _PROHIBIDOS_WINDOWS:
        ascii_puro = ascii_puro.replace(prohibido, " ")
    limpio = _NO_ALFANUMERICO.sub("-", ascii_puro)
    limpio = _GUIONES.sub("-", limpio).strip("-. ")

    # 4. Largo máximo.
    if len(limpio) > maximo:
        limpio = limpio[:maximo].strip("-. ")

    # 5. Red de contención.
    if not limpio:
        return "Paciente"
    if limpio.upper() in _RESERVADOS_WINDOWS:
        return f"{limpio}-paciente"
    return limpio


def ruta_pdf_nueva(dir_datos: Path, codigo: str, paciente_nombre: str,
                   fecha_iso: str) -> Path:
    """Devuelve una ruta libre para el PDF, sin pisar jamás un archivo existente.

    Formato de §4::

        pdf\\AAAA\\EC-AAAA-NNNN_APELLIDO-Nombre_AAAA-MM-DD.pdf

    El año de la carpeta sale de la fecha de emisión, que es la misma que
    determina el año del código (§6.1). Si el archivo ya existe —reemisión
    manual, o dos récipes del mismo paciente el mismo día con el código
    reusado por una restauración— se agrega ``_v2``, ``_v3``… Un récipe
    emitido es un documento histórico: nunca se sobrescribe (§4, §5).
    """
    anio = fecha_iso[:4] if len(fecha_iso) >= 4 and fecha_iso[:4].isdigit() else "0000"
    carpeta = Path(dir_datos) / "pdf" / anio
    carpeta.mkdir(parents=True, exist_ok=True)

    base = f"{codigo}_{sanitizar_nombre_archivo(paciente_nombre)}_{fecha_iso[:10]}"
    candidata = carpeta / f"{base}.pdf"
    version = 1
    while candidata.exists():
        version += 1
        if version > 999:  # no debería pasar nunca; mejor eso que un bucle infinito
            raise RuntimeError(
                "Ya hay demasiadas versiones de este PDF en la carpeta. "
                "Movelas a otro lado y volvé a intentar."
            )
        candidata = carpeta / f"{base}_v{version}.pdf"
    return candidata


def _abrir_desactivado() -> bool:
    """¿Está apagado el "abrir cosas en el escritorio"?

    ``RECIPES_ABRIR_PDF=0`` apaga tanto el visor de PDF como el Explorador:
    lo usan los tests y el modo ``--solo-servidor``, donde no hay nadie
    mirando la pantalla y una ventana emergente por pedido sería un estorbo.
    """
    return os.environ.get("RECIPES_ABRIR_PDF", "1").strip() in ("0", "no", "false")


def abrir_con_el_sistema(ruta: Path | str) -> bool:
    """`os.startfile`: abre un archivo o una carpeta con lo que use Windows.

    Devuelve ``True`` si se pudo. Nunca levanta: que no se pueda abrir el
    visor no es motivo para fallar nada, el archivo ya está en disco.
    """
    if _abrir_desactivado():
        return False
    try:
        abrir = getattr(os, "startfile", None)  # solo existe en Windows
        if abrir is None:
            return False
        abrir(str(ruta))
        return True
    except OSError:
        return False


def abrir_en_visor(ruta: Path | str) -> bool:
    """Abre el PDF con el visor del sistema, listo para imprimir (§7-A).

    Que no se pueda **nunca** es motivo para fallar el guardado: el récipe ya
    está guardado y el PDF ya está en disco; como mucho el médico lo abre a
    mano desde Historial.
    """
    return abrir_con_el_sistema(ruta)


# --------------------------------------------------------------------------
# Registro Excel (§9)
# --------------------------------------------------------------------------

def marcar_excel_pendiente(con: sqlite3.Connection, pendiente: bool) -> None:
    """Deja anotado en `config` si el registro quedó desactualizado."""
    basedatos.guardar_config(con, CLAVE_EXCEL_PENDIENTE, "1" if pendiente else "0")


def hay_excel_pendiente(con: sqlite3.Connection) -> bool:
    return basedatos.obtener_config(con, CLAVE_EXCEL_PENDIENTE, "0") == "1"


def actualizar_registro_excel(con: sqlite3.Connection, dir_datos: Path) -> str | None:
    """Regenera el registro Excel completo desde SQLite (§9).

    Devuelve ``None`` si quedó al día, o el aviso para el médico si no se
    pudo. **Nunca levanta**: el récipe ya está guardado y el PDF ya está en
    disco, y que un Excel abierto impida emitir sería exactamente lo que §9
    prohíbe.

    Cuando no se puede escribir se anota ``excel_pendiente=1`` en `config`. Como
    el archivo se reconstruye entero cada vez —el Excel es salida, nunca fuente
    (§13)—, el reintento no necesita guardar nada más: el próximo guardado o
    la próxima anulación lo escriben completo y la marca se limpia sola.
    Mientras tanto, el Historial devuelve el aviso en cada búsqueda para que la
    pantalla lo pueda mostrar (§7-B).
    """
    try:
        excel.regenerar_registro(con, excel.ruta_registro(dir_datos))
    except excel.RegistroBloqueadoError as err:
        _anotar_pendiente(con)
        return str(err)
    except Exception:
        # Disco lleno, carpeta borrada, openpyxl con un carácter imposible…
        # Da igual la causa: el récipe está a salvo y el registro se rehace.
        _anotar_pendiente(con)
        return AVISO_EXCEL_GENERICO
    try:
        marcar_excel_pendiente(con, False)
    except sqlite3.Error:
        pass
    return None


def _anotar_pendiente(con: sqlite3.Connection) -> None:
    try:
        marcar_excel_pendiente(con, True)
    except sqlite3.Error:
        # Si ni la marca se puede guardar, el aviso igual se devuelve en esta
        # respuesta. Perder el recordatorio no justifica perder el récipe.
        pass


# --------------------------------------------------------------------------
# PIN (§10)
# --------------------------------------------------------------------------

def validar_pin(pin: Any) -> str:
    """Devuelve el PIN si son 4 a 6 dígitos, o explica qué escribir."""
    texto = basedatos.limpiar(pin).replace(" ", "")
    if not _RE_PIN.match(texto):
        raise ErrorEntrada(
            "El PIN son de 4 a 6 números, sin letras ni espacios. "
            "Para sacarlo, dejá el campo vacío."
        )
    return texto


def hashear_pin(pin: str, iteraciones: int = ITERACIONES_PIN,
                sal: bytes | None = None) -> str:
    """``pbkdf2$iteraciones$sal_hex$hash_hex``.

    PBKDF2-HMAC-SHA256 con sal nueva por PIN: dos médicos con el mismo 1234 no
    guardan el mismo texto, y el hash no se puede buscar en una tabla armada de
    antemano. Con 200.000 vueltas, probar los 10.000 PIN de cuatro dígitos
    contra el archivo lleva horas de CPU en vez de un parpadeo. Sigue sin ser
    seguridad fuerte —§10 no la pide— pero no regala nada.
    """
    sal = sal if sal is not None else secrets.token_bytes(BYTES_SAL_PIN)
    resumen = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), sal, iteraciones)
    return f"{ALGORITMO_PIN}${iteraciones}${sal.hex()}${resumen.hex()}"


def verificar_pin(guardado: str | None, pin: str) -> bool:
    """¿Coincide el PIN con lo guardado? Un formato ilegible responde ``False``."""
    if not guardado or not pin:
        return False
    partes = str(guardado).split("$")
    if len(partes) != 4 or partes[0] != ALGORITMO_PIN:
        return False
    _, iteraciones, sal_hex, hash_hex = partes
    try:
        resumen = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(sal_hex), int(iteraciones)
        )
    except (ValueError, TypeError):
        return False
    # compare_digest y no ==: la comparación no se corta en el primer byte
    # distinto y no le cuenta a nadie cuánto acertó.
    return hmac.compare_digest(resumen.hex(), hash_hex)


# --------------------------------------------------------------------------
# Logo (§7-C)
# --------------------------------------------------------------------------

def limpiar_fondo_logo(imagen: Any) -> Any:
    """Limpieza suave del fondo, igual que `build/preparar_recursos.py` §5.3.

    Dos pasos, sin tocar un solo píxel por debajo de 242 de luminancia (o sea:
    sin tocar el verde del símbolo ni las letras):

    1. luminancia >= 242 -> gris neutro de ese mismo valor. Mata el halo de
       color que deja la compresión JPEG alrededor de las letras.
    2. luminancia >= 252 -> blanco puro. El fondo queda #FFFFFF de verdad y no
       se ve un rectángulo apenas más gris sobre el papel.

    Se hace con `convert("L")` + `point` + `composite` de Pillow, que usan la
    misma luminancia Rec.601 del script pero **redondeada al entero** antes de
    comparar con el umbral. Contra `recursos/logo.png` la diferencia es de 2.910
    píxeles sobre 400.706 (0,7%), todos a medio punto de un umbral y todos del
    lado de limpiar un poco más: sobre el papel no se ve, y evita meter NumPy
    en el instalador para procesar una imagen cada tanto.
    """
    from PIL import Image

    gris = imagen.convert("L")
    neutro = Image.merge("RGB", (gris, gris, gris))
    casi_blanco = gris.point(lambda v: 255 if v >= UMBRAL_NEUTRALIZAR else 0, mode="1")
    limpia = Image.composite(neutro, imagen, casi_blanco)

    blanco = Image.new("RGB", imagen.size, (255, 255, 255))
    del_todo_blanco = gris.point(lambda v: 255 if v >= UMBRAL_BLANCO else 0, mode="1")
    return Image.composite(blanco, limpia, del_todo_blanco)


# --------------------------------------------------------------------------
# Validación de entrada
# --------------------------------------------------------------------------

def _texto(valor: Any, maximo: int = MAX_TEXTO_CORTO) -> str:
    """Recorta espacios y corta a `maximo` caracteres."""
    return basedatos.limpiar(valor)[:maximo]


def _texto_largo(valor: Any, maximo: int = MAX_TEXTO_LARGO) -> str:
    """Como `_texto`, pero conserva los saltos de línea que escribió el médico."""
    return basedatos.limpiar_multilinea(valor)[:maximo]


def _cuerpo() -> dict[str, Any]:
    """Lee el JSON del pedido y explica qué hacer si no vino."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ErrorEntrada(
            "No llegaron los datos del récipe. Volvé a intentar; si sigue "
            "pasando, cerrá y abrí la aplicación."
        )
    return datos


def _entero(valor: Any, campo: str, minimo: int, maximo: int) -> int | None:
    """Convierte a entero o explica en criollo qué se esperaba."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErrorEntrada(
            f"{campo} tiene que ser un número. Si no la sabés, dejala vacía."
        ) from None
    if not (minimo <= numero <= maximo):
        raise ErrorEntrada(f"{campo} tiene que estar entre {minimo} y {maximo}.")
    return numero


def validar_items(crudos: Any, exigir: bool = True) -> list[dict[str, str]]:
    """Limpia los renglones del récipe y exige al menos uno con medicamento (§7-A).

    Los renglones vacíos del formulario no son un error: se descartan. Lo que
    no se puede es *guardar* un récipe sin ningún medicamento.

    Con `exigir=False` se admite la lista vacía. Lo usa `/api/medir`, que es
    una consulta y no un guardado: la interfaz mide mientras el médico escribe
    y todavía no cargó ningún medicamento, y así puede avisarle temprano si el
    nombre del paciente no entra en el renglón (`nombre_estado`). Exigir un
    medicamento ahí devolvía un 400 en cada tecla del nombre.
    """
    if crudos is None:
        crudos = []
    if not isinstance(crudos, list):
        raise ErrorEntrada("La lista de medicamentos llegó mal. Volvé a intentar.")
    if len(crudos) > MAX_ITEMS:
        raise ErrorEntrada(
            f"Son demasiados renglones ({len(crudos)}). Emití el récipe en dos partes."
        )

    limpios: list[dict[str, str]] = []
    for crudo in crudos:
        if not isinstance(crudo, Mapping):
            continue
        renglon = {
            "medicamento": _texto(crudo.get("medicamento")),
            "presentacion": _texto(crudo.get("presentacion")),
            "cantidad": _texto(crudo.get("cantidad"), 60),
            "dosis": _texto(crudo.get("dosis"), MAX_TEXTO_LARGO),
            "indicaciones": _texto(crudo.get("indicaciones"), MAX_TEXTO_LARGO),
        }
        if renglon["medicamento"]:
            limpios.append(renglon)

    if not limpios and exigir:
        raise ErrorEntrada(
            "Agregá al menos un medicamento antes de guardar el récipe."
        )
    return limpios


def validar_paciente(crudo: Any) -> dict[str, Any]:
    """Valida el bloque `paciente`. El nombre es obligatorio; la cédula, no (§15.4)."""
    if not isinstance(crudo, Mapping):
        crudo = {}
    nombre = _texto(crudo.get("nombre"), 120)
    if not nombre:
        raise ErrorEntrada("Escribí el nombre del paciente antes de guardar.")
    return {
        "id": _entero(crudo.get("id"), "El paciente", 1, 2 ** 31),
        "nombre": nombre,
        "cedula": _texto(crudo.get("cedula"), 30),
        "fecha_nacimiento": _texto(crudo.get("fecha_nacimiento"), 30),
        "edad": _entero(crudo.get("edad"), "La edad", 0, 130),
        "sexo": _texto(crudo.get("sexo"), 20),
        "telefono": _texto(crudo.get("telefono"), 40),
    }


def _fecha_filtro(valor: Any, campo: str) -> str | None:
    """Valida una fecha del buscador (`AAAA-MM-DD`). Vacía = sin filtro."""
    texto = basedatos.limpiar(valor)
    if not texto:
        return None
    if not _RE_FECHA_SIMPLE.match(texto):
        raise ErrorEntrada(
            f"La fecha «{campo}» va en formato AAAA-MM-DD, por ejemplo 2026-08-14."
        )
    try:
        date.fromisoformat(texto)
    except ValueError:
        raise ErrorEntrada(
            f"La fecha «{campo}» no existe en el calendario. Revisá el día y el mes."
        ) from None
    return texto


def _json_recipe(fila: Any, medicamentos: Iterable[str] = ()) -> dict[str, Any]:
    """Un récipe con la forma que muestra el Historial (§7-B).

    `medicamentos` es el resumen separado por comas: alcanza para reconocer el
    récipe en la lista sin abrir el PDF. Sale del texto literal guardado en
    `recipe_items`, así que dice lo que se recetó ese día (§5).
    """
    return {
        "id": int(fila["id"]),
        "codigo": fila["codigo"],
        "fecha_emision": fila["fecha_emision"],
        "paciente_nombre": fila["paciente_nombre"] or "",
        "cedula": fila["paciente_cedula"] or "",
        "diagnostico": fila["diagnostico"] or "",
        "medicamentos": ", ".join(m for m in medicamentos if m),
        "anulado": bool(fila["anulado"]),
        "motivo_anulacion": fila["motivo_anulacion"] or "",
        "fecha_anulacion": fila["fecha_anulacion"] or "",
    }


def _datos_pdf(codigo: str, paciente_nombre: str, fecha: str,
               items: Iterable[Mapping[str, Any]],
               indicaciones_generales: str) -> dict[str, Any]:
    """Arma el dict plano que esperan `medir_contenido` y `generar_recipe`."""
    return {
        "codigo": codigo,
        "fecha_emision": fecha,
        "paciente_nombre": paciente_nombre,
        "items": list(items),
        "indicaciones_generales": indicaciones_generales,
    }


# --------------------------------------------------------------------------
# La aplicación
# --------------------------------------------------------------------------

def crear_app(dir_datos: str | os.PathLike[str],
              ruta_db: str | os.PathLike[str] | None = None,
              ruta_logo: str | None = None,
              dir_fuentes: str | None = None) -> Flask:
    """Arma la app Flask sobre una carpeta de datos concreta.

    `dir_datos` es ``%USERPROFILE%\\Documents\\Recipes`` en la máquina del
    médico, o lo que diga ``RECIPES_DIR`` (tests y §7-C). Todo lo que la app
    escribe cuelga de ahí: la base, los PDF, el registro y los respaldos.

    El logo se toma de ``<dir_datos>/recursos/logo.png`` si está —es el que el
    médico puede cambiar desde Configuración (§7-C)— y si no, del que viene
    empaquetado con el programa. Las fuentes salen siempre del paquete.
    """
    dir_datos = Path(dir_datos)
    ruta_db = Path(ruta_db) if ruta_db else dir_datos / "datos" / "recipes.db"

    if dir_fuentes is None:
        dir_fuentes = pdf_recipe.DIR_FUENTES_DEFECTO

    app = Flask(__name__, static_folder=None)
    app.config.update(
        DIR_DATOS=dir_datos,
        RUTA_DB=ruta_db,
        RUTA_LOGO_FORZADA=ruta_logo,
        DIR_FUENTES=dir_fuentes,
    )

    def logo() -> str:
        """Ruta del logo, resuelta en cada pedido.

        Gana el de la carpeta del médico —el que él puede reemplazar desde
        Configuración (§7-C)— y si no hay, el que viene empaquetado. Se
        resuelve al momento de usarlo y no al arrancar, así cambiar el logo
        no obliga a cerrar y abrir la aplicación.
        """
        forzado = app.config.get("RUTA_LOGO_FORZADA")
        if forzado:
            return str(forzado)
        del_medico = Path(app.config["DIR_DATOS"]) / "recursos" / "logo.png"
        return str(del_medico if del_medico.is_file()
                   else pdf_recipe.RUTA_LOGO_DEFECTO)
    app.json.ensure_ascii = False   # los acentos viajan tal cual, no como \uXXXX
    app.json.sort_keys = False

    # ---------------------------------------------------------------- base
    def con() -> sqlite3.Connection:
        """Conexión de este pedido.

        Una por pedido y no una global, porque Flask atiende en varios hilos
        y una conexión de sqlite3 no se comparte entre hilos.
        """
        if "con" not in g:
            g.con = basedatos.inicializar(app.config["RUTA_DB"])
        return g.con

    @app.teardown_appcontext
    def _cerrar_con(_exc: BaseException | None = None) -> None:
        conexion = g.pop("con", None)
        if conexion is not None:
            conexion.close()

    # -------------------------------------------------------------- errores
    @app.errorhandler(ErrorEntrada)
    def _error_entrada(err: ErrorEntrada):
        return jsonify({"error": str(err)}), err.estado

    @app.errorhandler(pdf_recipe.RecursoFaltanteError)
    def _error_recurso(err: pdf_recipe.RecursoFaltanteError):
        return jsonify({"error": (
            "Falta el logo del récipe. Volvé a cargarlo desde Configuración "
            f"y probá de nuevo. ({err})"
        )}), 500

    @app.errorhandler(pdf_recipe.ContenidoNoCabeError)
    def _error_no_cabe(err: pdf_recipe.ContenidoNoCabeError):
        return jsonify({"error": (
            f"El contenido no entra en la hoja ({err}). Sacá un medicamento o "
            "acortá las indicaciones, y emití el resto en un segundo récipe."
        )}), 400

    @app.errorhandler(pdf_recipe.NombreNoCabeError)
    def _error_nombre(err: pdf_recipe.NombreNoCabeError):
        return jsonify({"error": (
            f"El nombre del paciente no entra en el renglón ({err}). Escribilo "
            "más corto: por ejemplo, un nombre y un apellido."
        )}), 400

    @app.errorhandler(ValueError)
    def _error_valor(err: ValueError):
        return jsonify({"error": str(err)}), 400

    @app.errorhandler(sqlite3.Error)
    def _error_base(err: sqlite3.Error):
        return jsonify({"error": (
            "No se pudo escribir en la base de datos. Cerrá y abrí la "
            f"aplicación; si sigue igual, restaurá el último respaldo. ({err})"
        )}), 500

    @app.errorhandler(Exception)
    def _error_interno(err: Exception):
        """Red de contención: cualquier falla no prevista sale como JSON.

        Los errores HTTP normales (un 404 de un archivo estático que no está)
        se dejan pasar tal cual.
        """
        if isinstance(err, HTTPException):
            return err
        return jsonify({"error": (
            "Algo salió mal. Volvé a intentar; si sigue pasando, cerrá y abrí "
            f"la aplicación. ({type(err).__name__}: {err})"
        )}), 500

    # ------------------------------------------------------------ interfaz
    @app.get("/")
    def inicio():
        indice = DIR_WEB / "index.html"
        if not indice.is_file():
            return (
                "<h1>Falta la interfaz</h1><p>No está "
                f"<code>{indice}</code>. Reinstalá la aplicación.</p>",
                503,
                {"Content-Type": "text/html; charset=utf-8"},
            )
        return send_from_directory(DIR_WEB, "index.html", max_age=0)

    @app.get("/<path:archivo>")
    def estatico(archivo: str):
        """Sirve `app/web/` (estilos, JS, imágenes). Sin caché: es local."""
        return send_from_directory(DIR_WEB, archivo, max_age=0)

    # --------------------------------------------------------- sugerencias
    @app.get("/api/sugerencias/pacientes")
    def sugerencias_pacientes():
        filas = basedatos.buscar_pacientes(con(), request.args.get("q", ""))
        return jsonify({"resultados": [
            {
                "id": f["id"],
                "nombre": f["nombre"],
                "cedula": f["cedula"] or "",
                "edad": f["edad"],
                "fecha_nacimiento": f["fecha_nacimiento"] or "",
                "sexo": f["sexo"] or "",
                "telefono": f["telefono"] or "",
            }
            for f in filas
        ]})

    @app.get("/api/sugerencias/medicamentos")
    def sugerencias_medicamentos():
        conexion = con()
        filas = basedatos.buscar_medicamentos(conexion, request.args.get("q", ""))
        resultados = []
        for f in filas:
            # La dosis más usada DE ESE medicamento: se ofrece como sugerencia
            # visible y editable, la interfaz no la aplica sola (§2.5 y §8).
            sugerida = basedatos.dosis_mas_usada(conexion, f["id"])
            resultados.append({
                "id": f["id"],
                "nombre": f["nombre"],
                "presentacion": f["presentacion"] or "",
                "dosis_sugerida": sugerida["texto"] if sugerida is not None else None,
            })
        return jsonify({"resultados": resultados})

    @app.get("/api/sugerencias/dosis")
    def sugerencias_dosis():
        """Dosis de un medicamento. La dosis cuelga del medicamento (§5).

        Sin `medicamento_id` —o con uno que no es número— devuelve la lista
        vacía en vez de un error: mientras el médico escribe un medicamento
        nuevo todavía no hay id, y el autocompletado nunca debe frenarlo.
        """
        crudo = (request.args.get("medicamento_id") or "").strip()
        try:
            medicamento_id = int(crudo)
        except ValueError:
            return jsonify({"resultados": []})
        filas = basedatos.buscar_dosis(con(), medicamento_id, request.args.get("q", ""))
        return jsonify({"resultados": [{"texto": f["texto"]} for f in filas]})

    @app.get("/api/sugerencias/indicaciones")
    def sugerencias_indicaciones():
        filas = basedatos.buscar_indicaciones(con(), request.args.get("q", ""))
        return jsonify({"resultados": [{"texto": f["texto"]} for f in filas]})

    @app.get("/api/sugerencias/diagnosticos")
    def sugerencias_diagnosticos():
        filas = basedatos.buscar_diagnosticos(con(), request.args.get("q", ""))
        return jsonify({"resultados": [{"texto": f["texto"]} for f in filas]})

    # --------------------------------------------------------------- medir
    @app.post("/api/medir")
    def medir():
        """¿Entra el contenido en la hoja? Se responde ANTES de generar (§7-A).

        Es una consulta, no un guardado: acepta el formulario a medio llenar
        (incluso sin ningún medicamento todavía) para que la interfaz pueda
        medir mientras el médico escribe.
        """
        cuerpo = _cuerpo()
        datos = _datos_pdf(
            codigo=f"{_prefijo(con())}-{RELLENO_CODIGO}-{RELLENO_CODIGO}",
            paciente_nombre=_texto(cuerpo.get("paciente_nombre"), 120),
            fecha=codigos.normalizar_fecha(None),
            items=validar_items(cuerpo.get("items"), exigir=False),
            indicaciones_generales=_texto_largo(cuerpo.get("indicaciones_generales")),
        )
        return jsonify(pdf_recipe.medir_contenido(
            datos, ruta_logo=logo(),
            dir_fuentes=app.config["DIR_FUENTES"],
        ))

    # -------------------------------------------------------- vista previa
    @app.post("/api/vista-previa")
    def vista_previa():
        """PDF de muestra, con código de relleno y SIN asignar número (§6.2).

        Un formulario abandonado no quema un número: la previa no toca el
        contador ni la base. El PDF se arma en una carpeta temporal que se
        borra sola y se devuelve inline: en `pdf\\AAAA\\` no queda nada, así
        que las previas no ensucian el archivo del médico.
        """
        cuerpo = _cuerpo()
        paciente = validar_paciente(cuerpo.get("paciente"))
        items = validar_items(cuerpo.get("items"))
        fecha = _texto(cuerpo.get("fecha_emision"), 30) or None

        datos = _datos_pdf(
            codigo=f"{_prefijo(con())}-{RELLENO_CODIGO}-{RELLENO_CODIGO}",
            paciente_nombre=paciente["nombre"],
            fecha=codigos.normalizar_fecha(fecha),
            items=items,
            indicaciones_generales=_texto_largo(cuerpo.get("indicaciones_generales")),
        )
        with tempfile.TemporaryDirectory(prefix="recipe-previa-") as tmp:
            destino = os.path.join(tmp, "previa.pdf")
            pdf_recipe.generar_recipe(
                datos, destino, ruta_logo=logo(),
                dir_fuentes=app.config["DIR_FUENTES"],
            )
            with open(destino, "rb") as archivo:
                contenido = archivo.read()
        return send_file(
            io.BytesIO(contenido), mimetype="application/pdf",
            as_attachment=False, download_name="vista-previa.pdf",
        )

    # ------------------------------------------------------------- guardar
    @app.post("/api/recipes")
    def guardar_recipe():
        """El botón **Guardar e imprimir** de §7-A, entero.

        Orden de las cosas, y por qué:

        1. Se valida y se **mide** el contenido *antes* de tocar la base. Si
           no entra en la hoja, el médico se entera sin que se haya quemado
           ningún número (§6.2).
        2. Una sola transacción ``BEGIN IMMEDIATE``: alta o búsqueda del
           paciente + `crear_recipe`, que adentro asigna el código, copia los
           renglones literales y aprende los términos (§6.3, §8). Si algo
           falla, no queda ni el récipe ni el número.
        3. Recién con el código en la mano se genera el PDF, se guarda su ruta
           y se abre en el visor del sistema, listo para imprimir.
        """
        cuerpo = _cuerpo()
        paciente = validar_paciente(cuerpo.get("paciente"))
        items = validar_items(cuerpo.get("items"))
        diagnostico = _texto(cuerpo.get("diagnostico"))
        notas = _texto(cuerpo.get("notas"), MAX_TEXTO_LARGO)
        generales = _texto_largo(cuerpo.get("indicaciones_generales"))
        fecha_pedida = _texto(cuerpo.get("fecha_emision"), 30) or None

        conexion = con()

        # 1. Medir antes de escribir nada.
        medida = pdf_recipe.medir_contenido(
            _datos_pdf(f"{_prefijo(conexion)}-{RELLENO_CODIGO}-{RELLENO_CODIGO}",
                       paciente["nombre"], codigos.normalizar_fecha(fecha_pedida),
                       items, generales),
            ruta_logo=logo(), dir_fuentes=app.config["DIR_FUENTES"],
        )
        if not medida.get("entra"):
            raise ErrorEntrada(
                "El récipe no entra en la hoja. Sacá un medicamento o acortá "
                "las indicaciones, y emití el resto en un segundo récipe."
            )

        # 2. Todo el guardado en una sola transacción inmediata.
        with basedatos.transaccion(conexion, inmediata=True):
            if paciente["id"]:
                fila = basedatos.obtener_paciente(conexion, paciente["id"])
                if fila is None:
                    raise ErrorEntrada(
                        "El paciente que elegiste ya no está en la lista. "
                        "Volvé a buscarlo o escribí el nombre de nuevo."
                    )
                paciente_id = int(fila["id"])
                # Se guarda lo que llegó con valor: completa lo que estaba
                # vacío (el médico va cargando de a poco) y también aplica las
                # correcciones, porque la ficha del paciente llega en pantalla
                # y §7-A promete que se pueden corregir. Un campo que llega
                # vacío nunca borra lo que ya estaba: borrar es otra cosa y no
                # se hace de refilón al emitir un récipe.
                cambios = {
                    campo: paciente[campo]
                    for campo in ("cedula", "fecha_nacimiento", "edad", "sexo", "telefono")
                    if paciente[campo] not in (None, "")
                    and str(paciente[campo]) != str(fila[campo] or "")
                }
                if cambios:
                    basedatos.actualizar_paciente(conexion, paciente_id, **cambios)
            else:
                paciente_id = basedatos.obtener_o_crear_paciente(
                    conexion,
                    nombre=paciente["nombre"],
                    cedula=paciente["cedula"],
                    fecha_nacimiento=paciente["fecha_nacimiento"],
                    edad=paciente["edad"],
                    sexo=paciente["sexo"],
                    telefono=paciente["telefono"],
                )

            recipe = codigos.crear_recipe(
                conexion, paciente_id, items,
                fecha_emision=fecha_pedida,
                diagnostico=diagnostico or None,
                notas=notas or None,
                indicaciones_generales=generales or None,
            )

        # 3. Con el código asignado: PDF, ruta y visor.
        destino = ruta_pdf_nueva(app.config["DIR_DATOS"], recipe["codigo"],
                                 paciente["nombre"], recipe["fecha_emision"])
        try:
            pdf_recipe.generar_recipe(
                _datos_pdf(recipe["codigo"], paciente["nombre"],
                           recipe["fecha_emision"], items, generales),
                str(destino),
                ruta_logo=logo(),
                dir_fuentes=app.config["DIR_FUENTES"],
            )
        except Exception as err:  # el récipe YA está guardado: no se pierde
            return jsonify({"error": (
                f"El récipe {recipe['codigo']} quedó guardado, pero no se pudo "
                f"crear el PDF: {err}. Buscalo en Historial y reimprimilo."
            )}), 500

        basedatos.guardar_ruta_pdf(conexion, int(recipe["id"]), str(destino))

        # 4. El registro Excel. Nunca puede impedir emitir (§9): si estaba
        # abierto, se avisa y se reintenta en el próximo guardado.
        try:
            aviso = actualizar_registro_excel(conexion, app.config["DIR_DATOS"])
        except Exception:
            aviso = AVISO_EXCEL_GENERICO

        abrir_en_visor(destino)
        respuesta = {"codigo": recipe["codigo"], "ruta_pdf": str(destino)}
        if aviso:
            respuesta["aviso"] = aviso
        return jsonify(respuesta)

    # ===================================================================
    # B · Historial (§7-B)
    # ===================================================================

    @app.get("/api/recipes")
    def listar_recipes():
        """Buscador por código, paciente, medicamento y rango de fechas.

        Un solo campo `q` para las tres cosas, porque el médico no sabe (ni
        tiene por qué saber) si lo que recuerda es el código o el remedio.
        Busca por subcadena y sin acentos (§8), ordena por fecha descendente y
        corta en 200: lo que se busca es un récipe, no un listado.

        Si el registro Excel quedó pendiente porque estaba abierto, la
        respuesta trae `aviso` con el texto de §7 para que la pantalla lo
        muestre (§9).
        """
        conexion = con()
        filas = basedatos.buscar_recipes(
            conexion,
            request.args.get("q", ""),
            desde=_fecha_filtro(request.args.get("desde"), "desde"),
            hasta=_fecha_filtro(request.args.get("hasta"), "hasta"),
            limite=LIMITE_HISTORIAL,
        )
        por_recipe = basedatos.medicamentos_por_recipe(
            conexion, [int(f["id"]) for f in filas]
        )
        cuerpo: dict[str, Any] = {
            "resultados": [
                _json_recipe(f, por_recipe.get(int(f["id"]), [])) for f in filas
            ]
        }
        if hay_excel_pendiente(conexion):
            cuerpo["aviso"] = excel.MENSAJE_BLOQUEADO
        return jsonify(cuerpo)

    def _recipe_o_404(recipe_id: int):
        """Busca el récipe y, si no está, corta con un 404 que dice qué hacer."""
        fila = basedatos.obtener_recipe_completo(con(), recipe_id)
        if fila is None:
            raise _NoEncontrado(
                "Ese récipe ya no está en la lista. Volvé a buscarlo en Historial."
            )
        return fila

    def _pdf_o_404(fila) -> Path:
        """Ruta del PDF guardado, o un 404 con el nombre del archivo que falta."""
        ruta = basedatos.limpiar(fila["ruta_pdf"])
        if not ruta or not Path(ruta).is_file():
            raise _NoEncontrado(
                f"No encuentro el PDF del récipe {fila['codigo']}. Si moviste o "
                "borraste la carpeta de récipes, restaurá el último respaldo "
                f"desde Configuración. (Lo buscaba en: {ruta or 'ninguna ruta guardada'})"
            )
        return Path(ruta)

    @app.get("/api/recipes/<int:recipe_id>/pdf")
    def pdf_recipe_guardado(recipe_id: int):
        """Devuelve el MISMO archivo que se guardó, byte por byte (§7-B).

        No se regenera nada: un récipe emitido es un documento histórico y el
        PDF que ve el paciente tiene que ser el que salió ese día, aunque hoy
        el logo o el encabezado sean otros. Por eso se manda el archivo tal
        cual está en disco y no una composición nueva (§12: "reimprimir desde
        Historial entrega el PDF original, byte por byte").

        Se lee entero a memoria y se manda desde ahí en vez de pasarle la ruta
        a `send_file`. Son unos 230 KB, y así el servidor no le deja a Windows
        un archivo tomado: con el handle abierto, el médico no puede mover ni
        borrar sus propios PDF mientras la aplicación esté corriendo (probado:
        el `unlink` fallaba con "está siendo utilizado por otro proceso").
        """
        fila = _recipe_o_404(recipe_id)
        ruta = _pdf_o_404(fila)
        try:
            contenido = ruta.read_bytes()
        except OSError as err:
            raise _NoEncontrado(
                f"No se pudo leer el PDF del récipe {fila['codigo']}. Fijate que "
                f"la carpeta de récipes esté disponible y probá de nuevo. ({err})"
            ) from err
        return send_file(
            io.BytesIO(contenido), mimetype="application/pdf",
            as_attachment=False, download_name=ruta.name, max_age=0,
        )

    @app.post("/api/recipes/<int:recipe_id>/abrir")
    def abrir_recipe(recipe_id: int):
        """Reimprimir: abre el PDF guardado en el visor del sistema (§7-B)."""
        fila = _recipe_o_404(recipe_id)
        ruta = _pdf_o_404(fila)
        if not abrir_con_el_sistema(ruta) and not _abrir_desactivado():
            return jsonify({"error": (
                "No se pudo abrir el PDF con el visor de Windows. Abrilo a "
                f"mano desde: {ruta}"
            )}), 500
        return jsonify({"ok": True})

    @app.post("/api/recipes/<int:recipe_id>/anular")
    def anular_recipe(recipe_id: int):
        """Anula con motivo escrito. No borra nada, nunca (§2.4 y §10).

        El PDF queda en disco, el código queda quemado y el estado se refleja
        en el Excel. No hay des-anular: un récipe anulado es un hecho, y si el
        médico se arrepiente emite uno nuevo. Anular dos veces es un 400 y no
        pisa el motivo original.
        """
        cuerpo = _cuerpo()
        motivo = _texto(cuerpo.get("motivo"), MAX_TEXTO_LARGO)
        if not motivo:
            raise ErrorEntrada(
                "Escribí el motivo de la anulación antes de anular el récipe."
            )

        conexion = con()
        fila = _recipe_o_404(recipe_id)
        if fila["anulado"]:
            fecha = basedatos.limpiar(fila["fecha_anulacion"])[:10]
            raise ErrorEntrada(
                f"El récipe {fila['codigo']} ya estaba anulado"
                + (f" el {fecha}" if fecha else "")
                + f". Motivo: {fila['motivo_anulacion'] or 'sin motivo guardado'}."
            )

        with basedatos.transaccion(conexion, inmediata=True):
            basedatos.anular_recipe(conexion, recipe_id, motivo)

        # El Excel se rehace fuera de la transacción: escribir un archivo con
        # la base tomada dejaría bloqueado al resto de la app por nada.
        try:
            aviso = actualizar_registro_excel(conexion, app.config["DIR_DATOS"])
        except Exception:
            aviso = AVISO_EXCEL_GENERICO

        actualizada = basedatos.obtener_recipe_completo(conexion, recipe_id)
        medicamentos = basedatos.medicamentos_por_recipe(conexion, [recipe_id])
        respuesta = _json_recipe(actualizada, medicamentos.get(recipe_id, []))
        if aviso:
            respuesta["aviso"] = aviso
        return jsonify(respuesta)

    # ===================================================================
    # C · Configuración (§7-C, §10)
    # ===================================================================

    def _config_json(conexion: sqlite3.Connection) -> dict[str, Any]:
        """Lo que ve la pantalla de Configuración.

        `carpeta_datos` es de solo lectura: se muestra y se abre con el botón,
        pero no se cambia desde acá. Mover la carpeta implica mover la base,
        los PDF y los respaldos con la app corriendo; se hace con la variable
        `RECIPES_DIR` y la app cerrada, que es una operación de instalación y
        no un campo de formulario.
        """
        guardado = basedatos.obtener_config_todo(conexion)
        datos = {
            campo: (guardado.get(clave) or "")
            for campo, clave in CAMPOS_MEDICO.items()
        }
        datos.update({
            "prefijo": codigos.obtener_prefijo(conexion),
            "carpeta_datos": str(app.config["DIR_DATOS"]),
            "pin_activo": bool(guardado.get(CLAVE_PIN)),
            # Booleano, igual que `pin_activo`: la pantalla pregunta "¿ya lo
            # vio?", no le interesa con qué texto se guardó adentro.
            "tutorial_visto": basedatos.limpiar(guardado.get(CLAVE_TUTORIAL)) == "1",
            "version_app": VERSION_APP,
        })
        return datos

    @app.get("/api/config")
    def obtener_configuracion():
        return jsonify(_config_json(con()))

    @app.post("/api/config")
    def guardar_configuracion():
        """Guarda los datos del médico y el prefijo del código.

        Los datos del médico **no se imprimen** en el récipe: el modelo lleva
        sello y firma a mano (decisión del médico, §15.1 y §15.3). Se guardan
        igual porque son los datos de colegiatura del establecimiento y la
        Fase 5 los necesita para el README y para un eventual encabezado
        opcional; que estén acá no cambia el PDF.

        El prefijo se valida (§6.6) y vale para los récipes **futuros**: los ya
        emitidos guardan su código literal y no se tocan.
        """
        cuerpo = _cuerpo()
        valores: dict[str, str | None] = {}
        for campo, clave in CAMPOS_MEDICO.items():
            if campo in cuerpo:
                valores[clave] = _texto(cuerpo.get(campo), MAX_CAMPO_MEDICO) or None

        if "prefijo" in cuerpo:
            # validar_prefijo levanta ValueError con un mensaje en criollo,
            # que el manejador de errores devuelve como 400.
            valores[codigos.CLAVE_PREFIJO] = codigos.validar_prefijo(cuerpo.get("prefijo"))

        if "tutorial_visto" in cuerpo:
            # Lo manda el tutorial de primer uso al terminarlo o al saltarlo, en
            # un POST propio que no trae ningún otro campo: el bucle de arriba
            # solo escribe lo que vino, así que marcar la visita no pisa los
            # datos del médico ni el prefijo.
            crudo = cuerpo.get("tutorial_visto")
            visto = crudo is True or basedatos.limpiar(crudo) in ("1", "true", "si", "sí")
            valores[CLAVE_TUTORIAL] = "1" if visto else None

        conexion = con()
        if valores:
            basedatos.guardar_config_varios(conexion, valores)
        return jsonify(_config_json(conexion))

    @app.get("/api/config/logo")
    def ver_logo():
        """El logo que hoy se imprime, para mostrarlo en pantalla (§7-C).

        Lo usan la vista de Configuración («este es el logo que está saliendo»)
        y la pantalla del PIN. Devuelve exactamente el mismo archivo que usa el
        PDF —el de la carpeta del médico si lo cambió, y si no el empaquetado—,
        así que lo que se ve en pantalla es lo que se imprime.

        Se lee a memoria y se manda desde ahí, por lo mismo que el PDF del
        Historial: con la ruta, Windows deja el archivo tomado y el médico no
        podría reemplazar su propio logo con la aplicación abierta.

        404 sin logo: la interfaz muestra un texto en vez de un cuadro roto.
        """
        ruta = Path(logo())
        if not ruta.is_file():
            raise _NoEncontrado(
                "Todavía no hay logo cargado. Elegí una imagen PNG o JPG y "
                "pulsá «Guardar logo»."
            )
        try:
            contenido = ruta.read_bytes()
        except OSError as err:
            raise _NoEncontrado(
                "No se pudo leer el logo. Volvé a cargarlo desde Configuración. "
                f"({err})"
            ) from err
        tipo = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
        return send_file(
            io.BytesIO(contenido), mimetype=tipo,
            as_attachment=False, download_name=ruta.name, max_age=0,
        )

    @app.post("/api/config/logo")
    def cargar_logo():
        """Carga el logo del récipe: `multipart/form-data` con el campo `archivo`.

        Se acepta PNG o JPG y se guarda siempre como PNG limpio en
        ``<carpeta de datos>\\recursos\\logo.png``: RGB sin canal alfa, sin
        perfil ICC y sin metadatos, que es lo que fpdf2 embebe sin sorpresas de
        color. La limpieza de fondo es la misma de §5.3 del análisis del
        modelo.

        El archivo se escribe con nombre temporal y recién al final se renombra
        encima del bueno: si algo falla a mitad de camino, el logo anterior
        queda intacto y el médico puede seguir emitiendo.
        """
        subido = request.files.get("archivo")
        if subido is None or not subido.filename:
            raise ErrorEntrada(
                "Elegí el archivo del logo (PNG o JPG) antes de darle a cargar."
            )

        crudo = subido.read(MAX_BYTES_LOGO + 1)
        if len(crudo) > MAX_BYTES_LOGO:
            raise ErrorEntrada(
                "El archivo pesa más de 20 MB. Para un logo alcanza y sobra con "
                "una imagen de menos de 2 MB."
            )
        if not crudo:
            raise ErrorEntrada("El archivo llegó vacío. Volvé a elegirlo y probá de nuevo.")

        try:  # Pillow se importa acá: si faltara, lo único que no anda es esto
            from PIL import Image
        except ImportError:
            return jsonify({"error": (
                "No se puede procesar imágenes en esta instalación. Copiá el "
                "logo a mano en la carpeta recursos, con el nombre logo.png."
            )}), 500

        try:
            with Image.open(io.BytesIO(crudo)) as abierta:
                formato = (abierta.format or "").upper()
                if formato not in FORMATOS_LOGO:
                    raise ErrorEntrada(
                        "El logo tiene que ser un PNG o un JPG. Si tenés otro "
                        "formato, abrilo con Paint y guardalo como PNG."
                    )
                ancho, alto = abierta.size
                if ancho < ANCHO_MINIMO_LOGO:
                    raise ErrorEntrada(
                        f"El logo mide {ancho} píxeles de ancho: va a salir "
                        "pixelado al imprimir; buscá una imagen más grande (de "
                        f"{ANCHO_MINIMO_LOGO} píxeles de ancho para arriba)."
                    )
                # convert("RGB") aplana el alfa y descarta la paleta; construir
                # una imagen nueva desde los bytes deja `info` vacío, así que no
                # se arrastra el ICC ni el EXIF del original.
                plana = abierta.convert("RGB")
                limpia = limpiar_fondo_logo(plana)
                sin_metadatos = Image.frombytes("RGB", limpia.size, limpia.tobytes())
        except ErrorEntrada:
            raise
        except Exception as err:
            raise ErrorEntrada(
                "No pude leer esa imagen. Probá con otro archivo PNG o JPG. "
                f"({type(err).__name__})"
            ) from err

        destino = Path(app.config["DIR_DATOS"]) / "recursos" / "logo.png"
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_name(f"~logo-{os.getpid()}.tmp.png")
        try:
            sin_metadatos.save(temporal, format="PNG", optimize=True)
            os.replace(temporal, destino)
        except OSError as err:
            try:
                temporal.unlink()
            except OSError:
                pass
            return jsonify({"error": (
                "No se pudo guardar el logo en la carpeta de datos. Fijate que "
                f"la carpeta exista y no esté de solo lectura. ({err})"
            )}), 500
        return jsonify({"ok": True, "ancho": ancho, "alto": alto})

    @app.post("/api/config/pin")
    def guardar_pin():
        """Pone, cambia o saca el PIN de entrada (§10).

        `pin_nuevo` vacío desactiva el PIN. Si ya había uno, hace falta
        `pin_actual` y tiene que ser el correcto: si no, cualquiera que pase
        frente a la computadora desbloqueada podría sacar la barrera.
        """
        cuerpo = _cuerpo()
        conexion = con()
        actual = basedatos.obtener_config(conexion, CLAVE_PIN)

        if actual:
            candidato = basedatos.limpiar(cuerpo.get("pin_actual")).replace(" ", "")
            if not candidato:
                raise ErrorEntrada("Escribí el PIN que usás hoy para poder cambiarlo.")
            if not verificar_pin(actual, candidato):
                raise ErrorEntrada("Ese no es el PIN actual. Probá de nuevo.")

        crudo = basedatos.limpiar(cuerpo.get("pin_nuevo")).replace(" ", "")
        if not crudo:
            basedatos.guardar_config(conexion, CLAVE_PIN, None)
            return jsonify({"ok": True, "pin_activo": False})

        basedatos.guardar_config(conexion, CLAVE_PIN, hashear_pin(validar_pin(crudo)))
        return jsonify({"ok": True, "pin_activo": True})

    @app.post("/api/pin/verificar")
    def comprobar_pin():
        """¿Es este el PIN? Sin PIN configurado, siempre sí (§10).

        No hay bloqueo por intentos a propósito: dejar al médico afuera de sus
        propios récipes en medio de una consulta es peor que el riesgo que
        cubre. La demora fija es la que hace que probar a mano no valga la pena.
        """
        cuerpo = _cuerpo()
        guardado = basedatos.obtener_config(con(), CLAVE_PIN)
        time.sleep(DEMORA_VERIFICAR_PIN)
        if not guardado:
            return jsonify({"ok": True})
        candidato = basedatos.limpiar(cuerpo.get("pin")).replace(" ", "")
        return jsonify({"ok": verificar_pin(guardado, candidato)})

    @app.post("/api/respaldo")
    def respaldar():
        """Botón **Respaldar ahora** de Configuración (§10).

        Hace el ZIP del día y deja los últimos 8. Además anota la fecha como
        respaldo de la semana: si el médico acaba de respaldar a mano, el
        próximo arranque no tiene por qué hacer otro igual.

        El tamaño se lee **antes** de podar: lo que se informa es el ZIP que se
        acaba de escribir, y así la respuesta no depende de que ese archivo
        siga estando cuando termine `conservar_ultimos`.
        """
        conexion = con()
        dir_datos = app.config["DIR_DATOS"]
        try:
            archivo = respaldo.respaldar_ahora(dir_datos)
            tamano = archivo.stat().st_size
            respaldo.conservar_ultimos(dir_datos)
        except respaldo.RespaldoError as err:
            return jsonify({"error": str(err)}), 500
        except OSError as err:
            return jsonify({"error": (
                "No se pudo terminar el respaldo. Fijate que haya espacio en el "
                f"disco y volvé a intentar. ({err})"
            )}), 500
        try:
            basedatos.guardar_config(
                conexion, respaldo.CLAVE_ULTIMO_RESPALDO, date.today().isoformat()
            )
        except sqlite3.Error:
            pass  # el ZIP ya está: como mucho el lunes hace uno de más
        return jsonify({
            "archivo": archivo.name,
            "tamano_kb": round(tamano / 1024),
        })

    @app.post("/api/abrir-carpeta")
    def abrir_carpeta():
        """Abre la carpeta de datos en el Explorador (§7-C).

        Es la forma de que el médico llegue a sus PDF, al registro y a los
        respaldos sin tener que aprenderse la ruta.
        """
        destino = Path(app.config["DIR_DATOS"])
        destino.mkdir(parents=True, exist_ok=True)
        if not abrir_con_el_sistema(destino) and not _abrir_desactivado():
            return jsonify({"error": (
                f"No se pudo abrir la carpeta. Está en: {destino}"
            )}), 500
        return jsonify({"ok": True})

    return app


def _prefijo(conexion: sqlite3.Connection) -> str:
    """Prefijo configurado (``EC`` por defecto, §6.6). Se usa en los rellenos."""
    try:
        return codigos.obtener_prefijo(conexion)
    except Exception:
        return codigos.PREFIJO_POR_DEFECTO
