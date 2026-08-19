# -*- coding: utf-8 -*-
"""Respaldos de la carpeta del médico (§10).

Un ZIP con ``datos\\``, ``registro\\`` y ``pacientes\\`` adentro, guardado en
``respaldos\\``, al primer arranque de cada semana y también a pedido desde
Configuración. Se conservan los últimos 8.

Tres decisiones que valen la pena explicar:

1. **La base se copia con `sqlite3.Connection.backup`, no con `shutil`.**
   La base corre en modo WAL: parte de lo escrito recién vive en
   ``recipes.db-wal`` hasta el próximo checkpoint. Copiar el ``.db`` a secas
   daría un archivo viejo o directamente inconsistente. `backup` produce un
   archivo entero y consistente aunque haya escrituras en curso, y por eso el
   ZIP no incluye los ``-wal`` ni los ``-shm``: ya no hacen falta.
2. **El ZIP se escribe con nombre temporal y recién al final se renombra.**
   Un corte a mitad de camino deja un ``.tmp`` que nadie va a confundir con
   un respaldo bueno, en vez de un ZIP truncado con nombre de respaldo.
3. **Al podar respaldos viejos se borra solo lo que matchea el patrón.**
   El médico guarda cosas donde quiere; si dejó un ``notas.txt`` o un
   ``respaldo-manual.rar`` en esa carpeta, no se toca. Y se borra únicamente
   dentro de ``respaldos\\``: nunca datos, nunca PDF (§2.4).
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:  # como paquete (``from app import respaldo``)
    from . import basedatos
except ImportError:  # con ``app/`` en el sys.path (tests, scripts)
    import basedatos  # type: ignore[no-redef]


# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

#: Subcarpeta donde viven los ZIP (§4).
DIR_RESPALDOS = "respaldos"

#: Qué entra en el respaldo: la base, el registro Excel y la carpeta de los
#: pacientes (§10 y dec. 17).
#:
#: `datos\` es lo irreemplazable. `pacientes\` entra **entera** desde la 2.0
#: porque adentro hay cosas que la base no puede reconstruir: los anexos de
#: WhatsApp (dec. 11) son la única copia que queda de una medición —el original
#: sale del teléfono y se pierde—, y los informes firmados son documentos
#: entregados. Los récipes en PDF sí se podrían regenerar, pero viven en la
#: misma carpeta y separarlos costaría más de lo que ahorra.
#:
#: **Ojo con el tamaño.** Hasta la 1.x el ZIP pesaba unos cientos de KB; con
#: `pacientes\` adentro crece con cada imagen que se anexa (una foto de balanza
#: son ~130 KB, mil anexos ~130 MB) y se conservan ocho respaldos. En el
#: consultorio, con un puñado de anexos por paciente, no molesta. Si algún día
#: molesta, lo que hay que hacer es un respaldo incremental o una casilla
#: "incluir anexos" en Configuración —no sacar la carpeta y quedarse sin copia.
#:
#: Los récipes viejos de `pdf\` siguen fuera del respaldo: se regeneran desde
#: la base y por eso nunca entraron.
CARPETAS_RESPALDADAS = ("datos", "registro", "pacientes")

#: Clave de `config` con la fecha del último respaldo (``AAAA-MM-DD``).
CLAVE_ULTIMO_RESPALDO = "ultimo_respaldo"

#: Nombres que este módulo reconoce como respaldo propio, y los ÚNICOS que
#: `conservar_ultimos` se permite borrar: ``respaldo-2026-08-14.zip`` y sus
#: repeticiones del mismo día ``-2``, ``-3``…
PATRON_RESPALDO = re.compile(
    r"^respaldo-(?P<fecha>\d{4}-\d{2}-\d{2})(?:-(?P<repeticion>\d+))?\.zip$",
    re.IGNORECASE,
)

#: Cuántos respaldos se conservan (§10).
CANTIDAD_CONSERVADA = 8

#: Archivos auxiliares del WAL: no se copian, el `backup` ya los incorporó.
_SUFIJOS_IGNORADOS = ("-wal", "-shm", "-journal")


class RespaldoError(RuntimeError):
    """No se pudo completar el respaldo. El mensaje dice qué hacer (§7)."""


# --------------------------------------------------------------------------
# Nombres y listado
# --------------------------------------------------------------------------

def dir_respaldos(dir_datos: str | os.PathLike[str]) -> Path:
    """``<dir_datos>\\respaldos``, creada si no existía."""
    destino = Path(dir_datos) / DIR_RESPALDOS
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _orden(ruta: Path) -> tuple[str, int]:
    """Clave de orden cronológico: fecha del nombre y repetición del día."""
    coincidencia = PATRON_RESPALDO.match(ruta.name)
    if coincidencia is None:  # no debería pasar: se filtra antes
        return ("", 0)
    return (coincidencia.group("fecha"), int(coincidencia.group("repeticion") or 1))


def listar_respaldos(dir_datos: str | os.PathLike[str]) -> list[Path]:
    """Respaldos existentes, del más viejo al más nuevo.

    Solo los que matchean `PATRON_RESPALDO`: lo demás que haya en la carpeta
    no es asunto de este módulo.
    """
    carpeta = Path(dir_datos) / DIR_RESPALDOS
    if not carpeta.is_dir():
        return []
    propios = [r for r in carpeta.iterdir() if r.is_file() and PATRON_RESPALDO.match(r.name)]
    return sorted(propios, key=_orden)


def ruta_respaldo_nueva(dir_datos: str | os.PathLike[str],
                        dia: date | None = None) -> Path:
    """Ruta libre para el respaldo del día, sin pisar uno existente.

    ``respaldo-2026-08-14.zip`` y, si ya está, ``-2``, ``-3``… (§10). Un
    respaldo nunca se sobrescribe: si el médico respalda dos veces el mismo
    día es porque quiere las dos fotos.

    El número **sigue al más alto que haya del día; no rellena huecos**. Si se
    buscara el primer nombre libre, pasaría esto: con ocho respaldos del mismo
    día (``-2`` a ``-9``), `conservar_ultimos` ya borró el primero, así que
    ``respaldo-2026-08-14.zip`` vuelve a estar libre; el noveno se llamaría
    igual que el original, `_orden` lo leería como el **más viejo del día** y
    la poda de esa misma corrida lo borraría recién creado. El respaldo que el
    médico acaba de pedir sería justo el que desaparece.
    """
    carpeta = dir_respaldos(dir_datos)
    fecha = (dia or date.today()).isoformat()

    usados = [
        _orden(r)[1] for r in listar_respaldos(dir_datos)
        if _orden(r)[0] == fecha
    ]
    if not usados:
        return carpeta / f"respaldo-{fecha}.zip"

    repeticion = max(max(usados), 1) + 1
    candidata = carpeta / f"respaldo-{fecha}-{repeticion}.zip"
    while candidata.exists():  # cinturón: un archivo suelto no bloquea nada
        repeticion += 1
        candidata = carpeta / f"respaldo-{fecha}-{repeticion}.zip"
    return candidata


# --------------------------------------------------------------------------
# Respaldo
# --------------------------------------------------------------------------

def _copia_consistente_db(origen: Path, destino: Path) -> None:
    """Copia una base SQLite viva usando la API de backup (WAL incluido)."""
    con_origen = sqlite3.connect(str(origen), timeout=15.0)
    try:
        con_destino = sqlite3.connect(str(destino))
        try:
            con_origen.backup(con_destino)
        finally:
            con_destino.close()
    finally:
        con_origen.close()


def _archivos_a_guardar(raiz: Path, temporales: Path) -> list[tuple[Path, str]]:
    """Pares ``(archivo en disco, nombre dentro del ZIP)`` de una subcarpeta.

    Las bases SQLite se reemplazan por su copia consistente en `temporales`;
    los archivos auxiliares del WAL se saltean.
    """
    pares: list[tuple[Path, str]] = []
    contador = 0
    for actual in sorted(raiz.rglob("*")):
        if not actual.is_file():
            continue
        relativa = actual.relative_to(raiz.parent).as_posix()
        if actual.suffix.lower() == ".db":
            contador += 1
            copia = temporales / f"{contador}-{actual.name}"
            try:
                _copia_consistente_db(actual, copia)
            except sqlite3.Error as err:
                raise RespaldoError(
                    "No se pudo copiar la base de datos para el respaldo. "
                    f"Cerrá la aplicación y volvé a intentar. ({err})"
                ) from err
            pares.append((copia, relativa))
            continue
        if any(actual.name.endswith(sufijo) for sufijo in _SUFIJOS_IGNORADOS):
            continue
        pares.append((actual, relativa))
    return pares


def respaldar_ahora(dir_datos: str | os.PathLike[str],
                    dia: date | None = None) -> Path:
    """Crea el ZIP del día y devuelve su ruta (§10).

    Adentro van `CARPETAS_RESPALDADAS` con esa misma estructura, así que
    restaurar es descomprimir encima de la carpeta de datos. Una carpeta que
    todavía no existe (``pacientes/`` antes del primer récipe) simplemente no
    aparece. Si ya existe el respaldo de hoy se agrega ``-2``, ``-3``…

    El registro Excel se copia aunque el médico lo tenga abierto: leerlo se
    puede, es escribirlo lo que no (§9).
    """
    raiz = Path(dir_datos)
    if not raiz.is_dir():
        raise RespaldoError(
            f"No encuentro la carpeta de datos ({raiz}). Abrí Configuración y "
            "revisá dónde está guardando la aplicación."
        )
    destino = ruta_respaldo_nueva(raiz, dia)
    temporal = destino.with_name(f"~{destino.stem}.tmp")

    try:
        with tempfile.TemporaryDirectory(prefix="respaldo_") as temporales:
            pares: list[tuple[Path, str]] = []
            for nombre in CARPETAS_RESPALDADAS:
                carpeta = raiz / nombre
                if carpeta.is_dir():
                    pares.extend(_archivos_a_guardar(carpeta, Path(temporales)))
            with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zip_:
                for archivo, nombre_interno in pares:
                    zip_.write(archivo, nombre_interno)
        os.replace(temporal, destino)
    except RespaldoError:
        _borrar_si_esta(temporal)
        raise
    except OSError as err:
        _borrar_si_esta(temporal)
        raise RespaldoError(
            "No se pudo escribir el respaldo. Revisá que haya espacio en el "
            f"disco y volvé a intentar. ({err})"
        ) from err
    return destino


def _borrar_si_esta(ruta: Path) -> None:
    try:
        ruta.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------
# Poda
# --------------------------------------------------------------------------

def conservar_ultimos(dir_datos: str | os.PathLike[str],
                      n: int = CANTIDAD_CONSERVADA) -> list[Path]:
    """Deja los `n` respaldos más nuevos y borra los demás. Devuelve los borrados.

    Borra **solo** dentro de ``respaldos\\`` y **solo** archivos cuyo nombre
    matchee `PATRON_RESPALDO`. Cualquier otra cosa que el médico haya dejado
    ahí queda donde está.
    """
    if n < 0:
        raise ValueError("La cantidad de respaldos a conservar no puede ser negativa.")
    existentes = listar_respaldos(dir_datos)
    sobrantes = existentes[: max(len(existentes) - n, 0)]
    borrados: list[Path] = []
    for viejo in sobrantes:
        # Cinturón y tirantes: se vuelve a verificar el nombre justo antes de
        # borrar. Es la única operación destructiva de toda la app.
        if not PATRON_RESPALDO.match(viejo.name):
            continue
        try:
            viejo.unlink()
            borrados.append(viejo)
        except OSError:
            # Si uno no se deja borrar (antivirus, OneDrive sincronizando),
            # no es motivo para frenar nada: se reintenta la próxima.
            continue
    return borrados


# --------------------------------------------------------------------------
# Respaldo semanal automático
# --------------------------------------------------------------------------

def _a_fecha(texto: str | None) -> date | None:
    """Fecha ISO guardada en `config`, o `None` si está vacía o ilegible."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(str(texto).strip()).date()
    except ValueError:
        try:
            return date.fromisoformat(str(texto).strip()[:10])
        except ValueError:
            return None


