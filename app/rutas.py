# -*- coding: utf-8 -*-
"""Endpoints Flask de la app de récipes (§7-A de las instrucciones).

Todo es local: el servidor escucha en `127.0.0.1` con un puerto libre que
elige `main.py`, y la interfaz que lo consume vive en `app/web/`. **Ninguna
ruta sale a internet** (§2.1): no hay CDN, ni fuentes remotas, ni telemetría.

Contrato de la API (JSON UTF-8; los errores son
``{"error": "qué hacer"}`` con estado 4xx/5xx):

    Nuevo récipe (§7-A)
    GET  /api/sugerencias/pacientes?q=  -> {"resultados": [{id, nombre, codigo,
                                          cedula, edad, fecha_nacimiento, sexo,
                                          telefono}]}. Es **el buscador
                                          principal de pacientes** (dec. 18):
                                          lo usan el campo del récipe y la
                                          pantalla de la Historia, y trae de
                                          una todo lo que hace falta para
                                          abrir la historia y para arrancar un
                                          récipe o un informe con ese paciente
                                          puesto por omisión, sin un segundo
                                          pedido.
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

    Historia clínica e informes (dec. 9 a 14, 18)
    POST /api/pacientes                   {nombre, cedula, edad,
                                          fecha_nacimiento, sexo, telefono} ->
                                          {"paciente", "codigo", "ya_existia"}.
                                          Alta desde la Historia (dec. 18): le
                                          asigna el código y le crea la
                                          carpeta. Si ya estaba, devuelve ESE
                                          con ``ya_existia: true`` y 200 en vez
                                          de duplicarlo (201 si es nuevo).
    POST /api/informes                    {paciente_id, tipo, anexo_ids, ...} ->
                                          lo emite, lo guarda en la historia,
                                          vincula los anexos y abre el PDF
    GET  /api/pacientes/<id>/informes     -> {"informes": [...]} del paciente
    GET  /api/informes/<id>/pdf           -> el MISMO archivo guardado
    POST /api/informes/<id>/abrir         -> lo abre para reimprimir
    POST /api/informes/<id>/anular        {motivo} -> el informe actualizado
    GET  /api/pacientes/<id>/ultimo-recipe   -> {"fecha", "items": [...]} para
                                          "Traer del último récipe"
    GET  /api/pacientes/<id>/frase-inicial?motivo= -> {"frase"} editable
    GET  /api/pacientes/<id>/historia/pdf -> la historia imprimible, al vuelo

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

**Qué es `codigo` desde la 2.0** (dec. 1 y 2). La forma de las respuestas no
cambió —la interfaz sigue leyendo las mismas claves—, pero lo que viaja en ese
campo sí: es el código **del paciente** (`EC-0001`, correlativo de por vida,
sin año), no un número propio del récipe. Todos los récipes de un mismo
paciente traen el mismo `codigo`; lo que distingue a cada uno es su `id` y su
`fecha_emision`, que ya venían en el Historial, y por eso `/pdf`, `/abrir` y
`/anular` van siempre por `id`. Los récipes emitidos antes de la 2.0 conservan
su código viejo (`EC-2026-0001`) tal cual se imprimió: no se reescribe nada.

**Dónde caen los archivos desde la 2.0** (dec. 17). Cada paciente tiene su
carpeta, ``pacientes\\EC-NNNN_APELLIDO-Nombre\\``, con ``recipes\\``,
``informes\\`` y ``anexos\\`` adentro; se crea al asignarle el código y el
nombre queda congelado ahí (la llave es el código). Los récipes emitidos antes
del cambio siguen en ``pdf\\AAAA\\``: nada se mueve y ``/pdf`` y ``/abrir``
entregan el archivo que dice la `ruta_pdf` guardada, sin recalcular nada.

**Qué se guarda y qué se imprime.** Un récipe y un informe son *actos*: llevan
el código del paciente, quedan en la base con su texto final, dejan su PDF en
la carpeta del paciente y se pueden reimprimir y anular. La historia clínica
no: es la foto de lo que hay hoy, se arma al vuelo cada vez que se pide
(``/api/pacientes/<id>/historia/pdf``) y **no se le persiste ninguna ruta**.
Guardar un PDF por cada impresión solo llenaría la carpeta de copias viejas
indistinguibles entre sí.

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
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from flask import Flask, g, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

try:  # como paquete (``from app import rutas``)
    from . import (basedatos, codigos, excel, pdf_comun, pdf_historia,
                   pdf_informe, pdf_recipe, respaldo)
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import basedatos  # type: ignore[no-redef]
    import codigos  # type: ignore[no-redef]
    import excel  # type: ignore[no-redef]
    import pdf_comun  # type: ignore[no-redef]
    import pdf_historia  # type: ignore[no-redef]
    import pdf_informe  # type: ignore[no-redef]
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

#: Máximo del código adentro de un nombre de carpeta o archivo. `EC-0001` usa
#: 7; el tope está para que un prefijo configurado a lo bestia (§7-C admite
#: escribir cualquier cosa) no se coma la ruta entera de Windows.
MAX_CODIGO_ARCHIVO = 20

#: Válvula de seguridad contra cuerpos absurdos. **No es un tope de producto**:
#: §7 pide "sin tope fijo", y quien avisa de verdad es `medir_contenido`, que
#: rechaza mucho antes por espacio en la hoja.
MAX_ITEMS = 200

#: Recorte defensivo de los textos libres, para que un pegado accidental de
#: media enciclopedia no llegue a la base ni al medidor del PDF.
MAX_TEXTO_CORTO = 300
MAX_TEXTO_LARGO = 2000

#: Los campos en prosa del informe (el cuerpo, los antecedentes, el motivo, la
#: evolución) son más largos que una indicación de récipe: son párrafos, y el
#: PDF los pagina sin problema. 6.000 caracteres son unas cuatro carillas
#: escritas, muy por encima de cualquier informe real, y siguen frenando un
#: pegado accidental de media enciclopedia.
MAX_TEXTO_INFORME = 6000

#: Tope de anexos por informe (dec. 12). Cada uno es una página completa; más
#: de veinte imágenes no es un informe, es un álbum, y el PDF pesaría 3 MB.
MAX_ANEXOS_INFORME = 20

#: Qué campos nombra el aviso de «informe vacío», por tipo (dec. 10). El
#: formulario de la aseguradora no tiene ningún campo llamado «cuerpo», así que
#: mandar a escribirlo ahí era mandar a buscar algo que no está en la pantalla.
#: La pantalla avisa lo mismo antes de mandar el pedido, y hay un test que
#: compara los dos textos contra `app.js` para que no se separen.
VACIO_POR_TIPO = {
    "clinico": "el cuerpo o el diagnóstico",
    "aseguradora": "el motivo de la consulta o el diagnóstico",
}

#: Código de relleno de la vista previa (§6.2: un formulario abandonado no
#: quema un número, así que la previa no pide ninguno).
#:
#: El contrato lo escribe ``EC-␣␣␣␣`` con U+2423 (el símbolo de espacio
#: abierto). Lato no trae ese glifo —se verificó sobre `recursos/fuentes/`— y
#: saldría un hueco mudo en el PDF, así que se rellena con guiones bajos, que
#: sí están en la fuente y se leen igual de claro: "acá va a ir un número".
#:
#: Desde la 2.0 es **un solo** grupo de cuatro: el código del paciente no lleva
#: año (dec. 1), así que el relleno tiene que medir lo mismo que el código de
#: verdad. Solo lo ve el paciente nuevo, que todavía no tiene número.
RELLENO_CODIGO = "____"

#: Versión que se muestra en Configuración. Se sube a mano al empaquetar (§11).
VERSION_APP = "2.0.1"

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
    # COMEZU: el número del Colegio de Médicos del Estado Zulia. Va aparte de
    # `colegio` (que es el nombre del colegio, texto libre) porque el informe
    # lo imprime en su propia casilla, al lado del MPPS (dec. 9).
    "comezu": "medico_comezu",
    "colegio": "medico_colegio",
    "rif": "medico_rif",
    "direccion": "medico_direccion",
    "telefonos": "medico_telefonos",
    # Ciudad del pie del informe clínico ("Maracaibo; 18 de Agosto de 2026").
    "ciudad": "medico_ciudad",
}

#: Largo máximo de cada campo del médico. Son renglones de encabezado, no
#: párrafos; el recorte evita que un pegado accidental rompa el PDF.
MAX_CAMPO_MEDICO = 200

#: Lo que trae la aplicación escrito de fábrica (dec. 9). Se carga **solo si
#: el campo está vacío**: son un punto de partida para que el primer informe
#: salga bien sin pasar por Configuración, no un valor fijo. Todos se editan
#: en Configuración y, una vez editados, no se vuelven a pisar nunca.
#:
#: El R.I.F. no está acá a propósito: no se imprime en ningún lado del informe
#: (ya viene adentro de `recursos/firma.png`) y precargar un dato fiscal que
#: nadie ve es pedir que quede desactualizado sin que se note.
DEFAULTS_MEDICO: dict[str, str] = {
    "medico_nombre": "Dr. Eleazar Shiera Bastidas",
    "medico_comezu": "7414",
    "medico_mpps": "34846",
    "medico_ciudad": "Maracaibo",
}

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


class _YaEstaba(ErrorEntrada):
    """Lo que se quiso agregar ya estaba (misma imagen anexada dos veces). 409.

    No es un error del médico ni una falla: es un aviso de que la app ya tiene
    eso guardado. El texto le dice dónde quedó, para que no lo busque.
    """

    estado = 409


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


# --------------------------------------------------------------------------
# Carpeta por paciente (dec. 17)
# --------------------------------------------------------------------------

#: Raíz de las carpetas por paciente, adentro de la carpeta de datos (dec. 17).
DIR_PACIENTES = "pacientes"

#: Qué hay adentro de la carpeta de un paciente (dec. 17). `recipes\\` la usa
#: `ruta_pdf_nueva`; `informes\\` y `anexos\\` las van a usar la historia
#: clínica y la bandeja de WhatsApp (dec. 10 y 11). Se crean las tres juntas
#: para que el médico vea siempre la misma estructura al abrir la carpeta.
SUBCARPETAS_PACIENTE = ("recipes", "informes", "anexos")


def _carpeta_congelada(raiz: Path, prefijo: str) -> Path | None:
    """La carpeta ya existente de ese código, si la hay.

    El código es la llave (dec. 17): alcanza con que el nombre de la carpeta
    empiece con ``<codigo>_``, sin importar qué venga después. Si por lo que
    sea hubiera más de una, gana la primera en orden alfabético —determinista,
    la misma en cada corrida— en vez de inventar una tercera.
    """
    if not raiz.is_dir():
        return None
    candidatas = sorted(
        hija for hija in raiz.iterdir()
        if hija.is_dir() and hija.name.upper().startswith(prefijo.upper())
    )
    return candidatas[0] if candidatas else None


def carpeta_paciente(dir_datos: Path | str, codigo: str,
                     nombre: str | None) -> Path:
    """Carpeta propia del paciente, creada si no estaba (dec. 17)::

        pacientes\\EC-0001_APELLIDO-Nombre\\
            recipes\\
            informes\\
            anexos\\

    **El nombre se congela.** La llave es el código, no el nombre: si ya hay
    una carpeta que empieza con ``EC-0001_`` se usa esa aunque hoy el paciente
    se llame distinto. Corregir un apellido mal tipeado no puede partir en dos
    el historial de una persona ni dejar archivos huérfanos, y renombrar la
    carpeta rompería las rutas ya guardadas en la base. El nombre real vive en
    la base y adentro de cada PDF; el de la carpeta es apenas una ayuda para
    que el médico la reconozca de un vistazo en el Explorador.

    Se llama al asignarle el código al paciente —hoy, al guardar su primer
    récipe (§7-A)— y es idempotente: llamarla de nuevo devuelve la misma
    carpeta y no toca nada.
    """
    raiz = Path(dir_datos) / DIR_PACIENTES
    prefijo = f"{sanitizar_nombre_archivo(codigo, MAX_CODIGO_ARCHIVO)}_"
    destino = (_carpeta_congelada(raiz, prefijo)
               or raiz / f"{prefijo}{sanitizar_nombre_archivo(nombre)}")
    for sub in SUBCARPETAS_PACIENTE:
        (destino / sub).mkdir(parents=True, exist_ok=True)
    return destino


def ruta_pdf_nueva(dir_datos: Path, codigo: str, paciente_nombre: str,
                   fecha_iso: str) -> Path:
    """Devuelve una ruta libre para el PDF, sin pisar jamás un archivo existente.

    Desde la 2.0 el récipe nuevo nace adentro de la carpeta del paciente
    (dec. 17), con el nombre de archivo de §4 y el código **del paciente**
    (dec. 2)::

        pacientes\\EC-NNNN_APELLIDO-Nombre\\recipes\\EC-NNNN_APELLIDO-Nombre_AAAA-MM-DD.pdf

    Se terminó el reparto por año (``pdf\\AAAA\\``): todo lo de un paciente
    queda junto, que es lo que el médico busca cuando abre el Explorador. Los
    récipes emitidos antes del cambio **no se mueven**: la `ruta_pdf` guardada
    en la base es la verdad y reimprimir la lee de ahí, no la recalcula.

    El nombre del archivo lleva el nombre de HOY, no el congelado de la
    carpeta: cada PDF es un documento histórico y guarda el nombre con el que
    se emitió. La carpeta agrupa; el archivo testimonia.

    La colisión de nombres es **normal, no excepcional**: dos récipes del mismo
    paciente el mismo día comparten código y fecha, y por lo tanto nombre base.
    El segundo sale ``…_v2``, el tercero ``…_v3``. Un récipe emitido nunca se
    sobrescribe (§4, §5).
    """
    carpeta = carpeta_paciente(dir_datos, codigo, paciente_nombre) / "recipes"

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


def ruta_informe_nueva(dir_datos: Path, codigo: str, paciente_nombre: str,
                       fecha_iso: str) -> Path:
    """Ruta libre para el PDF de un informe, adentro de la carpeta del paciente::

        pacientes\\EC-NNNN_APELLIDO-Nombre\\informes\\INFORME_EC-NNNN_AAAA-MM-DD.pdf

    Mismo criterio que `ruta_pdf_nueva`: el segundo informe del mismo día sale
    ``…_v2`` y **nunca** se pisa uno emitido. El nombre no lleva el nombre del
    paciente —a diferencia del récipe— porque ya está el de la carpeta y el
    código: así el archivo no queda larguísimo con el prefijo `INFORME_`, que
    es lo que hace falta para distinguirlo de un vistazo entre los récipes.
    """
    carpeta = carpeta_paciente(dir_datos, codigo, paciente_nombre) / "informes"
    base = f"INFORME_{codigo}_{fecha_iso[:10]}"
    candidata = carpeta / f"{base}.pdf"
    version = 1
    while candidata.exists():
        version += 1
        if version > 999:  # no debería pasar nunca; mejor eso que un bucle infinito
            raise RuntimeError(
                "Ya hay demasiadas versiones de este informe en la carpeta. "
                "Movelas a otro lado y volvé a intentar."
            )
        candidata = carpeta / f"{base}_v{version}.pdf"
    return candidata


def precargar_datos_medico(conexion: sqlite3.Connection) -> None:
    """Escribe los `DEFAULTS_MEDICO` que todavía estén vacíos (dec. 9).

    Se hace acá y no en una migración porque `config` es una bolsa de
    clave/valor y una migración no puede saber si el médico borró un campo a
    propósito o si nunca lo llenó. Con esto, el primer informe sale con el
    nombre y la colegiatura puestos aunque nadie haya pasado por Configuración,
    y en cuanto el médico edita uno, ese queda como él lo dejó para siempre.
    """
    guardado = basedatos.obtener_config_todo(conexion)
    faltantes = {clave: valor for clave, valor in DEFAULTS_MEDICO.items()
                 if not basedatos.limpiar(guardado.get(clave))}
    if faltantes:
        basedatos.guardar_config_varios(conexion, faltantes)


def datos_medico(conexion: sqlite3.Connection) -> dict[str, str]:
    """Los datos del médico con los que se imprime un informe (dec. 9).

    Salen de `config` —editables en Configuración— con los de fábrica ya
    precargados. Las claves son las que espera `pdf_informe.generar_informe`.
    """
    precargar_datos_medico(conexion)
    guardado = basedatos.obtener_config_todo(conexion)

    def leer(clave: str) -> str:
        return basedatos.limpiar(guardado.get(clave)) or DEFAULTS_MEDICO.get(clave, "")

    return {
        "medico_nombre": leer("medico_nombre"),
        "medico_especialidad": leer("medico_especialidad"),
        "medico_comezu": leer("medico_comezu"),
        "medico_mpps": leer("medico_mpps"),
        "ciudad": leer("medico_ciudad"),
    }


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
# Bandeja de imágenes y anexos (dec. 11 y 13, Parte C §4 y §5)
# --------------------------------------------------------------------------

#: Carpeta que la app crea para que el médico suelte ahí lo que va juntando.
#: En el Escritorio queda el acceso directo «MEDICIONES — soltar aquí» (§4).
DIR_ENTRADA = "entrada"

#: Qué se ofrece en la bandeja. El PDF queda afuera a propósito: la bandeja se
#: elige mirando miniaturas y un PDF no se mira, se abre. Se adjunta con el
#: botón «Adjuntar imagen…», que sí lo acepta (dec. 11).
EXTENSIONES_BANDEJA = (".jpg", ".jpeg", ".png", ".webp")

#: Lo que además se acepta al adjuntar a mano (dec. 11: laboratorios en PDF).
EXTENSIONES_ANEXO = EXTENSIONES_BANDEJA + (".pdf",)

#: Ventana de la bandeja (Parte C §4). Lo de hace más de un mes ya no es "lo
#: que me acaban de mandar": si hace falta, está el botón de adjuntar.
DIAS_BANDEJA = 30

#: Cuántas miniaturas se muestran. Más de dos docenas no se miran, se barren.
MAX_BANDEJA = 24

#: Tope de archivos que se llegan a mirar por escaneo. La carpeta Descargas del
#: médico tenía 55 archivos, pero una carpeta con diez mil no puede hacer que la
#: pantalla de la historia tarde diez segundos en abrir.
MAX_CANDIDATOS_BANDEJA = 600

#: Miniatura de ~400 px de lado largo (Parte C §5), calidad 80.
LADO_MINIATURA = 400
CALIDAD_MINIATURA = 80

#: La miniatura del anexo vive al lado del original, con este sufijo.
SUFIJO_MINIATURA = ".thumb.jpg"

#: Tope del archivo que se adjunta a mano. La imagen de WhatsApp pesa 129 KB y
#: un PDF de laboratorio unos pocos MB; 30 MB es holgado y frena que un arrastre
#: equivocado (un video) se cargue entero en memoria.
MAX_BYTES_ANEXO = 30 * 1024 * 1024

#: Tipos de anexo del desplegable (Parte C §4, paso 6).
TIPOS_ANEXO = ("medicion", "laboratorio", "imagen", "otro")

#: Cómo se lee cada tipo cuando hay que explicárselo al médico.
NOMBRES_TIPO_ANEXO = {
    "medicion": "Medición de composición corporal",
    "laboratorio": "Laboratorio",
    "imagen": "Estudio de imagen",
    "otro": "Otro",
}

#: Las cinco series del gráfico de evolución (dec. 13).
SERIES_EVOLUCION = ("peso", "imc", "grasa_pct", "musculo_kg", "grasa_visceral")

#: De las cinco, las dos que además salen de los signos vitales de la consulta.
SERIES_DE_CONSULTA = ("peso", "imc")

#: Tipo MIME por extensión, para servir el anexo sin adivinar.
MIME_ANEXO = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".pdf": "application/pdf",
}


#: Cuántos antecedentes entran en la frase inicial y con cuántos caracteres.
#: Es una frase, no la historia: si el paciente tiene ocho crónicos, los tres
#: primeros dan el contexto y el resto va en el cuerpo del informe, donde el
#: médico los escribe con el detalle que hagan falta.
MAX_ANTECEDENTES_FRASE = 3
MAX_LARGO_ANTECEDENTES = 240


def resumir_antecedentes(texto: Any) -> str:
    """Convierte el recuadro de crónico-degenerativos en una enumeración.

    En la ficha, los antecedentes se escriben como el médico quiera: uno por
    renglón, separados por punto y coma, o todo seguido. La frase inicial los
    necesita en línea y en minúscula, para que quede la fórmula de la
    plantilla B: "…con antecedentes de dislipidemia y trastornos del sueño".

    Las siglas se respetan: "HTA" no se convierte en "hTA" ni en "hta". Solo se
    baja la primera letra cuando la palabra está escrita como una palabra
    normal, que es cuando la mayúscula era del principio del renglón.
    """
    crudo = basedatos.limpiar_multilinea(texto)
    if not crudo:
        return ""
    partes: list[str] = []
    for renglon in crudo.replace(";", "\n").splitlines():
        item = renglon.strip().strip(".,").strip()
        if not item:
            continue
        primera = item.split(" ", 1)[0]
        if primera[:1].isupper() and not primera.isupper():
            item = item[:1].lower() + item[1:]
        partes.append(item)
        if len(partes) == MAX_ANTECEDENTES_FRASE:
            break
    if not partes:
        return ""
    if len(partes) == 1:
        resumen = partes[0]
    else:
        resumen = ", ".join(partes[:-1]) + " y " + partes[-1]
    return resumen[:MAX_LARGO_ANTECEDENTES].strip()


def series_evolucion(conexion: sqlite3.Connection,
                     paciente_id: int) -> dict[str, list[dict[str, Any]]]:
    """Las cinco series del paciente, combinando sus dos fuentes (dec. 13).

    Los valores clave que el médico tipeó al anexar la medición (tabla
    `mediciones`) y el peso y el IMC que quedaron en los signos vitales de cada
    consulta. Cada punto viaja **rotulado con su fuente**, porque no son lo
    mismo: una es la báscula de bioimpedancia del paciente y la otra la balanza
    del consultorio, y ver por qué dos puntos del mismo día no coinciden tiene
    que ser posible sin abrir la base.

    Está acá afuera —y no adentro del endpoint— porque la usan los dos lugares
    donde el médico ve la tendencia: la pantalla, por `/evolucion`, y el PDF de
    la historia, que la dibuja en mini-gráficos (dec. 13 ampliada). Si esto
    viviera en un solo endpoint, el papel y la pantalla podrían decir cosas
    distintas del mismo paciente.
    """
    series: dict[str, list[dict[str, Any]]] = {
        nombre: [] for nombre in SERIES_EVOLUCION}

    for fila in basedatos.listar_mediciones(conexion, paciente_id):
        for nombre in SERIES_EVOLUCION:
            valor = fila[nombre]
            if valor is None:
                continue
            series[nombre].append({
                "fecha": str(fila["fecha"])[:10],
                "valor": float(valor),
                "fuente": "medicion",
                "anexo_id": fila["anexo_id"],
            })

    for fila in basedatos.historico_signos_vitales(conexion, paciente_id):
        for nombre in SERIES_DE_CONSULTA:
            valor = fila[nombre]
            if valor is None:
                continue
            series[nombre].append({
                "fecha": str(fila["fecha"])[:10],
                "valor": float(valor),
                "fuente": "consulta",
                "consulta_id": int(fila["consulta_id"]),
            })

    for puntos in series.values():
        puntos.sort(key=lambda punto: punto["fecha"])
    return series


def carpetas_bandeja(dir_datos: Path | str) -> list[tuple[str, Path]]:
    """Dónde mira la bandeja, con la etiqueta que ve el médico (Parte C §4).

    Son las tres del análisis —Descargas, Escritorio y la carpeta ``entrada``
    de la app— con las variantes de OneDrive, que en esta máquina se lleva el
    Escritorio de verdad: ``%USERPROFILE%\\OneDrive\\Escritorio`` existe y
    ``%USERPROFILE%\\Desktop`` puede ser un espejo o no existir.

    Se devuelven **resueltas y sin repetir**: si el Escritorio es un enlace al
    de OneDrive, la misma imagen no aparece dos veces en la bandeja. Esta lista
    es además la única frontera de lectura: fuera de acá no se sirve un archivo
    ni aunque alguien acierte un token.
    """
    perfil = Path(os.environ.get("USERPROFILE") or Path.home())
    raices: list[Path] = [perfil]
    desde_onedrive = (os.environ.get("ONEDRIVE") or "").strip()
    if desde_onedrive:
        raices.append(Path(desde_onedrive))
    raices.append(perfil / "OneDrive")

    carpetas: list[tuple[str, Path]] = []
    vistas: set[str] = set()

    def sumar(etiqueta: str, ruta: Path) -> None:
        try:
            resuelta = ruta.resolve()
        except OSError:
            return
        clave = str(resuelta).lower()
        if clave in vistas:
            return
        vistas.add(clave)
        if resuelta.is_dir():
            carpetas.append((etiqueta, resuelta))

    sumar("Entrada", Path(dir_datos) / DIR_ENTRADA)
    for raiz in raices:
        for nombre in ("Downloads", "Descargas"):
            sumar("Descargas", raiz / nombre)
        for nombre in ("Desktop", "Escritorio"):
            sumar("Escritorio", raiz / nombre)
    return carpetas


def candidatos_bandeja(dir_datos: Path | str,
                       dias: int = DIAS_BANDEJA) -> list[tuple[str, Path]]:
    """Las imágenes recientes de las carpetas permitidas, la más nueva primero.

    Solo se mira el nivel de arriba de cada carpeta —nada de recorrer
    ``Descargas`` entera con sus subcarpetas— y solo la fecha del archivo, que
    es barata. El hash, que es lo caro, lo hace quien llama y solo hasta juntar
    las que va a mostrar.
    """
    corte = time.time() - dias * 86400
    encontrados: list[tuple[float, str, Path]] = []
    for etiqueta, carpeta in carpetas_bandeja(dir_datos):
        try:
            hijos = list(carpeta.iterdir())
        except OSError:
            continue  # carpeta sin permiso o desconectada: no es un error
        for hijo in hijos:
            if hijo.suffix.lower() not in EXTENSIONES_BANDEJA:
                continue
            if hijo.name.lower().endswith(SUFIJO_MINIATURA):
                continue
            try:
                if not hijo.is_file():
                    continue
                cuando = hijo.stat().st_mtime
            except OSError:
                continue
            if cuando < corte:
                continue
            encontrados.append((cuando, etiqueta, hijo))
    encontrados.sort(key=lambda t: t[0], reverse=True)
    return [(etiqueta, ruta) for _, etiqueta, ruta in
            encontrados[:MAX_CANDIDATOS_BANDEJA]]


def ruta_de_bandeja_valida(dir_datos: Path | str, ruta: Path) -> bool:
    """¿Ese archivo está adentro de una carpeta permitida y sigue estando?

    Se comprueba **al usar el token**, no solo al escanear: entre el escaneo y
    el clic el archivo se pudo borrar, y el token no puede ser una llave a
    cualquier lugar del disco.
    """
    try:
        resuelta = Path(ruta).resolve()
    except OSError:
        return False
    if resuelta.suffix.lower() not in EXTENSIONES_BANDEJA or not resuelta.is_file():
        return False
    for _, carpeta in carpetas_bandeja(dir_datos):
        try:
            resuelta.relative_to(carpeta)
        except ValueError:
            continue
        return True
    return False


def sha256_de(ruta: Path | str) -> str:
    """SHA-256 del archivo, leído de a un mega.

    Es la identidad del anexo: deduplica (dec. 11), marca lo que la bandeja ya
    no tiene que ofrecer y verifica que la copia salió byte por byte.
    """
    resumen = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def dimensiones_imagen(ruta: Path | str) -> tuple[int, int] | None:
    """``(ancho, alto)`` ya girados según el EXIF, o ``None`` si no es imagen.

    Pillow lee solo el encabezado, así que esto no carga los píxeles: 24
    archivos por escaneo salen en milisegundos.
    """
    try:
        from PIL import Image

        with Image.open(ruta) as abierta:
            ancho, alto = abierta.size
            try:
                orientacion = int(abierta.getexif().get(274, 1))  # 274 = Orientation
            except Exception:
                orientacion = 1
    except Exception:
        return None
    if orientacion in (5, 6, 7, 8):  # la foto está de costado
        ancho, alto = alto, ancho
    return ancho, alto


def miniatura_jpeg(ruta: Path | str, lado: int = LADO_MINIATURA) -> bytes:
    """Miniatura JPEG de ~`lado` px, con la orientación EXIF ya aplicada.

    RGB y calidad 80: es para mirar en pantalla y elegir, no para archivar. El
    original **no se toca nunca** (Parte C §3: si hoy lo recomprimimos, la
    puerta de extraer datos mañana queda cerrada para siempre).
    """
    from PIL import Image, ImageOps

    with Image.open(ruta) as abierta:
        derecha = ImageOps.exif_transpose(abierta) or abierta
        plana = derecha.convert("RGB")
        plana.thumbnail((lado, lado), Image.LANCZOS)
        deposito = io.BytesIO()
        plana.save(deposito, format="JPEG", quality=CALIDAD_MINIATURA, optimize=True)
    return deposito.getvalue()


class BandejaEnMemoria:
    """El mapa ``token -> archivo`` de la bandeja. En memoria y por proceso.

    La interfaz **nunca** manda una ruta: manda el token que le dio el último
    escaneo. El token es aleatorio (`secrets.token_urlsafe`), no dice nada de
    dónde está el archivo, no se puede adivinar y muere al cerrar la
    aplicación. Aceptar rutas del cliente sería dejar que cualquier pedido
    leyera cualquier archivo del disco del médico.

    El mismo archivo conserva su token entre escaneos, así que actualizar la
    bandeja veinte veces no hace crecer el mapa. Igual hay tope: pasado
    `MAXIMO`, se vacía y los tokens viejos dejan de valer (la pantalla los
    renueva con el próximo escaneo).
    """

    MAXIMO = 4000
    MAX_MINIATURAS = 48
    MAX_HASHES = 2000

    def __init__(self) -> None:
        self._por_token: dict[str, tuple[Path, str]] = {}
        self._por_ruta: dict[str, str] = {}
        self._miniaturas: dict[str, tuple[float, bytes]] = {}
        self._hashes: dict[str, tuple[float, int, str]] = {}
        self._candado = threading.Lock()

    def hash_de(self, ruta: Path) -> str:
        """SHA-256 del archivo, recordado mientras no cambie.

        El escaneo tiene que hashear todo lo que mira para saber qué ya está
        anexado, y la pantalla de la historia pide la bandeja cada vez que se
        abre. Sin esto, una carpeta Descargas grande se releería entera en cada
        pedido. La huella es fecha + tamaño: si el archivo cambia, se rehace.

        **Solo para decidir qué mostrar.** Al anexar se vuelve a calcular sobre
        el archivo, porque de ese hash depende que la copia sea verificable.
        """
        clave = str(ruta).lower()
        info = ruta.stat()
        huella = (info.st_mtime, info.st_size)
        with self._candado:
            guardado = self._hashes.get(clave)
        if guardado is not None and guardado[:2] == huella:
            return guardado[2]
        resumen = sha256_de(ruta)
        with self._candado:
            if len(self._hashes) >= self.MAX_HASHES:
                self._hashes.clear()
            self._hashes[clave] = (huella[0], huella[1], resumen)
        return resumen

    def registrar(self, ruta: Path, carpeta: str) -> str:
        clave = str(ruta).lower()
        with self._candado:
            if len(self._por_token) >= self.MAXIMO:
                self._por_token.clear()
                self._por_ruta.clear()
                self._miniaturas.clear()
            token = self._por_ruta.get(clave)
            if token is None:
                token = secrets.token_urlsafe(16)
                self._por_ruta[clave] = token
            self._por_token[token] = (ruta, carpeta)
            return token

    def resolver(self, token: str | None) -> tuple[Path, str] | None:
        if not token:
            return None
        with self._candado:
            return self._por_token.get(token)

    def miniatura(self, token: str, ruta: Path) -> bytes:
        """Miniatura del archivo de la bandeja, cacheada mientras no cambie."""
        try:
            sello = ruta.stat().st_mtime
        except OSError:
            sello = 0.0
        with self._candado:
            guardada = self._miniaturas.get(token)
        if guardada is not None and guardada[0] == sello:
            return guardada[1]
        contenido = miniatura_jpeg(ruta)
        with self._candado:
            if len(self._miniaturas) >= self.MAX_MINIATURAS:
                self._miniaturas.clear()
            self._miniaturas[token] = (sello, contenido)
        return contenido


def nombre_anexo_libre(carpeta: Path, fecha: str, tipo: str,
                       extension: str) -> Path:
    """``<fecha-de-la-medición>_<tipo>_<nn>.<ext>``, sin pisar nada (Parte C §5).

    La fecha es la que confirmó el médico, **no** la del archivo: en el ejemplo
    real había cuatro días de diferencia. El ``nn`` correlativo resuelve dos
    mediciones el mismo día.
    """
    base = f"{fecha[:10]}_{sanitizar_nombre_archivo(tipo, 30)}"
    for numero in range(1, 1000):
        candidata = carpeta / f"{base}_{numero:02d}{extension}"
        if not candidata.exists():
            return candidata
    raise RuntimeError(
        "Ya hay demasiados anexos de ese día en la carpeta del paciente. "
        "Movelos a otro lado y volvé a intentar."
    )


def copiar_anexo(origen: Path, destino: Path, sha_esperado: str) -> None:
    """Copia el original y comprueba que llegó **igual**.

    `shutil.copy2` conserva las fechas del archivo; el SHA-256 de la copia se
    vuelve a calcular y se compara. Si no coincide (disco lleno, red que se
    cortó, antivirus que metió la mano), se borra la copia a medias y se
    levanta: el original sigue intacto en Descargas y el médico no perdió nada,
    que es toda la razón por la que se copia en vez de mover.
    """
    shutil.copy2(origen, destino)
    if sha256_de(destino) != sha_esperado:
        try:
            destino.unlink()
        except OSError:
            pass
        raise OSError(
            "La copia del archivo no salió igual que el original. Fijate que "
            "haya espacio en el disco y volvé a adjuntarla."
        )


def escribir_miniatura(destino: Path) -> Path | None:
    """Deja la miniatura al lado del anexo. Devuelve su ruta, o ``None``.

    Que no se pueda generar (un PDF, una imagen rota, Pillow ausente) **no**
    frena el anexo: el original ya está copiado, que es lo que importa; la
    pantalla se las arregla mostrando el archivo completo.
    """
    if destino.suffix.lower() not in EXTENSIONES_BANDEJA:
        return None
    ruta = destino.with_name(destino.stem + SUFIJO_MINIATURA)
    try:
        ruta.write_bytes(miniatura_jpeg(destino))
    except Exception:
        return None
    return ruta


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


def _real(valor: Any, campo: str, minimo: float, maximo: float) -> float | None:
    """Como `_entero` pero con decimales. La coma decimal también vale.

    El médico escribe «36,5» tanto como «36.5»: rechazarle la coma en un
    teclado en español sería pelearle a la costumbre por nada.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    try:
        numero = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ErrorEntrada(
            f"{campo} tiene que ser un número. Si no lo sabés, dejalo vacío."
        ) from None
    if numero != numero or numero in (float("inf"), float("-inf")):  # NaN o ±inf
        raise ErrorEntrada(f"{campo} tiene que ser un número normal.")
    if not (minimo <= numero <= maximo):
        raise ErrorEntrada(f"{campo} tiene que estar entre {minimo} y {maximo}.")
    return numero


