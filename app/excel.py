# -*- coding: utf-8 -*-
"""Registro Excel de los récipes (§9).

El Excel **es salida, nunca fuente** (§13): este módulo lo reconstruye entero
desde SQLite cada vez que se lo llama. Nada de leerlo, nada de actualizarlo
fila por fila; si el archivo se pierde o se corrompe, se regenera y queda
igual que antes, porque la verdad vive en `recipes.db`.

Dos hojas (§9):

- **Récipes** — código, fecha, paciente, cédula, edad, diagnóstico, cantidad
  de medicamentos, estado (Emitido/Anulado), motivo de la anulación y ruta
  del PDF.
- **Medicamentos** — una fila por renglón recetado: código, fecha, paciente,
  medicamento, presentación, cantidad, dosis e indicaciones.

Dos cosas que este módulo se toma en serio:

1. **Escritura atómica.** Se escribe un archivo temporal en la misma carpeta
   y recién al final se lo renombra encima del bueno con `os.replace`, que es
   atómico. Un corte de luz a mitad de la escritura deja el registro anterior
   intacto en vez de un `.xlsx` corrupto que Excel no abre.
2. **Excel abierto = aviso, no drama.** Si el médico tiene el registro abierto
   se levanta `RegistroBloqueadoError` con el mensaje de §7 y quien llama
   decide qué hacer. El récipe ya se guardó y el PDF ya se generó: que un
   Excel abierto nunca impida emitir (§9).
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

try:  # como paquete (``from app import excel``)
    from . import basedatos
except ImportError:  # con ``app/`` en el sys.path (tests, scripts)
    import basedatos  # type: ignore[no-redef]

try:  # solo en Windows; sirve para detectar el bloqueo antes de escribir
    import msvcrt
except ImportError:  # pragma: no cover - la app corre en Windows
    msvcrt = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

#: Nombre del archivo dentro de ``<carpeta de datos>\registro\`` (§4).
NOMBRE_ARCHIVO = "registro_recipes.xlsx"

HOJA_RECIPES = "Récipes"
HOJA_MEDICAMENTOS = "Medicamentos"

#: Mensaje de §7: dice qué hacer, no qué falló.
MENSAJE_BLOQUEADO = "El registro está abierto en Excel. Cerralo y volvé a intentar."

ESTADO_EMITIDO = "Emitido"
ESTADO_ANULADO = "Anulado"

#: (encabezado, ancho de columna). El ancho es en "caracteres" de Excel.
COLUMNAS_RECIPES: tuple[tuple[str, int], ...] = (
    ("Código", 16),
    ("Fecha", 12),
    ("Paciente", 30),
    ("Cédula", 14),
    ("Edad", 7),
    ("Diagnóstico", 34),
    ("Medicamentos", 14),
    ("Estado", 11),
    ("Motivo de la anulación", 34),
    ("Ruta del PDF", 60),
)

COLUMNAS_MEDICAMENTOS: tuple[tuple[str, int], ...] = (
    ("Código", 16),
    ("Fecha", 12),
    ("Paciente", 30),
    ("Medicamento", 28),
    ("Presentación", 18),
    ("Cantidad", 14),
    ("Dosis", 30),
    ("Indicaciones", 40),
)

_FUENTE_ENCABEZADO = Font(bold=True, color="FFFFFFFF")
_RELLENO_ENCABEZADO = PatternFill("solid", fgColor="FF157F6F")  # --teal
_ALINEACION_ENCABEZADO = Alignment(vertical="center")
#: Los anulados se leen de un vistazo: gris y tachados, igual que en el
#: Historial de la interfaz (§7-B).
_FUENTE_ANULADO = Font(color="FF808080", strike=True)

#: Caracteres de control que openpyxl rechaza (IllegalCharacterError).
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


# --------------------------------------------------------------------------
# Errores
# --------------------------------------------------------------------------

class RegistroBloqueadoError(OSError):
    """El archivo del registro no se puede reemplazar: está abierto en Excel.

    Hereda de `OSError` porque eso es lo que pasó a bajo nivel, pero el texto
    ya viene escrito para el médico. Quien llama decide: al guardar un récipe
    se avisa y se sigue (§9), en el botón manual se muestra el mensaje.
    """

    def __init__(self, mensaje: str = MENSAJE_BLOQUEADO, ruta: Path | None = None):
        super().__init__(mensaje)
        self.ruta = ruta


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def ruta_registro(dir_datos: str | os.PathLike[str]) -> Path:
    """``<dir_datos>\\registro\\registro_recipes.xlsx`` (§4)."""
    return Path(dir_datos) / "registro" / NOMBRE_ARCHIVO


def _texto(valor: Any) -> str:
    """Texto listo para una celda: sin `None` y sin caracteres de control."""
    if valor is None:
        return ""
    return _CONTROL.sub(" ", str(valor))


def _fecha(valor: Any) -> str:
    """Fecha en ``AAAA-MM-DD``.

    Se guarda como texto ISO a propósito: ordena y filtra bien en cualquier
    configuración regional de Windows, y no se transforma sola en un número
    de serie cuando el médico abre el archivo en otra máquina.
    """
    return _texto(valor)[:10]


def _dato(fila: Any, clave: str, por_defecto: Any = None) -> Any:
    """Lee una clave de un `sqlite3.Row` o de un dict, sin romperse si falta."""
    try:
        return fila[clave]
    except (KeyError, IndexError):
        return por_defecto


# --------------------------------------------------------------------------
# Armado del libro
# --------------------------------------------------------------------------

def _preparar_hoja(hoja, columnas: Sequence[tuple[str, int]]) -> None:
    """Encabezados fijos en negrita, anchos y filtro automático (§9)."""
    hoja.append([nombre for nombre, _ in columnas])
    for indice, (_, ancho) in enumerate(columnas, start=1):
        celda = hoja.cell(row=1, column=indice)
        celda.font = _FUENTE_ENCABEZADO
        celda.fill = _RELLENO_ENCABEZADO
        celda.alignment = _ALINEACION_ENCABEZADO
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    # "Fijos" en los dos sentidos: se ven siempre al bajar (freeze_panes) y
    # traen el desplegable de filtro (auto_filter).
    hoja.freeze_panes = "A2"


def _cerrar_hoja(hoja, columnas: Sequence[tuple[str, int]], filas: int) -> None:
    """Extiende el filtro automático a todo lo escrito."""
    ultima = get_column_letter(len(columnas))
    hoja.auto_filter.ref = f"A1:{ultima}{max(filas, 1) + 1}"


def _escribir_fila(hoja, valores: Iterable[Any], anulado: bool) -> None:
    hoja.append(list(valores))
    if anulado:
        for celda in hoja[hoja.max_row]:
            celda.font = _FUENTE_ANULADO


def _armar_libro(con: sqlite3.Connection) -> Workbook:
    """Construye el libro completo leyendo SQLite. No toca el disco."""
    libro = Workbook()

    hoja_r = libro.active
    hoja_r.title = HOJA_RECIPES
    _preparar_hoja(hoja_r, COLUMNAS_RECIPES)

    recipes = basedatos.listar_recipes(con)
    for fila in recipes:
        anulado = bool(_dato(fila, "anulado", 0))
        _escribir_fila(hoja_r, (
            _texto(_dato(fila, "codigo")),
            _fecha(_dato(fila, "fecha_emision")),
            _texto(_dato(fila, "paciente_nombre")),
            _texto(_dato(fila, "paciente_cedula")),
            _dato(fila, "paciente_edad"),
            _texto(_dato(fila, "diagnostico")),
            int(_dato(fila, "cantidad_items", 0) or 0),
            ESTADO_ANULADO if anulado else ESTADO_EMITIDO,
            _texto(_dato(fila, "motivo_anulacion")),
            _texto(_dato(fila, "ruta_pdf")),
        ), anulado)
    _cerrar_hoja(hoja_r, COLUMNAS_RECIPES, len(recipes))

    hoja_m = libro.create_sheet(HOJA_MEDICAMENTOS)
    _preparar_hoja(hoja_m, COLUMNAS_MEDICAMENTOS)

    items = basedatos.listar_items_todos(con)
    for fila in items:
        anulado = bool(_dato(fila, "anulado", 0))
        _escribir_fila(hoja_m, (
            _texto(_dato(fila, "codigo")),
            _fecha(_dato(fila, "fecha_emision")),
            _texto(_dato(fila, "paciente_nombre")),
            _texto(_dato(fila, "medicamento")),
            _texto(_dato(fila, "presentacion")),
            _texto(_dato(fila, "cantidad")),
            _texto(_dato(fila, "dosis")),
            _texto(_dato(fila, "indicaciones")),
        ), anulado)
    _cerrar_hoja(hoja_m, COLUMNAS_MEDICAMENTOS, len(items))

    return libro


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------

def _ruta_temporal(destino: Path) -> Path:
    """Temporal en la MISMA carpeta que el destino.

    Tiene que ser el mismo volumen para que `os.replace` sea un renombrado
    atómico y no una copia. Lleva el PID por si dos procesos regeneran a la
    vez: cada uno escribe su temporal y gana el último en renombrar, pero
    ninguno ve el archivo a medio escribir del otro.
    """
    return destino.with_name(f"~{destino.stem}-{os.getpid()}.tmp")


def _verificar_desbloqueado(destino: Path) -> None:
    """Avisa temprano si el registro está tomado por otro programa.

    No es imprescindible —`os.replace` también falla contra un archivo
    abierto en Windows— pero evita armar el libro entero para nada y detecta
    además el bloqueo por rango de bytes, que es el que usa Excel mientras
    edita. Ante cualquier duda deja pasar: el chequeo de verdad es el
    renombrado final.
    """
    if not destino.exists():
        return
    try:
        descriptor = os.open(destino, os.O_RDWR | getattr(os, "O_BINARY", 0))
    except PermissionError as err:
        raise RegistroBloqueadoError(MENSAJE_BLOQUEADO, destino) from err
    except OSError:
        return
    try:
        if msvcrt is not None:
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as err:
                raise RegistroBloqueadoError(MENSAJE_BLOQUEADO, destino) from err
            try:
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
    finally:
        os.close(descriptor)


def regenerar_registro(con: sqlite3.Connection,
                       ruta_xlsx: str | os.PathLike[str]) -> Path:
    """Reconstruye el registro completo desde SQLite y lo deja escrito (§9).

    Devuelve la ruta escrita. Levanta `RegistroBloqueadoError` si el médico
    tiene el archivo abierto en Excel — en ese caso el archivo anterior queda
    tal cual estaba y no se deja ningún temporal dando vueltas.
    """
    destino = Path(ruta_xlsx)
    destino.parent.mkdir(parents=True, exist_ok=True)

    _verificar_desbloqueado(destino)

    libro = _armar_libro(con)
    temporal = _ruta_temporal(destino)
    try:
        libro.save(temporal)
        try:
            os.replace(temporal, destino)
        except OSError as err:
            # En Windows cualquier handle abierto sobre el destino hace
            # fallar el renombrado: eso es exactamente "lo tiene abierto".
            raise RegistroBloqueadoError(MENSAJE_BLOQUEADO, destino) from err
    finally:
        libro.close()
        if temporal.exists():
            try:
                temporal.unlink()
            except OSError:
                pass
    return destino


def regenerar_en(con: sqlite3.Connection,
                 dir_datos: str | os.PathLike[str]) -> Path:
    """Atajo: regenera ``<dir_datos>\\registro\\registro_recipes.xlsx``."""
    return regenerar_registro(con, ruta_registro(dir_datos))