def semana_iso(dia: date) -> tuple[int, int]:
    """``(año ISO, semana ISO)``. Es la semana que decide si toca respaldar."""
    partes = dia.isocalendar()
    return (partes[0], partes[1])


def toca_respaldo_semanal(con: sqlite3.Connection,
                          dir_datos: str | os.PathLike[str],
                          hoy: date | None = None,
                          conservar: int = CANTIDAD_CONSERVADA) -> dict[str, Any]:
    """Respalda si esta semana ISO todavía no hubo respaldo (§10).

    Se llama al arrancar. Devuelve qué hizo::

        {"hecho": bool,
         "motivo": "texto llano",
         "archivo": Path | None,
         "eliminados": [Path, ...],
         "semana": "2026-W33",
         "ultimo_respaldo": "AAAA-MM-DD" | None}

    La marca se guarda en `config` recién después de que el ZIP quedó
    escrito: si el respaldo falla, la semana sigue pendiente y el próximo
    arranque lo reintenta.
    """
    hoy = hoy or date.today()
    anio_iso, numero = semana_iso(hoy)
    etiqueta = f"{anio_iso}-W{numero:02d}"

    ultimo_texto = basedatos.obtener_config(con, CLAVE_ULTIMO_RESPALDO)
    ultimo = _a_fecha(ultimo_texto)

    if ultimo is not None and semana_iso(ultimo) == (anio_iso, numero):
        return {
            "hecho": False,
            "motivo": "Ya se respaldó esta semana.",
            "archivo": None,
            "eliminados": [],
            "semana": etiqueta,
            "ultimo_respaldo": ultimo.isoformat(),
        }

    archivo = respaldar_ahora(dir_datos, hoy)
    eliminados = conservar_ultimos(dir_datos, conservar)
    basedatos.guardar_config(con, CLAVE_ULTIMO_RESPALDO, hoy.isoformat())
    return {
        "hecho": True,
        "motivo": "Respaldo de la semana hecho.",
        "archivo": archivo,
        "eliminados": eliminados,
        "semana": etiqueta,
        "ultimo_respaldo": hoy.isoformat(),
    }