#: Los siete numeradores de `Alimentación` (Parte A §2.4), con su etiqueta y el
#: denominador que el formulario trae impreso. El denominador **no** limita lo
#: que se puede escribir: quien toma tres litros de agua sobre un impreso que
#: dice «/2» escribe 3, y rechazárselo sería corregirle la realidad al médico.
ALIMENTACION_HISTORIA: dict[str, tuple[str, int]] = {
    "alim_comidas_dia": ("Comidas al día", 3),
    "alim_frutas_verduras": ("Frutas y verduras", 7),
    "alim_pollo": ("Pollo", 7),
    "alim_pescado": ("Pescado", 7),
    "alim_carnes_rojas": ("Carnes rojas", 7),
    "alim_carbohidratos": ("Carbohidratos y lípidos", 7),
    "alim_litros_agua": ("Litros de agua al día", 2),
}

#: Lo que queda de la ficha de identificación del papel (dec. 4 y 6): renglones
#: cortos, no párrafos.
FICHA_HISTORIA = ("estado_civil", "ocupacion", "tipo_sangre")


def validar_historia(crudo: Any) -> dict[str, Any]:
    """Limpia los campos de la ficha y los antecedentes que hayan llegado.

    **Solo lo que vino**: la pantalla edita de a una sección plegable y lo que
    el médico no tocó no se pisa (por eso `guardar_historia` actualiza campo a
    campo). Un campo desconocido se ignora en silencio en vez de romper: la
    interfaz puede mandar de más sin quedar acoplada a esta lista.
    """
    if not isinstance(crudo, Mapping):
        raise ErrorEntrada(
            "No llegaron los datos de la historia. Volvé a intentar; si sigue "
            "pasando, cerrá y abrí la aplicación."
        )
    campos: dict[str, Any] = {}
    for nombre in basedatos.CAMPOS_HISTORIA:
        if nombre not in crudo:
            continue
        if nombre in ALIMENTACION_HISTORIA:
            etiqueta, _ = ALIMENTACION_HISTORIA[nombre]
            campos[nombre] = _entero(crudo.get(nombre), etiqueta, 0, 99)
        elif nombre in FICHA_HISTORIA:
            campos[nombre] = _texto(crudo.get(nombre), 120)
        else:
            campos[nombre] = _texto_largo(crudo.get(nombre), MAX_TEXTO_INFORME)
    return campos


