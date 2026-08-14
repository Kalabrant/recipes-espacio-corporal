"""Generación del código único del récipe (§6 de las instrucciones).

Formato: ``EC-2026-0001`` — prefijo configurable, año de emisión y secuencial
de cuatro dígitos con ceros a la izquierda.

Reglas que este módulo garantiza y que no hay que romper:

1. El secuencial **reinicia en 0001 cada año**. Lo determina el año de la
   fecha de emisión, no un contador corrido (§6.1).
2. Se asigna **al guardar**, dentro de una transacción ``BEGIN IMMEDIATE``
   que lee y actualiza ``contador_anual`` en la misma operación que inserta
   el récipe. Un formulario abandonado no quema un número, y dos ventanas
   abiertas no pueden sacar el mismo código (§6.2 y §6.3).
3. Los números **no se reciclan**: un récipe anulado conserva su código y ese
   código no se vuelve a emitir. El contador nunca baja, y además se toma el
   máximo contra los récipes ya emitidos, así que ni siquiera un contador
   perdido o pisado puede devolver un número usado (§6.4).
4. **Desborde:** pasado 9999 se sigue con cinco dígitos (``EC-2026-10000``)
   en vez de romper el formato o detenerse (§6.5).
5. El prefijo vive en ``config`` con ``EC`` por defecto. Al cambiarlo, los
   récipes ya emitidos conservan el prefijo con el que salieron, porque el
   código se guarda literal en la fila del récipe (§6.6).

Esta es la pieza que no puede fallar: sus tests están en
``tests/test_codigos.py``.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import AbstractContextManager, nullcontext
from datetime import date, datetime
from typing import Any, Iterable, Mapping

try:  # como paquete (``from app import codigos``)
    from . import basedatos
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import basedatos  # type: ignore[no-redef]


# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

#: Clave de `config` donde vive el prefijo editable desde Configuración (§6.6).
CLAVE_PREFIJO = "prefijo_codigo"

#: Prefijo por defecto: EC, de "Espacio Corporal" (§6).
PREFIJO_POR_DEFECTO = "EC"

#: Ancho mínimo del secuencial. Pasado 9999 crece solo a cinco dígitos (§6.5).
ANCHO_SECUENCIAL = 4

#: Último secuencial que entra en el ancho clásico. Solo informativo.
SECUENCIAL_MAXIMO_CLASICO = 10 ** ANCHO_SECUENCIAL - 1  # 9999

_RE_PREFIJO = re.compile(r"^[A-Za-z0-9]{1,10}$")

#: `EC-2026-0001`, y también `EC-2026-10000` cuando un año desborda.
_RE_CODIGO = re.compile(r"^(?P<prefijo>[A-Za-z0-9]{1,10})-(?P<anio>\d{4})-(?P<secuencial>\d{4,})$")

_RE_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


# --------------------------------------------------------------------------
# Prefijo
# --------------------------------------------------------------------------

def validar_prefijo(prefijo: str | None) -> str:
    """Devuelve el prefijo normalizado en mayúsculas, o falla con un mensaje claro.

    Se aceptan de una a diez letras o números. El guion queda excluido a
    propósito: es el separador del código y admitirlo haría ambiguo el
    formato ``PREFIJO-AÑO-SECUENCIAL``.
    """
    limpio = basedatos.limpiar(prefijo)
    if not limpio:
        raise ValueError("El prefijo del código no puede quedar vacío. Poné al menos una letra.")
    limpio = limpio.replace(" ", "")
    if not _RE_PREFIJO.match(limpio):
        raise ValueError(
            "El prefijo del código admite solo letras y números, de 1 a 10 caracteres "
            f"(sin espacios ni guiones). Recibí: {prefijo!r}"
        )
    return limpio.upper()


def obtener_prefijo(con: sqlite3.Connection) -> str:
    """Prefijo vigente según `config`. `EC` si nunca se configuró (§6.6).

    Si lo guardado quedara inservible (una base tocada a mano), se vuelve al
    valor por defecto en vez de impedir que el médico emita.
    """
    guardado = basedatos.obtener_config(con, CLAVE_PREFIJO, None)
    try:
        return validar_prefijo(guardado)
    except ValueError:
        return PREFIJO_POR_DEFECTO


def guardar_prefijo(con: sqlite3.Connection, prefijo: str) -> str:
    """Guarda el prefijo para los récipes futuros y devuelve cómo quedó.

    Los récipes ya emitidos no se tocan: su código está guardado literal (§6.6).
    """
    validado = validar_prefijo(prefijo)
    basedatos.guardar_config(con, CLAVE_PREFIJO, validado)
    return validado


# --------------------------------------------------------------------------
# Formato del código
# --------------------------------------------------------------------------

def formatear_secuencial(secuencial: int) -> str:
    """`1` → `0001`, `42` → `0042`, `1234` → `1234`, `10000` → `10000` (§6.5)."""
    numero = int(secuencial)
    if numero < 1:
        raise ValueError(f"El secuencial arranca en 1; recibí {secuencial!r}.")
    return f"{numero:0{ANCHO_SECUENCIAL}d}"


def formatear_codigo(prefijo: str, anio: int, secuencial: int) -> str:
    """Arma `EC-2026-0001` a partir de sus tres partes."""
    anio = int(anio)
    if not 1000 <= anio <= 9999:
        raise ValueError(f"El año del código tiene que tener cuatro dígitos; recibí {anio!r}.")
    return f"{validar_prefijo(prefijo)}-{anio:04d}-{formatear_secuencial(secuencial)}"


def partir_codigo(codigo: str) -> tuple[str, int, int]:
    """`"EC-2026-0042"` → `("EC", 2026, 42)`. Falla si el formato no cierra."""
    texto = basedatos.limpiar(codigo)
    encontrado = _RE_CODIGO.match(texto)
    if encontrado is None:
        raise ValueError(f"El código {codigo!r} no tiene el formato PREFIJO-AÑO-SECUENCIAL.")
    return (
        encontrado["prefijo"].upper(),
        int(encontrado["anio"]),
        int(encontrado["secuencial"]),
    )


# --------------------------------------------------------------------------
# Fechas
# --------------------------------------------------------------------------

def normalizar_fecha(fecha: str | date | datetime | None = None) -> str:
    """Deja la fecha de emisión en ISO 8601 y devuelve el texto que se guarda.

    Sin argumento usa el momento actual. Acepta `date`, `datetime` o un texto
    que empiece con `AAAA-MM-DD`; cualquier otra cosa falla temprano, porque
    de esta fecha sale el año del código.
    """
    if fecha is None:
        return basedatos.ahora_iso()
    if isinstance(fecha, datetime):
        return fecha.isoformat(timespec="seconds")
    if isinstance(fecha, date):
        return fecha.isoformat()
    texto = basedatos.limpiar(fecha)
    if not _RE_FECHA_ISO.match(texto):
        raise ValueError(
            f"La fecha de emisión tiene que estar en formato AAAA-MM-DD; recibí {fecha!r}."
        )
    # Que los dígitos formen una fecha real (no 2026-13-40).
    date.fromisoformat(texto[:10])
    return texto


def anio_de(fecha: str | date | datetime | None = None) -> int:
    """Año de emisión, que es el que manda sobre el secuencial (§6.1)."""
    return int(normalizar_fecha(fecha)[:4])


# --------------------------------------------------------------------------
# Asignación del secuencial
# --------------------------------------------------------------------------

def _ultimo_secuencial_real(con: sqlite3.Connection, anio: int) -> int:
    """El mayor secuencial que ese año realmente usó.

    Se mira el contador y también los récipes emitidos, y se toma el mayor de
    los dos. El contador solo sube, pero comparar contra la tabla `recipes`
    es el cinturón de seguridad de §6.4: aunque una base restaurada a medias
    trajera el contador atrasado, jamás se devuelve un número ya emitido.
    Los récipes anulados siguen contando: su número queda quemado.
    """
    fila = con.execute(
        "SELECT MAX(secuencial) AS maximo FROM recipes WHERE anio = ?", (anio,)
    ).fetchone()
    emitido = int(fila["maximo"] or 0) if fila is not None else 0
    return max(basedatos.obtener_ultimo_secuencial(con, anio), emitido)


def proximo_secuencial(con: sqlite3.Connection, anio: int | None = None) -> int:
    """Qué número saldría ahora, **sin reservarlo**.

    Sirve para mostrar una vista previa. No quema el número: la reserva pasa
    solo dentro de `asignar_codigo`, al guardar (§6.2).
    """
    anio = int(anio) if anio is not None else anio_de()
    return _ultimo_secuencial_real(con, anio) + 1


def proximo_codigo(con: sqlite3.Connection, anio: int | None = None, prefijo: str | None = None) -> str:
    """El código que saldría ahora, **sin reservarlo**. Para la vista previa."""
    anio = int(anio) if anio is not None else anio_de()
    prefijo = validar_prefijo(prefijo) if prefijo else obtener_prefijo(con)
    return formatear_codigo(prefijo, anio, proximo_secuencial(con, anio))


def asignar_codigo(
    con: sqlite3.Connection, anio: int | None = None, prefijo: str | None = None
) -> tuple[int, str]:
    """Reserva el próximo secuencial del año y devuelve `(secuencial, codigo)`.

    **Tiene que llamarse con una transacción `BEGIN IMMEDIATE` ya abierta**
    (`basedatos.transaccion(con, inmediata=True)`) y en la misma transacción
    que inserta el récipe. Ese lock de escritura tomado desde el arranque es
    lo que hace imposible que dos ventanas lean el mismo contador (§6.3); por
    eso se rechaza el llamado suelto en vez de abrir la transacción acá.
    """
    if not con.in_transaction:
        raise RuntimeError(
            "asignar_codigo() necesita una transacción abierta con "
            "basedatos.transaccion(con, inmediata=True): el código se reserva y "
            "el récipe se inserta en la misma operación."
        )
    anio = int(anio) if anio is not None else anio_de()
    prefijo = validar_prefijo(prefijo) if prefijo else obtener_prefijo(con)

    secuencial = _ultimo_secuencial_real(con, anio) + 1
    momento = basedatos.ahora_iso()
    con.execute(
        """
        INSERT INTO contador_anual (anio, ultimo_secuencial, creado_en, actualizado_en)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(anio) DO UPDATE SET
            ultimo_secuencial = excluded.ultimo_secuencial,
            actualizado_en    = excluded.actualizado_en
        """,
        (anio, secuencial, momento, momento),
    )
    return secuencial, formatear_codigo(prefijo, anio, secuencial)


# --------------------------------------------------------------------------
# Alta del récipe
# --------------------------------------------------------------------------

_CLAVES_ITEM = ("medicamento", "presentacion", "cantidad", "dosis", "indicaciones")


def _limpiar_items(items: Iterable[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    """Normaliza los renglones y descarta los que no tienen medicamento.

    El formulario arranca con renglones vacíos: los que el médico no llenó no
    son un error, simplemente no se guardan.
    """
    limpios: list[dict[str, str]] = []
    for item in items or ():
        renglon = {clave: basedatos.limpiar(item.get(clave)) for clave in _CLAVES_ITEM}
        if renglon["medicamento"]:
            limpios.append(renglon)
    return limpios


def _transaccion_si_hace_falta(con: sqlite3.Connection) -> AbstractContextManager[Any]:
    """Abre `BEGIN IMMEDIATE`, salvo que quien llama ya haya abierto la suya.

    Permite que `rutas.py` meta el guardado dentro de una transacción más
    grande. Si lo hace, esa transacción tiene que ser inmediata, porque es de
    donde sale la garantía de §6.3.
    """
    if con.in_transaction:
        return nullcontext(con)
    return basedatos.transaccion(con, inmediata=True)


def crear_recipe(
    con: sqlite3.Connection,
    paciente_id: int,
    items: Iterable[Mapping[str, Any]],
    fecha_emision: str | date | datetime | None = None,
    diagnostico: str | None = None,
    notas: str | None = None,
    indicaciones_generales: str | None = None,
    prefijo: str | None = None,
    aprender: bool = True,
    registrar_paciente: bool = True,
) -> dict[str, Any]:
    """Guarda un récipe completo y devuelve su fila como dict (con `codigo`).

    Todo pasa dentro de una sola transacción `BEGIN IMMEDIATE` (§6.3): se
    reserva el secuencial del año, se inserta el encabezado, se copian los
    renglones **literales** (§5), se suma la atención del paciente y se
    aprenden los términos para el autocompletado (§8). Si algo falla, no
    queda ni el récipe ni el número quemado.

    `items` es una lista de diccionarios con las claves `medicamento`,
    `presentacion`, `cantidad`, `dosis` e `indicaciones`. Hace falta al menos
    un renglón con medicamento (§7-A).

    `indicaciones_generales` es opcional: es el texto libre del récipe entero
    que va en la mitad `Ind.` del modelo, aparte de las indicaciones de cada
    medicamento. Sin él, el récipe se guarda igual y la columna queda en NULL.
    """
    renglones = _limpiar_items(items)
    if not renglones:
        raise ValueError("El récipe necesita al menos un medicamento.")

    fecha = normalizar_fecha(fecha_emision)
    anio = int(fecha[:4])
    diagnostico = basedatos.limpiar(diagnostico)
    notas = basedatos.limpiar(notas)
    # Multilínea: es texto libre y cada renglón es una instrucción aparte.
    indicaciones_generales = basedatos.limpiar_multilinea(indicaciones_generales)

    with _transaccion_si_hace_falta(con):
        secuencial, codigo = asignar_codigo(con, anio, prefijo)
        momento = basedatos.ahora_iso()
        cur = con.execute(
            """
            INSERT INTO recipes (codigo, anio, secuencial, paciente_id, fecha_emision,
                                 diagnostico, notas, indicaciones_generales,
                                 ruta_pdf, anulado,
                                 motivo_anulacion, fecha_anulacion,
                                 creado_en, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL, ?, ?)
            """,
            (
                codigo, anio, secuencial, paciente_id, fecha,
                diagnostico or None, notas or None,
                indicaciones_generales or None, momento, momento,
            ),
        )
        recipe_id = int(cur.lastrowid)

        for orden, renglon in enumerate(renglones, start=1):
            basedatos.insertar_recipe_item(
                con, recipe_id, orden,
                medicamento=renglon["medicamento"],
                presentacion=renglon["presentacion"],
                cantidad=renglon["cantidad"],
                dosis=renglon["dosis"],
                indicaciones=renglon["indicaciones"],
            )

        if registrar_paciente:
            basedatos.registrar_atencion(con, paciente_id, momento)
        if aprender:
            basedatos.aprender_terminos(con, diagnostico, renglones, momento)

    fila = basedatos.obtener_recipe(con, recipe_id)
    return dict(fila) if fila is not None else {}