def validar_signos(crudo: Any) -> dict[str, Any]:
    """La tabla de signos vitales del papel (Parte A §2.7), con topes de cordura.

    Los rangos son anchos a propósito: están para atajar el dedo pesado (una
    temperatura de 365, un peso de 7000) y no para discutirle al médico un
    valor extremo que de verdad midió. Todo es opcional; lo que no se midió
    queda vacío, nunca en cero.
    """
    if crudo is None:
        crudo = {}
    if not isinstance(crudo, Mapping):
        raise ErrorEntrada(
            "Los signos vitales llegaron mal. Volvé a cargarlos y guardá otra vez."
        )
    return {
        "ta_sistolica": _entero(crudo.get("ta_sistolica"), "La tensión sistólica", 40, 300),
        "ta_diastolica": _entero(crudo.get("ta_diastolica"), "La tensión diastólica", 20, 200),
        "fc": _entero(crudo.get("fc"), "La frecuencia cardíaca", 20, 300),
        "fr": _entero(crudo.get("fr"), "La frecuencia respiratoria", 4, 90),
        "temperatura": _real(crudo.get("temperatura"), "La temperatura", 25, 45),
        "tam": _real(crudo.get("tam"), "La TAM", 20, 250),
        "dxtx": _entero(crudo.get("dxtx"), "La glucemia capilar", 10, 900),
        "tfg": _real(crudo.get("tfg"), "La TFG", 1, 300),
        "spo2": _entero(crudo.get("spo2"), "La saturación de oxígeno", 30, 100),
        "peso": _real(crudo.get("peso"), "El peso", 0.5, 500),
        # En metros o en centímetros: `calcular_imc` entiende las dos.
        "talla": _real(crudo.get("talla"), "La talla", 0.3, 250),
        "imc": _real(crudo.get("imc"), "El IMC", 5, 120),
    }


def validar_medicion(crudo: Any) -> dict[str, Any]:
    """Los cinco valores clave del informe de la báscula (dec. 13).

    Siempre opcionales: son un ofrecimiento al anexar la imagen, nunca un
    requisito. Se devuelven **solo los que tienen valor**, así una medición sin
    nada no crea una fila vacía.
    """
    if crudo is None:
        crudo = {}
    if not isinstance(crudo, Mapping):
        raise ErrorEntrada(
            "Los valores de la medición llegaron mal. Revisalos y guardá otra vez."
        )
    valores = {
        "peso": _real(crudo.get("peso"), "El peso", 0.5, 500),
        "imc": _real(crudo.get("imc"), "El IMC", 5, 120),
        "grasa_pct": _real(crudo.get("grasa_pct"), "El porcentaje de grasa", 0, 90),
        "musculo_kg": _real(crudo.get("musculo_kg"), "La masa muscular", 0.5, 200),
        "grasa_visceral": _real(crudo.get("grasa_visceral"), "La grasa visceral", 0, 100),
    }
    return {campo: valor for campo, valor in valores.items() if valor is not None}


def validar_tipo_anexo(crudo: Any) -> str:
    """Uno de los cuatro del desplegable (Parte C §4). Vacío = medición."""
    tipo = basedatos.limpiar(crudo).lower()
    if not tipo:
        return "medicion"
    if tipo not in TIPOS_ANEXO:
        opciones = ", ".join(NOMBRES_TIPO_ANEXO[t] for t in TIPOS_ANEXO)
        raise ErrorEntrada(
            f"«{tipo}» no es un tipo de anexo. Elegí uno de estos: {opciones}."
        )
    return tipo


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


#: Qué se le dice al médico cuando el nombre del paciente llegó vacío. Cambia
#: según desde dónde se guarda: en el récipe el botón dice «Guardar e imprimir»
#: y en la Historia dice «Crear paciente» (dec. 18), y un error tiene que
#: nombrar el botón que el médico acaba de apretar.
FALTA_NOMBRE_RECIPE = "Escribí el nombre del paciente antes de guardar."
FALTA_NOMBRE_ALTA = (
    "Escribí el nombre del paciente para darlo de alta. Es lo único "
    "obligatorio; la cédula, la edad y el teléfono se pueden completar después."
)


def validar_paciente(crudo: Any,
                     falta_nombre: str = FALTA_NOMBRE_RECIPE) -> dict[str, Any]:
    """Valida el bloque `paciente`. El nombre es obligatorio; la cédula, no (§15.4).

    Es el **mismo** validador para el récipe y para el alta desde la Historia
    (dec. 18): los dos guardan la misma persona en la misma tabla, y tener dos
    listas de campos con dos topes distintos terminaría en un alta que acepta
    una edad que después el récipe rechaza. Lo único que cambia entre los dos
    caminos es el texto de «falta el nombre», que nombra el botón apretado.
    """
    if not isinstance(crudo, Mapping):
        crudo = {}
    nombre = _texto(crudo.get("nombre"), 120)
    if not nombre:
        raise ErrorEntrada(falta_nombre)
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

    La forma no cambió en la 2.0, pero `codigo` es ahora el del paciente
    (dec. 2) y se repite en todos sus récipes: quien identifica cada uno es el
    `id` —que es el que viaja a `/api/recipes/<id>/pdf`, `/abrir` y `/anular`—
    junto con `fecha_emision`. Por eso el Historial nunca busca un récipe por
    código: lo usa para agrupar y para mostrar.
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


def codigo_relleno(conexion: sqlite3.Connection) -> str:
    """``EC-____``: el hueco que se imprime cuando todavía no hay número.

    Un solo grupo, porque el código del paciente no lleva año (dec. 1).
    """
    return f"{_prefijo(conexion)}-{RELLENO_CODIGO}"


def paciente_existente(conexion: sqlite3.Connection,
                       paciente: Mapping[str, Any]) -> Any:
    """El paciente que va a recibir el récipe, **si ya está en la base**.

    Repite el camino de `basedatos.obtener_o_crear_paciente` —id elegido de la
    lista, si no cédula, si no nombre normalizado exacto— sin crear nada: es
    una consulta, y la usa la vista previa, que no puede escribir (§6.2).

    Devuelve la fila del paciente o ``None`` si es alguien nuevo.
    """
    if paciente.get("id"):
        return basedatos.obtener_paciente(conexion, int(paciente["id"]))
    fila = basedatos.obtener_paciente_por_cedula(conexion, paciente.get("cedula"))
    if fila is not None:
        return fila
    nombre = basedatos.limpiar(paciente.get("nombre"))
    if not nombre:
        return None
    objetivo = basedatos.normalizar(nombre)
    # `buscar_pacientes` ordena por veces_atendido igual que el alta, así que
    # ante dos homónimos la previa muestra el mismo que se va a usar al guardar.
    for candidato in basedatos.buscar_pacientes(conexion, nombre):
        if basedatos.normalizar(candidato["nombre"]) == objetivo:
            return candidato
    return None


def paciente_ya_registrado(conexion: sqlite3.Connection, nombre: Any,
                           cedula: Any) -> Any:
    """El paciente que un alta con esos datos va a **reusar**, si lo hay (dec. 18).

    Mira exactamente lo mismo que `basedatos.obtener_o_crear_paciente` —primero
    la cédula; si no hay, el nombre normalizado idéntico (sin acentos, sin
    mayúsculas, sin dobles espacios)— pero sin crear ni tocar nada. Se llama
    **antes** del alta y dentro de su misma transacción, porque
    `obtener_o_crear_paciente` devuelve un id y no cuenta si lo creó o lo
    encontró, y esa diferencia es justo la que la pantalla necesita para decir
    «Este paciente ya estaba registrado» y abrirle la historia que ya tiene en
    vez de armarle una segunda.

    No se reusa `paciente_existente`: aquella resuelve al paciente *elegido en
    el formulario del récipe* —que puede venir con `id` de la lista— y busca el
    nombre a través del autocompletado, que corta en ocho resultados. Acá el
    nombre se compara contra la tabla entera, porque un homónimo que la
    sugerencia no llegó a mostrar igual lo va a reusar el alta, y decirle al
    médico que creamos uno nuevo cuando en realidad devolvimos el viejo sería
    mentirle sobre el archivo del paciente.

    Devuelve la fila o ``None`` si de verdad es alguien nuevo.
    """
    fila = basedatos.obtener_paciente_por_cedula(conexion, cedula)
    if fila is not None:
        return fila
    limpio = basedatos.limpiar(nombre)
    if not limpio:
        return None
    return conexion.execute(
        "SELECT * FROM pacientes WHERE nombre_norm = ? "
        "ORDER BY veces_atendido DESC LIMIT 1",
        (basedatos.normalizar(limpio),),
    ).fetchone()


def codigo_para_previa(conexion: sqlite3.Connection,
                       paciente: Mapping[str, Any]) -> str:
    """Qué código muestra la vista previa (dec. 2).

    Si el paciente ya existe, **su** código: es el que va a salir impreso, y
    verlo antes de guardar es media razón de ser de la previa. Si es alguien
    nuevo, el relleno ``EC-____``: el número se asigna recién al guardar, y un
    formulario abandonado no puede quemar uno (§6.2). Acá no se asigna nada.
    """
    fila = paciente_existente(conexion, paciente)
    codigo = basedatos.limpiar(fila["codigo"]) if fila is not None else ""
    return codigo or codigo_relleno(conexion)


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

    @app.errorhandler(pdf_informe.InformeError)
    def _error_informe(err: pdf_informe.InformeError):
        """Los errores del informe ya vienen escritos para el médico.

        `TipoDesconocidoError`, `AnexoNoEncontradoError` y `AnexoNoEsImagenError`
        dicen exactamente qué hacer (destildar el anexo, volver a adjuntarlo,
        elegir otro tipo), así que se devuelven tal cual con un 400: son cosas
        que el médico puede arreglar desde la pantalla.
        """
        estado = 500 if isinstance(err, pdf_comun.RecursoFaltanteError) else 400
        return jsonify({"error": str(err)}), estado

    @app.errorhandler(pdf_historia.HistoriaError)
    def _error_historia(err: pdf_historia.HistoriaError):
        return jsonify({"error": (
            f"No se pudo armar la historia para imprimir. ({err})"
        )}), 500

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
                # El código viaja porque la pantalla de la historia lo muestra
                # en la lista y en la cabecera del paciente elegido (dec. 1):
                # es lo que el médico tiene a mano mirando un récipe impreso.
                "codigo": f["codigo"] or "",
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
            codigo=codigo_relleno(con()),
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
        """PDF de muestra, SIN asignar ni quemar ningún número (§6.2).

        El código que se ve es el **del paciente** (dec. 2): si ya está en la
        base, sale su código de verdad —el mismo que va a imprimir el récipe—;
        si es alguien nuevo, sale el relleno ``EC-____`` y el número se asigna
        recién al guardar. En los dos casos la previa solo lee: no toca el
        contador ni escribe en la base.

        El PDF se arma en una carpeta temporal que se borra sola y se devuelve
        inline: en `pacientes\\` no queda nada —ni siquiera la carpeta del
        paciente, que se crea recién al guardar—, así que las previas no
        ensucian el archivo del médico.
        """
        cuerpo = _cuerpo()
        paciente = validar_paciente(cuerpo.get("paciente"))
        items = validar_items(cuerpo.get("items"))
        fecha = _texto(cuerpo.get("fecha_emision"), 30) or None

        datos = _datos_pdf(
            codigo=codigo_para_previa(con(), paciente),
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
           paciente + `crear_recipe`, que adentro resuelve el código **del
           paciente** —asignándoselo si todavía no tiene—, copia los renglones
           literales y aprende los términos (§6.3, §8). Si algo falla, no queda
           ni el récipe ni el número.
        3. Recién con el código en la mano se crea la carpeta del paciente
           (dec. 17), se genera el PDF adentro de ``recipes\\``, se guarda su
           ruta y se abre en el visor del sistema, listo para imprimir.

        Desde la 2.0 el `codigo` que se devuelve y se imprime es el del
        paciente (dec. 2), así que el segundo récipe del mismo paciente sale
        con el mismo número. Lo que los separa es el `id` del récipe, su fecha
        y —en disco— el sufijo ``_v2`` del nombre de archivo.
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
            _datos_pdf(codigo_relleno(conexion),
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

        # 3. Con el código asignado, la carpeta del paciente (dec. 17). Se pide
        # acá, aparte, y no solo de refilón adentro de `ruta_pdf_nueva`: este es
        # el momento en que el paciente tiene código, que es cuando dec. 17
        # manda crearla. Si el PDF fallara, la carpeta ya está —vacía, pero
        # está— y la historia clínica y los anexos la encuentran hecha. Es
        # idempotente: `ruta_pdf_nueva` la vuelve a pedir y devuelve la misma.
        carpeta_paciente(app.config["DIR_DATOS"], recipe["codigo"],
                         paciente["nombre"])

        # 4. PDF, ruta y visor.
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

        # 5. El registro Excel. Nunca puede impedir emitir (§9): si estaba
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

        Buscar por código (`EC-0001`) trae ahora **todos** los récipes de ese
        paciente, del más nuevo al más viejo (dec. 2): es exactamente lo que
        quiere el que tiene un récipe impreso en la mano y quiere ver el
        historial de quien se lo dio.

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
    # B-bis · Historia clínica e informes (dec. 9 a 14)
    # ===================================================================
    # Solo los dos endpoints que **emiten un documento**. La pantalla de la
    # historia —fichas, consultas, bandeja de anexos— llega en otra fase; lo
    # que se necesitaba ahora era que los tres generadores de PDF tuvieran por
    # dónde salir a la impresora.

    def _paciente_o_404(paciente_id: int):
        fila = basedatos.obtener_paciente(con(), paciente_id)
        if fila is None:
            raise _NoEncontrado(
                "Ese paciente ya no está en la lista. Volvé a buscarlo por "
                "nombre o por cédula."
            )
        return fila

    def _anexos_del_informe(conexion: sqlite3.Connection, paciente_id: int,
                            crudos: Any) -> tuple[list[int], list[dict[str, Any]]]:
        """Resuelve los anexos marcados (dec. 12) **antes** de tocar la base.

        Devuelve los ids para guardarlos con el informe y los dicts con la
        ruta absoluta que espera `pdf_informe`. Si uno no está en la base, es
        de otro paciente, el archivo ya no está en disco o no es una imagen que
        se pueda pegar en una página, se corta acá: un informe emitido sin el
        anexo que el médico creía estar mandando es peor que un informe que no
        salió, porque nadie se da cuenta hasta que ya lo entregó.

        Las mismas tres revisiones las vuelve a hacer `pdf_informe` sobre las
        rutas, y no sobra: allá se cortaría *después* de guardar el informe en
        la base —el PDF se arma al final, a propósito, para que un fallo del
        dibujo no pierda el texto—, y el médico se quedaría con una tarjeta
        «informe sin PDF» en la historia por haber tildado un archivo que no
        iba. Un formulario mal llenado no puede dejar rastro.
        """
        if crudos is None:
            crudos = []
        if not isinstance(crudos, list):
            raise ErrorEntrada(
                "La lista de anexos llegó mal. Destildá los anexos y volvé a "
                "marcarlos."
            )
        if len(crudos) > MAX_ANEXOS_INFORME:
            raise ErrorEntrada(
                f"Marcaste {len(crudos)} anexos y el informe admite hasta "
                f"{MAX_ANEXOS_INFORME}. Dejá los que hagan falta y el resto "
                "entregalos impresos aparte."
            )

        ids: list[int] = []
        para_pdf: list[dict[str, Any]] = []
        for crudo in crudos:
            anexo_id = _entero(crudo, "El anexo", 1, 2 ** 31)
            if anexo_id is None:
                continue
            fila = basedatos.obtener_anexo(conexion, anexo_id)
            if fila is None or int(fila["paciente_id"]) != paciente_id:
                raise ErrorEntrada(
                    "Uno de los anexos marcados ya no está en la historia de "
                    "este paciente. Actualizá la pantalla y volvé a marcarlo."
                )
            ruta = Path(app.config["DIR_DATOS"]) / str(fila["ruta_relativa"])
            if not ruta.is_file():
                raise _NoEncontrado(
                    "No encuentro el archivo de uno de los anexos "
                    f"({fila['ruta_relativa']}). Si moviste o borraste la "
                    "carpeta del paciente, restaurá el último respaldo desde "
                    "Configuración; si no, volvé a adjuntar la imagen."
                )
            if ruta.suffix.lower() not in EXTENSIONES_BANDEJA:
                # Dec. 11 acepta laboratorios en PDF entre los anexos de la
                # historia, pero un PDF no se incrusta como página: se entrega
                # aparte. La pantalla ya apaga esa casilla; esto es para el
                # pedido que llega igual (una pantalla vieja, un anexo que se
                # marcó antes de que la lista se refrescara).
                cual = ruta.suffix.lstrip(".").upper() or "archivo"
                raise ErrorEntrada(
                    f"El anexo «{ruta.name}» es un {cual} y no se puede pegar "
                    "adentro del informe. Destildalo e imprimilo aparte, junto "
                    "con el informe."
                )
            ids.append(anexo_id)
            tipo = basedatos.limpiar(fila["tipo"])
            para_pdf.append({
                "ruta": str(ruta),
                # El pie de la página de anexo lo lee una persona, así que sale
                # el nombre largo del desplegable («Medición de composición
                # corporal») y no la llave con la que se guarda («medicion»).
                # Un tipo viejo que no esté en el mapa se imprime tal cual.
                "tipo": NOMBRES_TIPO_ANEXO.get(tipo.lower(), tipo),
                "fecha": fila["fecha_medicion"],
            })
        return ids, para_pdf

    def _anexos_pedidos(cuerpo: Mapping[str, Any]) -> Any:
        """La lista de anexos marcados, venga con el nombre que venga.

        El contrato de la pantalla de informes los manda como `anexo_ids`; la
        E2 los recibía como `anexos` y hay código —y tests— que ya usan ese
        nombre. Se aceptan los dos y **no** se mezclan: si llegan ambos, manda
        `anexo_ids`, que es el nombre nuevo. Mandar los dos con contenidos
        distintos sería un formulario roto, no una elección del médico.
        """
        if cuerpo.get("anexo_ids") is not None:
            return cuerpo.get("anexo_ids")
        return cuerpo.get("anexos")

    #: Qué campos del cuerpo del pedido usa cada tipo de informe, y con qué
    #: recorte. Lo comparten la validación y el armado del PDF, así que no hay
    #: forma de que uno guarde un campo que el otro no imprime.
    CAMPOS_CLINICO = {
        "cuerpo": MAX_TEXTO_INFORME,
        "diagnostico": MAX_TEXTO_LARGO,
        "tratamiento": MAX_TEXTO_LARGO,
    }
    CAMPOS_ASEGURADORA = {
        "numero_poliza": MAX_TEXTO_CORTO,
        "prestacion_sanitaria": MAX_TEXTO_LARGO,
        "antecedentes": MAX_TEXTO_INFORME,
        "motivo_consulta": MAX_TEXTO_INFORME,
        "diagnostico": MAX_TEXTO_LARGO,
        "evolucion": MAX_TEXTO_INFORME,
    }

    @app.post("/api/informes")
    def crear_informe():
        """Emite un informe: lo guarda en la historia y abre el PDF (dec. 10).

        Orden de las cosas, igual que en el récipe:

        1. Se valida todo lo que se puede validar sin escribir —el paciente,
           el tipo, los anexos marcados y que el informe diga *algo*—, así un
           formulario a medio llenar no deja una fila muerta en la base.
        2. Una transacción: se le asegura el código al paciente (dec. 1) y se
           guarda el informe con su texto final y sus anexos elegidos.
        3. Recién ahí se arma el PDF adentro de ``pacientes\\<código>\\informes\\``
           (dec. 17), se guarda su ruta y se abre en el visor, listo para
           imprimir y firmar… aunque ya sale firmado (dec. 9).

        Si el PDF fallara, el informe **queda guardado**: se puede reimprimir
        desde la historia, igual que un récipe.
        """
        cuerpo = _cuerpo()
        conexion = con()

        paciente_id = _entero(cuerpo.get("paciente_id"), "El paciente", 1, 2 ** 31)
        if paciente_id is None:
            raise ErrorEntrada(
                "Elegí a qué paciente le hacés el informe antes de guardarlo."
            )
        paciente = _paciente_o_404(paciente_id)

        tipo = pdf_informe.normalizar_tipo(cuerpo.get("tipo"))
        definicion = (CAMPOS_CLINICO if tipo == pdf_informe.TIPO_CLINICO
                      else CAMPOS_ASEGURADORA)
        campos = {campo: _texto_largo(cuerpo.get(campo), maximo)
                  for campo, maximo in definicion.items()}
        if not any(campos.values()):
            raise ErrorEntrada(
                "El informe está vacío. Escribí al menos "
                f"{VACIO_POR_TIPO[tipo]} antes de emitirlo."
            )

        consulta_id = _entero(cuerpo.get("consulta_id"), "La consulta", 1, 2 ** 31)
        if consulta_id is not None and basedatos.obtener_consulta(
                conexion, consulta_id) is None:
            raise ErrorEntrada(
                "Esa consulta ya no está en la historia. Actualizá la pantalla "
                "y volvé a elegirla."
            )

        anexo_ids, anexos_pdf = _anexos_del_informe(
            conexion, paciente_id, _anexos_pedidos(cuerpo))

        medico = datos_medico(conexion)
        # La especialidad y la ciudad se pueden pisar por informe (un informe
        # se puede firmar desde otra ciudad), pero lo normal es que lleguen
        # vacías y valga lo de Configuración.
        especialidad = (_texto(cuerpo.get("especialidad"), MAX_CAMPO_MEDICO)
                        or medico["medico_especialidad"])
        ciudad = (_texto(cuerpo.get("ciudad"), MAX_CAMPO_MEDICO)
                  or medico["ciudad"])
        fecha = codigos.normalizar_fecha(_texto(cuerpo.get("fecha"), 30) or None)

        with basedatos.transaccion(conexion, inmediata=True):
            codigo = codigos.asegurar_codigo_paciente(conexion, paciente_id)
            informe_id = basedatos.crear_informe(
                conexion, paciente_id, tipo=tipo, fecha=fecha,
                anexos=anexo_ids, consulta_id=consulta_id,
                codigo_paciente=codigo, ciudad=ciudad,
                especialidad=especialidad, **campos,
            )

        nombre = basedatos.limpiar(paciente["nombre"])
        carpeta_paciente(app.config["DIR_DATOS"], codigo, nombre)
        destino = ruta_informe_nueva(app.config["DIR_DATOS"], codigo, nombre, fecha)

        datos_pdf = {
            "tipo": tipo,
            "codigo": codigo,
            "fecha": fecha,
            "paciente_nombre": nombre,
            "paciente_cedula": basedatos.limpiar(paciente["cedula"]),
            "medico_nombre": medico["medico_nombre"],
            "medico_especialidad": especialidad,
            "medico_comezu": medico["medico_comezu"],
            "medico_mpps": medico["medico_mpps"],
            "ciudad": ciudad,
            "anexos": anexos_pdf,
            **campos,
        }
        try:
            pdf_informe.generar_informe(
                datos_pdf, str(destino),
                ruta_logo=logo(), dir_fuentes=app.config["DIR_FUENTES"],
            )
        except Exception as err:  # el informe YA está guardado: no se pierde
            return jsonify({"error": (
                f"El informe de {nombre} quedó guardado, pero no se pudo crear "
                f"el PDF: {err}. Volvé a generarlo desde la historia."
            )}), 500

        basedatos.guardar_ruta_pdf_informe(conexion, informe_id, str(destino))
        abrir_en_visor(destino)
        return jsonify({
            "id": informe_id,
            "codigo": codigo,
            "tipo": tipo,
            "fecha": fecha,
            "ruta_pdf": str(destino),
            "cantidad_anexos": len(anexo_ids),
        })

    # ------------------------------------------------ la lista de informes

    def _json_informe(fila: Any, cantidad_anexos: int = 0) -> dict[str, Any]:
        """Un informe con la forma que muestra la historia.

        No viaja el texto del informe: la lista es para reconocerlo y volver a
        imprimirlo, y el documento que vale es el PDF guardado, no una
        recomposición del texto. `tiene_pdf` mira el **disco**, no la columna:
        una ruta guardada que apunta a un archivo que el médico movió es
        exactamente el caso en el que la pantalla tiene que mostrar el informe
        sin ofrecer el botón de reimprimir.
        """
        ruta = basedatos.limpiar(fila["ruta_pdf"])
        return {
            "id": int(fila["id"]),
            "tipo": fila["tipo"],
            "fecha": fila["fecha"],
            "diagnostico": fila["diagnostico"] or "",
            "anulado": bool(fila["anulado"]),
            "motivo_anulacion": fila["motivo_anulacion"] or "",
            "fecha_anulacion": fila["fecha_anulacion"] or "",
            "tiene_pdf": bool(ruta) and Path(ruta).is_file(),
            "cantidad_anexos": int(cantidad_anexos),
        }

    @app.get("/api/pacientes/<int:paciente_id>/informes")
    def listar_informes_paciente(paciente_id: int):
        """Los informes emitidos a ese paciente, del más nuevo al más viejo.

        Los anulados vienen también, marcados: un informe anulado es un hecho
        de la historia y esconderlo sería mentirle al que la lee (§10, mismo
        criterio que el Historial de récipes).
        """
        conexion = con()
        _paciente_o_404(paciente_id)
        filas = basedatos.listar_informes(conexion, paciente_id)
        cuenta = basedatos.anexos_por_informe(
            conexion, [int(f["id"]) for f in filas])
        return jsonify({"informes": [
            _json_informe(f, cuenta.get(int(f["id"]), 0)) for f in filas
        ]})

    def _dia_del_informe(fila: Any) -> str:
        """La fecha del informe como la lee una persona: ``18/08/2026``.

        En la base, `informes.fecha` es una marca de tiempo entera
        (`2026-08-18T20:17:56`), igual que la del récipe: sirve para ordenar
        dos informes del mismo día. Pero un informe **no tiene número** —el
        código impreso es el del paciente y lo comparten todos sus documentos
        (dec. 2)—, así que la fecha es lo único con lo que un mensaje puede
        nombrarlo, y ahí no puede salir con la hora y los segundos pegados.
        """
        return pdf_comun.formatear_fecha(fila["fecha"]) or str(fila["fecha"] or "")

    def _informe_o_404(informe_id: int):
        fila = basedatos.obtener_informe(con(), informe_id)
        if fila is None:
            raise _NoEncontrado(
                "Ese informe ya no está en la historia. Actualizá la pantalla y "
                "volvé a buscarlo."
            )
        return fila

    def _pdf_informe_o_404(fila) -> Path:
        """Ruta del PDF guardado del informe, o un 404 que dice qué falta.

        Mismo texto y mismo criterio que `_pdf_o_404` para los récipes: se
        nombra el archivo que se buscaba, porque la mitad de las veces el
        médico lo movió él mismo y con verlo lo encuentra.
        """
        ruta = basedatos.limpiar(fila["ruta_pdf"])
        if not ruta or not Path(ruta).is_file():
            raise _NoEncontrado(
                f"No encuentro el PDF del informe del {_dia_del_informe(fila)}. Si "
                "moviste o borraste la carpeta del paciente, restaurá el último "
                "respaldo desde Configuración. (Lo buscaba en: "
                f"{ruta or 'ninguna ruta guardada'})"
            )
        return Path(ruta)

    @app.get("/api/informes/<int:informe_id>/pdf")
    def pdf_informe_guardado(informe_id: int):
        """El MISMO archivo que se emitió, byte por byte (dec. 10, §7-B).

        Nunca se regenera: el informe salió firmado y con los anexos que el
        médico eligió ese día, y rehacerlo hoy podría darle otro membrete, otra
        especialidad de Configuración o —peor— dejar afuera un anexo cuyo
        archivo ya no está. Un documento emitido no se recompone: se reimprime.

        Se lee entero a memoria y se manda desde ahí, como el récipe: con el
        handle abierto Windows no deja mover ni borrar el PDF mientras la
        aplicación esté corriendo.
        """
        fila = _informe_o_404(informe_id)
        ruta = _pdf_informe_o_404(fila)
        try:
            contenido = ruta.read_bytes()
        except OSError as err:
            raise _NoEncontrado(
                f"No se pudo leer el PDF del informe del {_dia_del_informe(fila)}. "
                "Fijate que la carpeta del paciente esté disponible y probá de "
                f"nuevo. ({err})"
            ) from err
        return send_file(
            io.BytesIO(contenido), mimetype="application/pdf",
            as_attachment=False, download_name=ruta.name, max_age=0,
        )

    @app.post("/api/informes/<int:informe_id>/abrir")
    def abrir_informe(informe_id: int):
        """Reimprimir: abre el PDF guardado en el visor del sistema."""
        fila = _informe_o_404(informe_id)
        ruta = _pdf_informe_o_404(fila)
        if not abrir_con_el_sistema(ruta) and not _abrir_desactivado():
            return jsonify({"error": (
                "No se pudo abrir el PDF con el visor de Windows. Abrilo a "
                f"mano desde: {ruta}"
            )}), 500
        return jsonify({"ok": True})

    @app.post("/api/informes/<int:informe_id>/anular")
    def anular_informe_emitido(informe_id: int):
        """Anula un informe con motivo escrito. No borra nada, nunca.

        Espejo de la anulación del récipe (§2.4 y §10): el PDF queda en disco
        —el paciente o la aseguradora pueden tener una copia y hay que poder
        comparar contra qué se anuló—, el motivo queda escrito y anular dos
        veces es un 400 que no pisa el motivo original.

        **El Excel no se toca, y es a propósito.** El registro de §9 es el
        registro de *récipes*: sus columnas son código, paciente, medicamentos
        y estado, y un informe no tiene medicamentos. Meterlo ahí obligaría a
        una hoja nueva con otro sentido, y el dueño no la pidió: los informes
        se listan desde la historia del paciente, que es donde se los busca. Si
        más adelante el médico quiere el informe en el Excel, se agrega una
        hoja aparte y se rehace el registro también acá.
        """
        cuerpo = _cuerpo()
        motivo = _texto(cuerpo.get("motivo"), MAX_TEXTO_LARGO)
        if not motivo:
            raise ErrorEntrada(
                "Escribí el motivo de la anulación antes de anular el informe."
            )

        conexion = con()
        fila = _informe_o_404(informe_id)
        if fila["anulado"]:
            fecha = pdf_comun.formatear_fecha(fila["fecha_anulacion"])
            raise ErrorEntrada(
                f"El informe del {_dia_del_informe(fila)} ya estaba anulado"
                + (f" el {fecha}" if fecha else "")
                + f". Motivo: {fila['motivo_anulacion'] or 'sin motivo guardado'}."
            )

        with basedatos.transaccion(conexion, inmediata=True):
            basedatos.anular_informe(conexion, informe_id, motivo)

        actualizada = basedatos.obtener_informe(conexion, informe_id)
        cuenta = basedatos.anexos_por_informe(conexion, [informe_id])
        return jsonify(_json_informe(actualizada, cuenta.get(informe_id, 0)))

    # -------------------------------------- ayudas para llenar el formulario

    @app.get("/api/pacientes/<int:paciente_id>/ultimo-recipe")
    def ultimo_recipe_paciente(paciente_id: int):
        """El botón "Traer del último récipe" de Tratamiento indicado (dec. 10).

        Devuelve los renglones **literales** del último récipe vigente, que es
        lo que el paciente tiene en la mano. Los anulados no cuentan: volcar el
        tratamiento de un récipe que se anuló es justamente el error que la
        anulación quiso corregir.

        Sin récipes (o con todos anulados) devuelve la lista vacía y no un 404:
        que un paciente nuevo no tenga récipe previo no es una falla, y la
        pantalla solo tiene que dejar el botón sin nada que traer.
        """
        conexion = con()
        _paciente_o_404(paciente_id)
        recipe = basedatos.ultimo_recipe_de_paciente(conexion, paciente_id)
        if recipe is None:
            return jsonify({"fecha": "", "items": []})
        items = basedatos.obtener_items(conexion, int(recipe["id"]))
        return jsonify({
            "fecha": recipe["fecha_emision"],
            "items": [{
                "medicamento": fila["medicamento"] or "",
                "presentacion": fila["presentacion"] or "",
                "cantidad": fila["cantidad"] or "",
                "dosis": fila["dosis"] or "",
            } for fila in items],
        })

    @app.get("/api/pacientes/<int:paciente_id>/frase-inicial")
    def frase_inicial_paciente(paciente_id: int):
        """La primera frase del informe clínico, ya armada (dec. 10).

        La pantalla la pide **una vez**, al abrir el formulario, y la deja en
        el recuadro para que el médico la edite: dec. 10 dice que es editable,
        así que esto es un punto de partida y no una regla. Por eso no se
        recalcula sola mientras se escribe —pisarle el texto al médico porque
        cambió una letra del motivo sería insoportable— y por eso el que se
        guarda es el texto final que quedó en el recuadro, no esta frase.

        El sexo y la edad salen de la ficha; si la ficha no dice el sexo, la
        frase sale neutra ("paciente de 60 años de edad") en vez de adivinar.
        Los antecedentes salen de `historias.cronico_degenerativos`, resumidos
        a una enumeración; si el paciente todavía no tiene historia cargada, la
        frase sale sin la parte de antecedentes.
        """
        conexion = con()
        paciente = _paciente_o_404(paciente_id)
        motivo = _texto_largo(request.args.get("motivo"), MAX_TEXTO_LARGO)
        historia = basedatos.obtener_historia(conexion, paciente_id)
        antecedentes = resumir_antecedentes(
            historia["cronico_degenerativos"] if historia is not None else "")
        return jsonify({"frase": pdf_informe.frase_inicial(
            paciente["sexo"], paciente["edad"], motivo, antecedentes)})

    @app.get("/api/pacientes/<int:paciente_id>/historia/pdf")
    def pdf_historia_paciente(paciente_id: int):
        """La historia imprimible del paciente, armada al vuelo (dec. 14).

        **No se persiste ninguna ruta y no se guarda nada en la base**: esto es
        una impresión, no un documento emitido. Un récipe y un informe son
        actos —llevan número, quedan en el historial y se pueden anular—; la
        historia es la foto de lo que hay hoy, y mañana va a ser otra. Guardar
        un PDF por cada vez que el médico la imprime solo llenaría la carpeta
        del paciente de copias viejas indistinguibles entre sí.

        Se devuelve inline para que la interfaz lo muestre o lo mande a
        imprimir; el archivo temporal se borra solo.
        """
        conexion = con()
        paciente = _paciente_o_404(paciente_id)
        datos = {
            "codigo": basedatos.limpiar(paciente["codigo"]),
            "paciente": basedatos.a_dict(paciente),
            "historia": basedatos.a_dict(
                basedatos.obtener_historia(conexion, paciente_id)) or {},
            # `listar_consultas` ya devuelve de la más nueva a la más vieja y
            # trae los signos vitales aplanados en la misma fila, que es
            # exactamente lo que `pdf_historia` sabe leer.
            "consultas": basedatos.a_dict(
                basedatos.listar_consultas(conexion, paciente_id)),
            # Dec. 13 ampliada: la tendencia va TAMBIÉN adentro del PDF, con
            # las mismas series que muestra la pantalla. `pdf_historia` dibuja
            # solo las métricas con dos puntos o más y omite la sección entera
            # si no hay ninguna, así que esto no molesta en la primera visita.
            "evolucion": series_evolucion(conexion, paciente_id),
            "fecha": date.today().isoformat(),
        }
        with tempfile.TemporaryDirectory(prefix="recipes-historia-") as tmp:
            destino = os.path.join(tmp, "historia.pdf")
            pdf_historia.generar_historia(
                datos, destino,
                ruta_logo=logo(), dir_fuentes=app.config["DIR_FUENTES"],
            )
            with open(destino, "rb") as archivo:
                contenido = archivo.read()
        nombre = sanitizar_nombre_archivo(basedatos.limpiar(paciente["nombre"]))
        codigo = basedatos.limpiar(paciente["codigo"]) or "paciente"
        return send_file(
            io.BytesIO(contenido), mimetype="application/pdf",
            as_attachment=False, max_age=0,
            download_name=f"HISTORIA_{codigo}_{nombre}.pdf",
        )

    # ===================================================================
    # B-ter · La pantalla de la historia (dec. 3 a 6, 11, 13, 15 y 17)
    # ===================================================================
    # Todo lo que la pantalla de la historia lee y escribe: la ficha con los
    # antecedentes (una vez por paciente), las consultas con sus signos
    # vitales (cada visita), la bandeja de imágenes de WhatsApp, los anexos y
    # el gráfico de evolución.

    #: El mapa `token -> archivo` de la bandeja, uno por aplicación y solo en
    #: memoria. Se arma acá adentro —y no como global del módulo— para que dos
    #: apps de prueba en el mismo proceso no compartan tokens.
    bandeja = BandejaEnMemoria()

    def _dir_entrada() -> Path:
        """La carpeta `entrada`, creada si hiciera falta.

        `main.preparar_carpeta_datos` ya la crea en cada arranque; acá se
        vuelve a asegurar porque el médico puede borrarla sin querer y la
        bandeja no tiene por qué romperse ni el acceso directo del Escritorio
        quedar apuntando a la nada.
        """
        destino = Path(app.config["DIR_DATOS"]) / DIR_ENTRADA
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return destino

    def _consulta_o_404(consulta_id: int):
        fila = basedatos.obtener_consulta(con(), consulta_id)
        if fila is None:
            raise _NoEncontrado(
                "Esa consulta ya no está en la historia. Actualizá la pantalla "
                "y volvé a abrirla."
            )
        return fila

    def _anexo_o_404(anexo_id: int):
        fila = basedatos.obtener_anexo(con(), anexo_id)
        if fila is None:
            raise _NoEncontrado(
                "Ese anexo ya no está en la historia. Actualizá la pantalla; si "
                "hace falta, volvé a adjuntar la imagen."
            )
        return fila

    def _json_signos(fila: Any) -> dict[str, Any] | None:
        """Los doce campos de la tabla del papel, o `None` si no se midió nada."""
        if fila is None:
            return None
        datos = basedatos.a_dict(fila)
        signos = {campo: datos.get(campo) for campo in basedatos.CAMPOS_SIGNOS_VITALES}
        return signos if any(v is not None for v in signos.values()) else None

    def _json_consulta_de_lista(fila: Any) -> dict[str, Any]:
        """Una consulta de la línea de tiempo, con los signos vitales anidados.

        `listar_consultas` los trae aplanados en la misma fila —le sirve así al
        PDF— pero la pantalla los muestra como un bloque, así que acá se
        separan. Se conservan los contadores de anexos, récipes e informes: son
        los `📎2 📄1` del renglón colapsado.
        """
        datos = basedatos.a_dict(fila)
        signos = {campo: datos.pop(campo, None)
                  for campo in basedatos.CAMPOS_SIGNOS_VITALES}
        datos["signos_vitales"] = (
            signos if any(v is not None for v in signos.values()) else None)
        return datos

    def _json_consulta(conexion: sqlite3.Connection, consulta_id: int) -> dict[str, Any]:
        """La consulta recién guardada, con la misma forma que en la lista."""
        datos = basedatos.a_dict(basedatos.obtener_consulta(conexion, consulta_id))
        datos["signos_vitales"] = _json_signos(
            basedatos.obtener_signos_vitales(conexion, consulta_id))
        return datos

    def _json_anexo(fila: Any) -> dict[str, Any]:
        """Un anexo, con las dos direcciones que la pantalla necesita.

        La ruta relativa viaja porque es lo que el médico ve si abre la carpeta
        del paciente, pero la imagen **no** se pide por ruta: se pide por id,
        contra `/api/anexos/<id>/imagen`.
        """
        datos = basedatos.a_dict(fila)
        anexo_id = int(datos["id"])
        relativa = str(datos.get("ruta_relativa") or "")
        datos["nombre"] = Path(relativa).name
        datos["url_imagen"] = f"/api/anexos/{anexo_id}/imagen"
        datos["url_miniatura"] = f"/api/anexos/{anexo_id}/miniatura"
        return datos

    def _archivo_de_anexo(fila: Any) -> Path:
        ruta = Path(app.config["DIR_DATOS"]) / str(fila["ruta_relativa"])
        if not ruta.is_file():
            raise _NoEncontrado(
                f"No encuentro el archivo del anexo ({fila['ruta_relativa']}). "
                "Si moviste o borraste la carpeta del paciente, restaurá el "
                "último respaldo desde Configuración; si no, volvé a adjuntar "
                "la imagen."
            )
        return ruta

    # ------------------------------------------------- alta de un paciente
    @app.post("/api/pacientes")
    def alta_paciente():
        """Da de alta un paciente **desde la Historia**, sin emitir récipe (dec. 18).

        La historia es la puerta de entrada: el médico escribe un nombre en el
        buscador, no aparece, y lo crea ahí mismo con lo que tenga a mano
        —nombre (lo único obligatorio), cédula, edad, fecha de nacimiento, sexo
        y teléfono—. El alta termina con el paciente listo para trabajar: con su
        **código de por vida** (`EC-0007`, dec. 1) y con su **carpeta** en
        ``pacientes\\`` ya hecha (dec. 17), que es lo que necesitan el primer
        anexo de WhatsApp y el primer informe para tener dónde caer.

        **Nunca duplica.** Si ya hay alguien con esa cédula —o, sin cédula, con
        el mismo nombre normalizado— se devuelve **ese** paciente con
        ``ya_existia: true``, y la pantalla avisa «Este paciente ya estaba
        registrado» y le abre su historia. Duplicar a una persona parte su
        archivo en dos: la mitad de las mediciones en un lado y la mitad de los
        récipes en el otro, sin que nadie se entere hasta que falta algo. Los
        datos que llegan completan los que estaban vacíos (el médico carga de a
        poco) y **no pisan** los que ya tenían valor: corregir la ficha es un
        acto explícito de la Historia, no un efecto secundario de un alta.

        Todo el alta va en una sola transacción inmediata: si algo falla no
        queda ni el paciente ni el número quemado (§6.3). La carpeta se crea
        después, con el código ya en la mano, igual que en el récipe.

        Respuesta::

            201  {"paciente": {...}, "codigo": "EC-0007", "ya_existia": false}
            200  {"paciente": {...}, "codigo": "EC-0003", "ya_existia": true}

        `paciente` trae la fila completa —incluido el `codigo`, la `cedula`, la
        `edad` y el `sexo`—, que es exactamente lo que la pantalla necesita para
        abrir la historia recién creada y para el récipe predeterminado de ese
        paciente, sin tener que volver a pedir nada.
        """
        datos = validar_paciente(_cuerpo(), FALTA_NOMBRE_ALTA)
        conexion = con()

        with basedatos.transaccion(conexion, inmediata=True):
            existente = paciente_ya_registrado(
                conexion, datos["nombre"], datos["cedula"])
            paciente_id = basedatos.obtener_o_crear_paciente(
                conexion,
                nombre=datos["nombre"],
                cedula=datos["cedula"],
                fecha_nacimiento=datos["fecha_nacimiento"],
                edad=datos["edad"],
                sexo=datos["sexo"],
                telefono=datos["telefono"],
            )
            # `crear_paciente` ya le asigna el código; esto es para el paciente
            # que hubiera entrado por otro camino y esté sin número (dec. 1).
            codigo = codigos.asegurar_codigo_paciente(conexion, paciente_id)
            fila = basedatos.obtener_paciente(conexion, paciente_id)

        # Con el código en la mano, la carpeta (dec. 17). Va con el nombre
        # GUARDADO, no con el tipeado: si el paciente ya estaba, su carpeta
        # sigue siendo la que dice la base, y `carpeta_paciente` congela por
        # código de todos modos.
        carpeta_paciente(app.config["DIR_DATOS"], codigo,
                         basedatos.limpiar(fila["nombre"]))

        return jsonify({
            "paciente": basedatos.a_dict(fila),
            "codigo": codigo,
            "ya_existia": existente is not None,
        }), (200 if existente is not None else 201)

    # ------------------------------------------------------------- historia
    @app.get("/api/pacientes/<int:paciente_id>/historia")
    def ver_historia(paciente_id: int):
        """Todo lo que la pantalla de la historia muestra, en un solo pedido.

        Es una lectura pura: **no** asigna código ni crea carpetas. Abrir la
        historia de alguien para mirarla no puede quemar un número (§6.2); el
        código se le asigna en cuanto se guarda algo (la ficha, una consulta o
        un anexo), que es cuando el paciente deja de ser una consulta y pasa a
        tener archivo propio.

        `historia` viene en `null` mientras nadie llenó la ficha: la pantalla
        distingue "todavía no hay" de "está vacía" y arranca el flujo guiado de
        historia nueva (dec. 15).
        """
        conexion = con()
        paciente = _paciente_o_404(paciente_id)
        return jsonify({
            "paciente": basedatos.a_dict(paciente),
            "historia": basedatos.a_dict(
                basedatos.obtener_historia(conexion, paciente_id)),
            "consultas": [
                _json_consulta_de_lista(fila)
                for fila in basedatos.listar_consultas(conexion, paciente_id)
            ],
            "anexos": [
                _json_anexo(fila)
                for fila in basedatos.listar_anexos(conexion, paciente_id)
            ],
            "mediciones": basedatos.a_dict(
                basedatos.listar_mediciones(conexion, paciente_id)),
        })

    @app.post("/api/pacientes/<int:paciente_id>/historia")
    def guardar_historia(paciente_id: int):
        """Crea o corrige la ficha y los antecedentes (dec. 3 a 6).

        Se guarda **solo lo que llegó**, para que guardar una sección plegable
        no borre las otras. Y acá sí se le asegura el código al paciente y se
        le crea la carpeta (dec. 17): a partir de este momento tiene historia,
        y todo lo suyo —récipes, informes, anexos— va a vivir junta.
        """
        conexion = con()
        paciente = _paciente_o_404(paciente_id)
        campos = validar_historia(_cuerpo())

        with basedatos.transaccion(conexion, inmediata=True):
            codigo = codigos.asegurar_codigo_paciente(conexion, paciente_id)
            basedatos.guardar_historia(conexion, paciente_id, **campos)

        carpeta_paciente(app.config["DIR_DATOS"], codigo,
                         basedatos.limpiar(paciente["nombre"]))
        return jsonify({
            "codigo": codigo,
            "historia": basedatos.a_dict(
                basedatos.obtener_historia(conexion, paciente_id)),
        })

    # ------------------------------------------------------------ consultas
    def _guardar_consulta(conexion: sqlite3.Connection, paciente_id: int,
                          consulta_id: int | None) -> dict[str, Any]:
        """Alta o corrección de una consulta, que son lo mismo salvo el INSERT.

        El IMC y la TAM los calcula `guardar_signos_vitales` cuando faltan, y
        respeta lo que el médico haya escrito a mano.
        """
        cuerpo = _cuerpo()
        fecha = (_fecha_filtro(cuerpo.get("fecha"), "de la consulta")
                 or date.today().isoformat())
        campos = {
            "motivo": _texto_largo(cuerpo.get("motivo"), MAX_TEXTO_INFORME),
            "examen_fisico": _texto_largo(cuerpo.get("examen_fisico"), MAX_TEXTO_INFORME),
            "evolucion": _texto_largo(cuerpo.get("evolucion"), MAX_TEXTO_INFORME),
            "diagnostico": _texto_largo(cuerpo.get("diagnostico"), MAX_TEXTO_LARGO),
            "plan": _texto_largo(cuerpo.get("plan"), MAX_TEXTO_INFORME),
        }
        signos = validar_signos(cuerpo.get("signos"))

        with basedatos.transaccion(conexion, inmediata=True):
            codigos.asegurar_codigo_paciente(conexion, paciente_id)
            if consulta_id is None:
                consulta_id = basedatos.crear_consulta(
                    conexion, paciente_id, fecha=fecha, **campos)
            else:
                basedatos.actualizar_consulta(
                    conexion, consulta_id, fecha=fecha, **campos)
            basedatos.guardar_signos_vitales(conexion, consulta_id, **signos)
        return _json_consulta(conexion, consulta_id)

    @app.post("/api/pacientes/<int:paciente_id>/consultas")
    def crear_consulta(paciente_id: int):
        """Abre una consulta con sus signos vitales (dec. 3).

        Es lo que el médico hace todos los días: fecha (hoy por defecto),
        motivo, la tabla de signos vitales, evolución, diagnóstico y plan.
        """
        conexion = con()
        _paciente_o_404(paciente_id)
        return jsonify(_guardar_consulta(conexion, paciente_id, None)), 201

    @app.put("/api/consultas/<int:consulta_id>")
    def editar_consulta(consulta_id: int):
        """Corrige la consulta del día. Misma forma que el alta.

        No hay "consulta anulada": una consulta no es un documento emitido, es
        la nota de lo que pasó, y corregir una nota es lo normal.
        """
        conexion = con()
        fila = _consulta_o_404(consulta_id)
        return jsonify(_guardar_consulta(
            conexion, int(fila["paciente_id"]), consulta_id))

    # -------------------------------------------------------------- bandeja
    @app.get("/api/bandeja")
    def ver_bandeja():
        """Las imágenes recientes de la computadora, con miniatura (Parte C §4).

        Mira Descargas, el Escritorio (con las variantes de OneDrive) y la
        carpeta `entrada`; se queda con las de los últimos 30 días, descarta
        por SHA-256 las que ya están anexadas —así la bandeja se vacía sola sin
        borrar un solo archivo del disco— y devuelve las 24 más nuevas.

        El escaneo pasa **acá, cuando se pide**: no hay vigilancia en segundo
        plano (Parte C §4). Y lo que viaja es un token, nunca una ruta.
        """
        conexion = con()
        _dir_entrada()
        try:
            anexados = basedatos.sha256_anexados(conexion)
        except sqlite3.Error:
            anexados = set()

        imagenes: list[dict[str, Any]] = []
        for etiqueta, ruta in candidatos_bandeja(app.config["DIR_DATOS"]):
            if len(imagenes) >= MAX_BANDEJA:
                break
            try:
                if bandeja.hash_de(ruta) in anexados:
                    continue
                cuando = ruta.stat().st_mtime
            except OSError:
                continue  # se borró entre el listado y el hash: no es un error
            medidas = dimensiones_imagen(ruta)
            if medidas is None:
                continue  # no era una imagen de verdad (o está rota)
            imagenes.append({
                "token": bandeja.registrar(ruta, etiqueta),
                "nombre": ruta.name,
                "carpeta": etiqueta,
                "fecha_archivo": date.fromtimestamp(cuando).isoformat(),
                "ancho": medidas[0],
                "alto": medidas[1],
            })
        return jsonify({"imagenes": imagenes})

    @app.get("/api/bandeja/<token>/miniatura")
    def miniatura_bandeja(token: str):
        """La miniatura de una imagen de la bandeja, hecha al vuelo.

        El token se traduce a un archivo **y se vuelve a comprobar** que esté
        adentro de una carpeta permitida. Un token inventado o vencido responde
        404 con un texto que no dice ni una ruta: la respuesta no puede servir
        para averiguar qué hay en el disco.
        """
        encontrado = bandeja.resolver(token)
        ruta = encontrado[0] if encontrado else None
        if ruta is None or not ruta_de_bandeja_valida(app.config["DIR_DATOS"], ruta):
            raise _NoEncontrado(
                "Esa imagen ya no está en la bandeja. Actualizá la bandeja y "
                "volvé a elegirla."
            )
        try:
            contenido = bandeja.miniatura(token, ruta)
        except Exception as err:
            raise _NoEncontrado(
                "No pude armar la vista de esa imagen. Puede estar dañada o a "
                f"medio descargar; probá con otra. ({type(err).__name__})"
            ) from err
        return send_file(
            io.BytesIO(contenido), mimetype="image/jpeg",
            as_attachment=False, download_name="miniatura.jpg", max_age=0,
        )

    # --------------------------------------------------------------- anexos
    def _cuerpo_anexo() -> tuple[Mapping[str, Any], Any]:
        """Los campos del anexo y el archivo subido, si vino por multipart.

        Son los dos caminos de la Parte C §4: la bandeja manda JSON con un
        `token`, y el botón «Adjuntar imagen…» manda `multipart/form-data` con
        el archivo adentro. Todo lo demás (fecha, tipo, nota, medición) es
        igual en los dos.
        """
        subido = request.files.get("archivo")
        if subido is not None and subido.filename:
            return request.form, subido
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            raise ErrorEntrada(
                "No llegó ninguna imagen. Elegila de la bandeja o con el botón "
                "«Adjuntar imagen…» y volvé a intentar."
            )
        return datos, None

    def _medicion_del_cuerpo(cuerpo: Mapping[str, Any]) -> dict[str, Any]:
        """Los valores clave, vengan anidados en `medicion` o sueltos.

        Por JSON llegan anidados; por multipart llegan sueltos (un formulario
        no tiene diccionarios) o como un `medicion` con JSON adentro. Los tres
        caminos terminan igual.
        """
        crudo = cuerpo.get("medicion")
        if isinstance(crudo, str):
            texto = crudo.strip()
            try:
                crudo = json.loads(texto) if texto else {}
            except ValueError:
                raise ErrorEntrada(
                    "Los valores de la medición llegaron mal. Revisalos y "
                    "guardá otra vez."
                ) from None
        if not isinstance(crudo, Mapping):
            crudo = cuerpo
        return validar_medicion(crudo)

    @app.post("/api/pacientes/<int:paciente_id>/anexos")
    def crear_anexo(paciente_id: int):
        """Anexa una imagen a la historia: **copia**, nunca mueve (Parte C §5).

        Orden de las cosas, y por qué:

        1. Se valida todo —paciente, fecha confirmada, tipo, medición— antes de
           tocar un archivo.
        2. Se calcula el SHA-256 del original y se busca: si ya estaba anexado,
           se responde 409 diciendo a qué historia fue a parar. Anexar dos veces
           la misma foto no es un error grave, pero enterarse tarde sí.
        3. Se copia con `copy2` a ``pacientes\\<código>\\anexos\\`` con el
           nombre ``<fecha-de-la-medición>_<tipo>_<nn>.<ext>`` y se **verifica
           el hash de la copia**. El original queda intacto donde estaba: si
           algo sale mal, el médico no perdió nada.
        4. Se deja la miniatura al lado y recién ahí se escribe en la base.

        La fecha es obligatoria y es la de la medición, no la del archivo: en
        el ejemplo real había cuatro días de diferencia entre una y otra.
        """
        conexion = con()
        paciente = _paciente_o_404(paciente_id)
        cuerpo, subido = _cuerpo_anexo()

        fecha = _fecha_filtro(cuerpo.get("fecha_medicion"), "de la medición")
        if not fecha:
            raise ErrorEntrada(
                "Confirmá la fecha de la medición (la que dice el informe, no "
                "la del archivo) antes de anexarla."
            )
        tipo = validar_tipo_anexo(cuerpo.get("tipo"))
        nota = _texto_largo(cuerpo.get("nota"), MAX_TEXTO_LARGO)
        medicion = _medicion_del_cuerpo(cuerpo)

        consulta_id = _entero(cuerpo.get("consulta_id"), "La consulta", 1, 2 ** 31)
        if consulta_id is not None:
            consulta = basedatos.obtener_consulta(conexion, consulta_id)
            if consulta is None or int(consulta["paciente_id"]) != paciente_id:
                raise ErrorEntrada(
                    "Esa consulta no es de este paciente. Actualizá la pantalla "
                    "y volvé a elegirla."
                )

        # ---- de dónde sale el archivo, y su identidad
        temporal: Path | None = None
        if subido is not None:
            extension = Path(subido.filename or "").suffix.lower()
            if extension not in EXTENSIONES_ANEXO:
                admitidas = ", ".join(e.lstrip(".").upper()
                                      for e in EXTENSIONES_ANEXO)
                cual = extension.lstrip(".").upper() or "sin extensión"
                raise ErrorEntrada(
                    f"Un archivo {cual} no se puede anexar. Se aceptan: "
                    f"{admitidas}."
                )
            crudo = subido.read(MAX_BYTES_ANEXO + 1)
            if not crudo:
                raise ErrorEntrada(
                    "El archivo llegó vacío. Volvé a elegirlo y probá de nuevo."
                )
            if len(crudo) > MAX_BYTES_ANEXO:
                raise ErrorEntrada(
                    "El archivo pesa más de 30 MB. Mandá la imagen sola, no el "
                    "video ni el estudio completo."
                )
            temporal = Path(tempfile.mkdtemp(prefix="recipes-anexo-")) / f"origen{extension}"
            temporal.write_bytes(crudo)
            origen = temporal
            nombre_origen = basedatos.limpiar(subido.filename)
        else:
            encontrado = bandeja.resolver(basedatos.limpiar(cuerpo.get("token")))
            origen = encontrado[0] if encontrado else None
            if origen is None or not ruta_de_bandeja_valida(
                    app.config["DIR_DATOS"], origen):
                raise _NoEncontrado(
                    "Esa imagen ya no está en la bandeja. Actualizá la bandeja "
                    "y volvé a elegirla."
                )
            extension = origen.suffix.lower()
            nombre_origen = str(origen)

        try:
            # Un `.jpg` que adentro no es una imagen (una descarga cortada a la
            # mitad, un archivo renombrado) se frena acá y no después: si se
            # copiara, la historia quedaría con un anexo que no se puede ver ni
            # imprimir, con miniatura rota y sin medidas. El PDF no pasa por
            # esto —no es una imagen y nadie espera que lo sea (dec. 11)—.
            if extension in EXTENSIONES_BANDEJA and dimensiones_imagen(origen) is None:
                raise ErrorEntrada(
                    "Ese archivo dice ser una imagen pero no se puede abrir "
                    "como tal. Puede estar a medio descargar o dañado: "
                    "descargalo de nuevo de WhatsApp y volvé a intentar."
                )

            sha = sha256_de(origen)
            repetido = basedatos.obtener_anexo_por_sha256(conexion, sha)
            if repetido is not None:
                dueno = basedatos.obtener_paciente(
                    conexion, int(repetido["paciente_id"]))
                de_quien = (f"{basedatos.limpiar(dueno['nombre'])} "
                            f"({basedatos.limpiar(dueno['codigo'])})"
                            if dueno is not None else "otro paciente")
                raise _YaEstaba(
                    f"Esa imagen ya está anexada a la historia de {de_quien}, "
                    f"con fecha {str(repetido['fecha_medicion'])[:10]}. Si es "
                    "otra medición, descargala de nuevo de WhatsApp; si no, ya "
                    "la tenés guardada."
                )

            with basedatos.transaccion(conexion, inmediata=True):
                codigo = codigos.asegurar_codigo_paciente(conexion, paciente_id)
            nombre = basedatos.limpiar(paciente["nombre"])
            carpeta = carpeta_paciente(app.config["DIR_DATOS"], codigo, nombre) / "anexos"
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = nombre_anexo_libre(carpeta, fecha, tipo, extension)

            try:
                copiar_anexo(origen, destino, sha)
            except OSError as err:
                return jsonify({"error": (
                    f"No se pudo guardar la imagen en la carpeta de {nombre}. "
                    f"El archivo original quedó donde estaba. ({err})"
                )}), 500

            escribir_miniatura(destino)
            medidas = dimensiones_imagen(destino)
            relativa = destino.relative_to(app.config["DIR_DATOS"]).as_posix()

            try:
                with basedatos.transaccion(conexion, inmediata=True):
                    anexo_id = basedatos.crear_anexo(
                        conexion, paciente_id, relativa, sha, fecha, tipo,
                        consulta_id=consulta_id, nota=nota,
                        ancho_px=medidas[0] if medidas else None,
                        alto_px=medidas[1] if medidas else None,
                        bytes=destino.stat().st_size,
                        origen=nombre_origen[:MAX_TEXTO_CORTO],
                    )
                    medicion_id = (basedatos.crear_medicion(
                        conexion, paciente_id, fecha=fecha,
                        anexo_id=anexo_id, **medicion) if medicion else None)
            except sqlite3.IntegrityError:
                # Alguien anexó la misma imagen entre el chequeo y el INSERT.
                # La copia recién hecha sobra: se saca para no dejar basura.
                for sobra in (destino,
                              destino.with_name(destino.stem + SUFIJO_MINIATURA)):
                    try:
                        sobra.unlink()
                    except OSError:
                        pass
                raise _YaEstaba(
                    "Esa imagen ya está anexada a una historia. Actualizá la "
                    "pantalla para verla."
                ) from None
        finally:
            if temporal is not None:
                shutil.rmtree(temporal.parent, ignore_errors=True)

        respuesta = _json_anexo(basedatos.obtener_anexo(conexion, anexo_id))
        respuesta["medicion"] = (basedatos.a_dict(
            basedatos.obtener_medicion(conexion, medicion_id))
            if medicion_id else None)
        return jsonify(respuesta), 201

    @app.get("/api/anexos/<int:anexo_id>/imagen")
    def ver_anexo(anexo_id: int):
        """El archivo del anexo, tal cual se copió (Parte C §5).

        Se lee a memoria y se manda desde ahí por lo mismo que el PDF del
        Historial: con la ruta, Windows deja el archivo tomado y el médico no
        podría moverlo ni respaldar la carpeta con la aplicación abierta.
        """
        fila = _anexo_o_404(anexo_id)
        ruta = _archivo_de_anexo(fila)
        try:
            contenido = ruta.read_bytes()
        except OSError as err:
            raise _NoEncontrado(
                f"No se pudo leer el anexo. ({err})"
            ) from err
        return send_file(
            io.BytesIO(contenido),
            mimetype=MIME_ANEXO.get(ruta.suffix.lower(), "application/octet-stream"),
            as_attachment=False, download_name=ruta.name, max_age=0,
        )

    @app.get("/api/anexos/<int:anexo_id>/miniatura")
    def ver_miniatura_anexo(anexo_id: int):
        """La miniatura del anexo: la de al lado, o una hecha en el momento.

        La grilla de la historia carga esto y no el original: son 400 px contra
        una foto entera, y con veinte anexos la diferencia se nota. Si la
        miniatura no está (un anexo de una versión anterior, o un borrado a
        mano en el Explorador) se rehace y se deja escrita.
        """
        fila = _anexo_o_404(anexo_id)
        ruta = _archivo_de_anexo(fila)
        al_lado = ruta.with_name(ruta.stem + SUFIJO_MINIATURA)
        if al_lado.is_file():
            try:
                return send_file(
                    io.BytesIO(al_lado.read_bytes()), mimetype="image/jpeg",
                    as_attachment=False, download_name=al_lado.name, max_age=0,
                )
            except OSError:
                pass  # se rehace abajo
        try:
            contenido = miniatura_jpeg(ruta)
        except Exception as err:
            raise _NoEncontrado(
                "Ese anexo no se puede mostrar como imagen (un PDF, por "
                f"ejemplo). Abrilo con el botón de abrir. ({type(err).__name__})"
            ) from err
        try:
            al_lado.write_bytes(contenido)
        except OSError:
            pass  # servirla vale; guardarla es solo para la próxima vez
        return send_file(
            io.BytesIO(contenido), mimetype="image/jpeg",
            as_attachment=False, download_name=al_lado.name, max_age=0,
        )

    @app.post("/api/anexos/<int:anexo_id>/abrir")
    def abrir_anexo(anexo_id: int):
        """Abre el anexo con el visor de Windows (Parte C §5).

        Es el botón «Abrir con el visor de Windows» del visor de la historia:
        sirve para imprimir la medición sola, y es el único camino para un PDF
        de laboratorio, que en pantalla no se puede mostrar como imagen.
        """
        fila = _anexo_o_404(anexo_id)
        ruta = _archivo_de_anexo(fila)
        if not abrir_con_el_sistema(ruta) and not _abrir_desactivado():
            return jsonify({"error": (
                "No se pudo abrir el anexo con el visor de Windows. Abrilo a "
                f"mano desde: {ruta}"
            )}), 500
        return jsonify({"ok": True})

    # ------------------------------------------------------------ evolución
    @app.get("/api/pacientes/<int:paciente_id>/evolucion")
    def ver_evolucion(paciente_id: int):
        """Las series para el gráfico de evolución (dec. 13).

        Se combinan las dos fuentes que tiene el paciente: los valores clave
        que el médico tipeó al anexar la medición (tabla `mediciones`) y el
        peso y el IMC que quedaron en los signos vitales de cada consulta. Cada
        punto viaja **rotulado con su fuente**, porque no son lo mismo: una es
        la báscula de bioimpedancia del paciente y la otra la balanza del
        consultorio, y ver por qué dos puntos del mismo día no coinciden tiene
        que ser posible sin abrir la base.
        """
        conexion = con()
        _paciente_o_404(paciente_id)
        return jsonify({"series": series_evolucion(conexion, paciente_id)})

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

        Antes de leer se precargan los datos de fábrica del médico (dec. 9) que
        estén vacíos, así la pantalla los muestra ya escritos y el médico ve
        exactamente lo que va a salir impreso en el informe.
        """
        precargar_datos_medico(conexion)
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

        Con ``{"carpeta": "entrada"}`` abre en cambio la carpeta donde soltar
        las mediciones. Es el botón «Abrir carpeta de entrada» de la pantalla
        de la historia, y es lo que cubre el hueco cuando no se pudo crear el
        acceso directo del Escritorio (PowerShell restringido, por ejemplo).
        """
        cuerpo = request.get_json(silent=True)
        cual = basedatos.limpiar(
            cuerpo.get("carpeta") if isinstance(cuerpo, dict) else "").lower()
        if cual == DIR_ENTRADA:
            destino = _dir_entrada()
        else:
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
