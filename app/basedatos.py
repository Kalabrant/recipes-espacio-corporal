"""Base de datos de la app de récipes médicos.

Un solo archivo SQLite, sin servicio y sin dependencias fuera de la stdlib.
Acá viven el esquema, las migraciones por versión y las consultas que usan
las demás piezas (rutas.py, codigos.py, pdf_recipe.py, excel.py).

Reglas que este módulo respeta y que no hay que romper:
  - Ningún récipe se borra: se anula (§2.4 y §10 de las instrucciones).
  - `recipe_items` guarda copia literal de los textos, nunca referencias (§5).
  - La asignación del código único vive en codigos.py, no acá; este módulo
    solo provee la tabla `contador_anual` y el contexto `transaccion(...)`
    con BEGIN IMMEDIATE para que esa operación sea atómica (§6.3).
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

#: Cantidad máxima de sugerencias del autocompletado (§8).
LIMITE_SUGERENCIAS = 8

#: Tablas de términos globales que aprende la app.
TABLAS_TERMINOS = ("indicaciones", "diagnosticos")

_ESPACIOS = re.compile(r"\s+")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def ahora_iso() -> str:
    """Marca de tiempo local en ISO 8601, con segundos. Formato de toda la BD."""
    return datetime.now().isoformat(timespec="seconds")


def normalizar(texto: str | None) -> str:
    """Baja a minúsculas, saca acentos y colapsa espacios.

    Es la forma en la que se guardan las columnas `*_norm` y en la que se
    normaliza el término buscado, para que la búsqueda sea insensible a
    mayúsculas y acentos (§8). Se descomponen todos los diacríticos, así que
    la ñ pasa a n: buscar "nino" encuentra "Niño", que es lo deseado acá.
    """
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", str(texto))
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return _ESPACIOS.sub(" ", sin_acentos).strip().casefold()


def limpiar(texto: str | None) -> str:
    """Recorta y colapsa espacios conservando mayúsculas y acentos originales."""
    if texto is None:
        return ""
    return _ESPACIOS.sub(" ", str(texto)).strip()


def limpiar_multilinea(texto: str | None) -> str:
    """Como `limpiar`, pero **respeta los saltos de línea** que escribió el médico.

    Es para los textos libres largos —las indicaciones generales del récipe—,
    donde cada renglón es una instrucción aparte y colapsarlos en un párrafo
    corrido cambiaría lo que el paciente lee. Unifica los fines de línea de
    Windows a `\\n`, limpia los espacios de cada renglón y recorta las líneas
    en blanco de los extremos.
    """
    if texto is None:
        return ""
    unificado = str(texto).replace("\r\n", "\n").replace("\r", "\n")
    renglones = [_ESPACIOS.sub(" ", linea).strip() for linea in unificado.split("\n")]
    return "\n".join(renglones).strip("\n")


def _patron_like(termino: str | None) -> str:
    """Arma el patrón `%termino%` escapando los comodines de LIKE."""
    base = normalizar(termino)
    escapado = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def ruta_por_defecto() -> Path:
    """`%USERPROFILE%\\Documents\\Recipes\\datos\\recipes.db` (§4)."""
    base = Path(os.environ.get("USERPROFILE") or Path.home())
    return base / "Documents" / "Recipes" / "datos" / "recipes.db"


# --------------------------------------------------------------------------
# Conexión
# --------------------------------------------------------------------------

def conectar(ruta: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Abre la base con las PRAGMA que necesita la app.

    - `foreign_keys=ON` para que las bajas en cascada y las referencias valgan.
    - `journal_mode=WAL` para que dos ventanas puedan leer mientras una escribe.
    - `busy_timeout` para que la segunda escritura espere en vez de fallar.
    - `isolation_level=None`: autocommit; las transacciones se abren a mano
      con `transaccion(...)`, que es lo que precisa el BEGIN IMMEDIATE de §6.3.

    La ruta es parametrizable; `":memory:"` sirve para los tests.
    """
    destino = Path(ruta) if ruta is not None else ruta_por_defecto()
    if str(destino) != ":memory:":
        destino.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(destino), isolation_level=None, timeout=15.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 15000")
    if str(destino) != ":memory:":
        con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    # Disponible dentro de SQL para buscar sobre columnas sin `*_norm`
    # (por ejemplo los textos literales de recipe_items).
    con.create_function("norm", 1, normalizar, deterministic=True)
    return con


@contextmanager
def transaccion(con: sqlite3.Connection, inmediata: bool = False) -> Iterator[sqlite3.Connection]:
    """Transacción explícita. Con `inmediata=True` toma el lock de escritura ya.

    `BEGIN IMMEDIATE` es lo que evita la condición de carrera del contador
    anual cuando hay dos ventanas abiertas (§6.3).
    """
    con.execute("BEGIN IMMEDIATE" if inmediata else "BEGIN")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


# --------------------------------------------------------------------------
# Esquema y migraciones
# --------------------------------------------------------------------------

# Cada elemento lleva el esquema de la versión N-1 a la N. Para cambiar el
# modelo se agrega un script nuevo al final: nunca se edita uno ya publicado,
# porque las bases del médico ya lo aplicaron. Una base recién creada arranca
# en 0 y las recorre todas en orden, así que el resultado es el mismo que el
# de una base vieja que se va migrando.
#
# Los scripts no llevan BEGIN ni COMMIT: `migrar` los envuelve para que cada
# versión se aplique entera o nada.
MIGRACIONES: list[str] = [
    # -- versión 1: esquema inicial (§5) -----------------------------------
    """
    CREATE TABLE IF NOT EXISTS config (
        clave          TEXT PRIMARY KEY,
        valor          TEXT,
        creado_en      TEXT NOT NULL,
        actualizado_en TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pacientes (
        id                INTEGER PRIMARY KEY,
        nombre            TEXT    NOT NULL,
        nombre_norm       TEXT    NOT NULL,
        cedula            TEXT,
        fecha_nacimiento  TEXT,
        edad              INTEGER,
        sexo              TEXT,
        telefono          TEXT,
        notas             TEXT,
        veces_atendido    INTEGER NOT NULL DEFAULT 0,
        ultima_vez        TEXT,
        creado_en         TEXT    NOT NULL,
        actualizado_en    TEXT    NOT NULL
    );
    -- La cédula es única pero admite vacío: por eso el índice es parcial.
    CREATE UNIQUE INDEX IF NOT EXISTS ix_pacientes_cedula
        ON pacientes(cedula) WHERE cedula IS NOT NULL AND cedula <> '';
    CREATE INDEX IF NOT EXISTS ix_pacientes_busqueda
        ON pacientes(nombre_norm);
    CREATE INDEX IF NOT EXISTS ix_pacientes_orden
        ON pacientes(veces_atendido DESC, ultima_vez DESC);

    CREATE TABLE IF NOT EXISTS medicamentos (
        id                INTEGER PRIMARY KEY,
        nombre            TEXT    NOT NULL,
        nombre_norm       TEXT    NOT NULL,
        presentacion      TEXT    NOT NULL DEFAULT '',
        presentacion_norm TEXT    NOT NULL DEFAULT '',
        veces_usado       INTEGER NOT NULL DEFAULT 0,
        ultima_vez        TEXT,
        creado_en         TEXT    NOT NULL,
        actualizado_en    TEXT    NOT NULL,
        -- Único por (nombre, presentación); se compara normalizado para que
        -- "Amoxicilina" y "amoxicilina " no entren dos veces al catálogo.
        UNIQUE (nombre_norm, presentacion_norm)
    );
    CREATE INDEX IF NOT EXISTS ix_medicamentos_orden
        ON medicamentos(veces_usado DESC, ultima_vez DESC);

    -- La dosis cuelga del medicamento, no es una lista global (§5).
    CREATE TABLE IF NOT EXISTS dosis (
        id             INTEGER PRIMARY KEY,
        medicamento_id INTEGER NOT NULL REFERENCES medicamentos(id) ON DELETE CASCADE,
        texto          TEXT    NOT NULL,
        texto_norm     TEXT    NOT NULL,
        veces_usado    INTEGER NOT NULL DEFAULT 0,
        ultima_vez     TEXT,
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL,
        UNIQUE (medicamento_id, texto_norm)
    );
    CREATE INDEX IF NOT EXISTS ix_dosis_orden
        ON dosis(medicamento_id, veces_usado DESC, ultima_vez DESC);

    CREATE TABLE IF NOT EXISTS indicaciones (
        id             INTEGER PRIMARY KEY,
        texto          TEXT    NOT NULL,
        texto_norm     TEXT    NOT NULL UNIQUE,
        veces_usado    INTEGER NOT NULL DEFAULT 0,
        ultima_vez     TEXT,
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_indicaciones_orden
        ON indicaciones(veces_usado DESC, ultima_vez DESC);

    CREATE TABLE IF NOT EXISTS diagnosticos (
        id             INTEGER PRIMARY KEY,
        texto          TEXT    NOT NULL,
        texto_norm     TEXT    NOT NULL UNIQUE,
        veces_usado    INTEGER NOT NULL DEFAULT 0,
        ultima_vez     TEXT,
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_diagnosticos_orden
        ON diagnosticos(veces_usado DESC, ultima_vez DESC);

    CREATE TABLE IF NOT EXISTS recipes (
        id                INTEGER PRIMARY KEY,
        codigo            TEXT    NOT NULL UNIQUE,
        anio              INTEGER NOT NULL,
        secuencial        INTEGER NOT NULL,
        paciente_id       INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE RESTRICT,
        fecha_emision     TEXT    NOT NULL,
        diagnostico       TEXT,
        notas             TEXT,
        ruta_pdf          TEXT,
        anulado           INTEGER NOT NULL DEFAULT 0 CHECK (anulado IN (0, 1)),
        motivo_anulacion  TEXT,
        fecha_anulacion   TEXT,
        creado_en         TEXT    NOT NULL,
        actualizado_en    TEXT    NOT NULL,
        UNIQUE (anio, secuencial)
    );
    CREATE INDEX IF NOT EXISTS ix_recipes_fecha    ON recipes(fecha_emision DESC);
    CREATE INDEX IF NOT EXISTS ix_recipes_paciente ON recipes(paciente_id);

    -- Copia literal de los textos: un récipe emitido es un documento
    -- histórico y no cambia si mañana se corrige el catálogo (§5).
    CREATE TABLE IF NOT EXISTS recipe_items (
        id             INTEGER PRIMARY KEY,
        recipe_id      INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        orden          INTEGER NOT NULL,
        medicamento    TEXT    NOT NULL,
        presentacion   TEXT    NOT NULL DEFAULT '',
        cantidad       TEXT    NOT NULL DEFAULT '',
        dosis          TEXT    NOT NULL DEFAULT '',
        indicaciones   TEXT    NOT NULL DEFAULT '',
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL,
        UNIQUE (recipe_id, orden)
    );
    CREATE INDEX IF NOT EXISTS ix_recipe_items_recipe ON recipe_items(recipe_id, orden);

    CREATE TABLE IF NOT EXISTS contador_anual (
        anio              INTEGER PRIMARY KEY,
        ultimo_secuencial INTEGER NOT NULL DEFAULT 0,
        creado_en         TEXT    NOT NULL,
        actualizado_en    TEXT    NOT NULL
    );
    """,

    # -- versión 2: indicaciones generales del récipe ----------------------
    # La mitad derecha del modelo (`Ind.`) lleva las indicaciones de cada
    # medicamento —que ya viven en recipe_items.indicaciones— y ADEMÁS un
    # texto libre general del récipe, que hasta acá no tenía dónde guardarse.
    # Columna opcional: los récipes ya emitidos quedan en NULL, que es
    # exactamente lo que eran (no tenían el campo), y no se los toca.
    """
    ALTER TABLE recipes ADD COLUMN indicaciones_generales TEXT;
    """,
]

#: Versión de esquema que espera este código.
VERSION_ESQUEMA = len(MIGRACIONES)


def version_actual(con: sqlite3.Connection) -> int:
    """Versión de esquema guardada en la base (`PRAGMA user_version`)."""
    return int(con.execute("PRAGMA user_version").fetchone()[0])


def migrar(con: sqlite3.Connection) -> int:
    """Aplica las migraciones pendientes y devuelve la versión resultante.

    Idempotente: si la base ya está al día no hace nada.

    Cada versión se aplica **atómicamente**: el script y el salto de
    `user_version` van dentro de la misma transacción. En SQLite el DDL es
    transaccional y `user_version` vive en el encabezado del archivo, así que
    un corte de luz a mitad de camino deshace todo y la base queda en la
    versión anterior, entera. Volver a correr la recupera. Eso es lo que
    permite usar `ALTER TABLE`, que no se puede escribir con `IF NOT EXISTS`
    y no sobreviviría a una re-aplicación parcial.
    """
    version = version_actual(con)
    if version > VERSION_ESQUEMA:
        raise RuntimeError(
            f"La base está en la versión {version} y este programa entiende "
            f"hasta la {VERSION_ESQUEMA}. Actualizá la app antes de abrirla."
        )
    for indice in range(version, VERSION_ESQUEMA):
        guion = f"BEGIN;\n{MIGRACIONES[indice]}\nPRAGMA user_version = {indice + 1};\nCOMMIT;"
        try:
            con.executescript(guion)
        except BaseException:
            # Si el script se cortó a la mitad, la transacción sigue abierta:
            # se cierra acá para no dejar la conexión (ni el archivo) tomada.
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
    return VERSION_ESQUEMA


def inicializar(ruta: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Abre (creando si hace falta) la base y deja el esquema al día.

    Devuelve la conexión lista para usar. Se puede llamar en cada arranque.
    """
    con = conectar(ruta)
    migrar(con)
    return con


# --------------------------------------------------------------------------
# Config (clave/valor)
# --------------------------------------------------------------------------

def obtener_config(con: sqlite3.Connection, clave: str, por_defecto: str | None = None) -> str | None:
    fila = con.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila is not None else por_defecto


def obtener_config_todo(con: sqlite3.Connection) -> dict[str, str | None]:
    return {f["clave"]: f["valor"] for f in con.execute("SELECT clave, valor FROM config")}


def guardar_config(con: sqlite3.Connection, clave: str, valor: str | None) -> None:
    momento = ahora_iso()
    con.execute(
        """
        INSERT INTO config (clave, valor, creado_en, actualizado_en)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor,
                                         actualizado_en = excluded.actualizado_en
        """,
        (clave, valor, momento, momento),
    )


def guardar_config_varios(con: sqlite3.Connection, valores: dict[str, str | None]) -> None:
    with transaccion(con):
        for clave, valor in valores.items():
            guardar_config(con, clave, valor)


# --------------------------------------------------------------------------
# Pacientes
# --------------------------------------------------------------------------

_CAMPOS_PACIENTE = (
    "nombre", "cedula", "fecha_nacimiento", "edad", "sexo", "telefono", "notas",
)


def buscar_pacientes(
    con: sqlite3.Connection, termino: str | None = "", limite: int = LIMITE_SUGERENCIAS
) -> list[sqlite3.Row]:
    """Autocompletado de pacientes: subcadena en nombre o cédula.

    Orden `veces_atendido DESC, ultima_vez DESC`, máximo 8 (§8). Con término
    vacío devuelve los más frecuentes, que es lo que conviene mostrar al
    entrar al campo.
    """
    if normalizar(termino):
        sql = """
            SELECT * FROM pacientes
            WHERE nombre_norm LIKE ? ESCAPE '\\'
               OR IFNULL(cedula, '') LIKE ? ESCAPE '\\'
            ORDER BY veces_atendido DESC, ultima_vez DESC, nombre_norm ASC
            LIMIT ?
        """
        patron = _patron_like(termino)
        parametros: tuple[Any, ...] = (patron, patron, limite)
    else:
        sql = """
            SELECT * FROM pacientes
            ORDER BY veces_atendido DESC, ultima_vez DESC, nombre_norm ASC
            LIMIT ?
        """
        parametros = (limite,)
    return list(con.execute(sql, parametros))


def obtener_paciente(con: sqlite3.Connection, paciente_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM pacientes WHERE id = ?", (paciente_id,)).fetchone()


def obtener_paciente_por_cedula(con: sqlite3.Connection, cedula: str | None) -> sqlite3.Row | None:
    cedula = limpiar(cedula)
    if not cedula:
        return None
    return con.execute("SELECT * FROM pacientes WHERE cedula = ?", (cedula,)).fetchone()


def crear_paciente(
    con: sqlite3.Connection,
    nombre: str,
    cedula: str | None = None,
    fecha_nacimiento: str | None = None,
    edad: int | None = None,
    sexo: str | None = None,
    telefono: str | None = None,
    notas: str | None = None,
) -> int:
    """Da de alta un paciente y devuelve su id. La cédula vacía se guarda NULL."""
    nombre = limpiar(nombre)
    if not nombre:
        raise ValueError("El paciente necesita un nombre.")
    momento = ahora_iso()
    cur = con.execute(
        """
        INSERT INTO pacientes (nombre, nombre_norm, cedula, fecha_nacimiento, edad,
                               sexo, telefono, notas, veces_atendido, ultima_vez,
                               creado_en, actualizado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
        """,
        (
            nombre, normalizar(nombre), limpiar(cedula) or None,
            limpiar(fecha_nacimiento) or None, edad, limpiar(sexo) or None,
            limpiar(telefono) or None, limpiar(notas) or None, momento, momento,
        ),
    )
    return int(cur.lastrowid)


def actualizar_paciente(con: sqlite3.Connection, paciente_id: int, **campos: Any) -> None:
    """Actualiza solo los campos pasados. Ignora claves desconocidas."""
    asignaciones: list[str] = []
    valores: list[Any] = []
    for campo in _CAMPOS_PACIENTE:
        if campo not in campos:
            continue
        valor = campos[campo]
        if campo == "edad":
            valor = int(valor) if valor not in (None, "") else None
        else:
            valor = limpiar(valor) or None
        asignaciones.append(f"{campo} = ?")
        valores.append(valor)
        if campo == "nombre":
            if not valor:
                raise ValueError("El paciente necesita un nombre.")
            asignaciones.append("nombre_norm = ?")
            valores.append(normalizar(valor))
    if not asignaciones:
        return
    asignaciones.append("actualizado_en = ?")
    valores.extend([ahora_iso(), paciente_id])
    con.execute(f"UPDATE pacientes SET {', '.join(asignaciones)} WHERE id = ?", valores)


def obtener_o_crear_paciente(
    con: sqlite3.Connection, nombre: str, cedula: str | None = None, **datos: Any
) -> int:
    """Busca por cédula y, si no hay, por nombre normalizado exacto.

    Si existe, completa los datos que estaban vacíos (el médico va cargando
    de a poco) sin pisar los que ya tenían valor. Si no existe, lo crea.
    """
    existente = obtener_paciente_por_cedula(con, cedula)
    if existente is None:
        existente = con.execute(
            "SELECT * FROM pacientes WHERE nombre_norm = ? ORDER BY veces_atendido DESC LIMIT 1",
            (normalizar(nombre),),
        ).fetchone()
    if existente is None:
        return crear_paciente(con, nombre, cedula=cedula, **datos)

    faltantes = {c: v for c, v in {"cedula": cedula, **datos}.items()
                 if c in _CAMPOS_PACIENTE and v not in (None, "") and not existente[c]}
    if faltantes:
        actualizar_paciente(con, existente["id"], **faltantes)
    return int(existente["id"])


def registrar_atencion(con: sqlite3.Connection, paciente_id: int, cuando: str | None = None) -> None:
    """Suma una atención al paciente. Se llama al guardar el récipe."""
    momento = cuando or ahora_iso()
    con.execute(
        """
        UPDATE pacientes
           SET veces_atendido = veces_atendido + 1,
               ultima_vez = ?, actualizado_en = ?
         WHERE id = ?
        """,
        (momento, momento, paciente_id),
    )


# --------------------------------------------------------------------------
# Medicamentos y dosis
# --------------------------------------------------------------------------

def buscar_medicamentos(
    con: sqlite3.Connection, termino: str | None = "", limite: int = LIMITE_SUGERENCIAS
) -> list[sqlite3.Row]:
    """Sugerencias de medicamentos por subcadena de nombre o presentación."""
    if normalizar(termino):
        sql = """
            SELECT * FROM medicamentos
            WHERE nombre_norm LIKE ? ESCAPE '\\'
               OR presentacion_norm LIKE ? ESCAPE '\\'
            ORDER BY veces_usado DESC, ultima_vez DESC, nombre_norm ASC
            LIMIT ?
        """
        patron = _patron_like(termino)
        parametros: tuple[Any, ...] = (patron, patron, limite)
    else:
        sql = """
            SELECT * FROM medicamentos
            ORDER BY veces_usado DESC, ultima_vez DESC, nombre_norm ASC
            LIMIT ?
        """
        parametros = (limite,)
    return list(con.execute(sql, parametros))


def obtener_medicamento(con: sqlite3.Connection, medicamento_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM medicamentos WHERE id = ?", (medicamento_id,)).fetchone()


def obtener_o_crear_medicamento(
    con: sqlite3.Connection, nombre: str, presentacion: str | None = ""
) -> int:
    """Devuelve el id del medicamento (nombre, presentación), creándolo si no está."""
    nombre = limpiar(nombre)
    if not nombre:
        raise ValueError("El medicamento necesita un nombre.")
    presentacion = limpiar(presentacion)
    fila = con.execute(
        "SELECT id FROM medicamentos WHERE nombre_norm = ? AND presentacion_norm = ?",
        (normalizar(nombre), normalizar(presentacion)),
    ).fetchone()
    if fila is not None:
        return int(fila["id"])
    momento = ahora_iso()
    cur = con.execute(
        """
        INSERT INTO medicamentos (nombre, nombre_norm, presentacion, presentacion_norm,
                                  veces_usado, ultima_vez, creado_en, actualizado_en)
        VALUES (?, ?, ?, ?, 0, NULL, ?, ?)
        """,
        (nombre, normalizar(nombre), presentacion, normalizar(presentacion), momento, momento),
    )
    return int(cur.lastrowid)


def registrar_uso_medicamento(
    con: sqlite3.Connection, medicamento_id: int, cuando: str | None = None
) -> None:
    momento = cuando or ahora_iso()
    con.execute(
        """
        UPDATE medicamentos
           SET veces_usado = veces_usado + 1, ultima_vez = ?, actualizado_en = ?
         WHERE id = ?
        """,
        (momento, momento, medicamento_id),
    )


def buscar_dosis(
    con: sqlite3.Connection,
    medicamento_id: int,
    termino: str | None = "",
    limite: int = LIMITE_SUGERENCIAS,
) -> list[sqlite3.Row]:
    """Dosis de ESE medicamento. La dosis nunca es una lista global (§5)."""
    if normalizar(termino):
        sql = """
            SELECT * FROM dosis
            WHERE medicamento_id = ? AND texto_norm LIKE ? ESCAPE '\\'
            ORDER BY veces_usado DESC, ultima_vez DESC, texto_norm ASC
            LIMIT ?
        """
        parametros: tuple[Any, ...] = (medicamento_id, _patron_like(termino), limite)
    else:
        sql = """
            SELECT * FROM dosis
            WHERE medicamento_id = ?
            ORDER BY veces_usado DESC, ultima_vez DESC, texto_norm ASC
            LIMIT ?
        """
        parametros = (medicamento_id, limite)
    return list(con.execute(sql, parametros))


def dosis_mas_usada(con: sqlite3.Connection, medicamento_id: int) -> sqlite3.Row | None:
    """La dosis más frecuente del medicamento.

    Se ofrece como sugerencia visible y editable; la interfaz nunca la aplica
    en silencio (§2.5 y §8).
    """
    resultados = buscar_dosis(con, medicamento_id, "", limite=1)
    return resultados[0] if resultados else None


def obtener_o_crear_dosis(con: sqlite3.Connection, medicamento_id: int, texto: str) -> int:
    texto = limpiar(texto)
    if not texto:
        raise ValueError("La dosis necesita un texto.")
    fila = con.execute(
        "SELECT id FROM dosis WHERE medicamento_id = ? AND texto_norm = ?",
        (medicamento_id, normalizar(texto)),
    ).fetchone()
    if fila is not None:
        return int(fila["id"])
    momento = ahora_iso()
    cur = con.execute(
        """
        INSERT INTO dosis (medicamento_id, texto, texto_norm, veces_usado,
                           ultima_vez, creado_en, actualizado_en)
        VALUES (?, ?, ?, 0, NULL, ?, ?)
        """,
        (medicamento_id, texto, normalizar(texto), momento, momento),
    )
    return int(cur.lastrowid)


def registrar_uso_dosis(con: sqlite3.Connection, dosis_id: int, cuando: str | None = None) -> None:
    momento = cuando or ahora_iso()
    con.execute(
        """
        UPDATE dosis
           SET veces_usado = veces_usado + 1, ultima_vez = ?, actualizado_en = ?
         WHERE id = ?
        """,
        (momento, momento, dosis_id),
    )


# --------------------------------------------------------------------------
# Términos globales: indicaciones y diagnósticos
# --------------------------------------------------------------------------

def _validar_tabla(tabla: str) -> str:
    # El nombre de tabla se interpola en el SQL, así que se valida contra la
    # lista blanca en vez de confiar en quien llama.
    if tabla not in TABLAS_TERMINOS:
        raise ValueError(f"Tabla de términos desconocida: {tabla!r}")
    return tabla


def buscar_terminos(
    con: sqlite3.Connection,
    tabla: str,
    termino: str | None = "",
    limite: int = LIMITE_SUGERENCIAS,
) -> list[sqlite3.Row]:
    """Búsqueda genérica sobre `indicaciones` o `diagnosticos`."""
    tabla = _validar_tabla(tabla)
    if normalizar(termino):
        sql = f"""
            SELECT * FROM {tabla}
            WHERE texto_norm LIKE ? ESCAPE '\\'
            ORDER BY veces_usado DESC, ultima_vez DESC, texto_norm ASC
            LIMIT ?
        """
        parametros: tuple[Any, ...] = (_patron_like(termino), limite)
    else:
        sql = f"""
            SELECT * FROM {tabla}
            ORDER BY veces_usado DESC, ultima_vez DESC, texto_norm ASC
            LIMIT ?
        """
        parametros = (limite,)
    return list(con.execute(sql, parametros))


def obtener_o_crear_termino(con: sqlite3.Connection, tabla: str, texto: str) -> int:
    tabla = _validar_tabla(tabla)
    texto = limpiar(texto)
    if not texto:
        raise ValueError("El término necesita un texto.")
    fila = con.execute(
        f"SELECT id FROM {tabla} WHERE texto_norm = ?", (normalizar(texto),)
    ).fetchone()
    if fila is not None:
        return int(fila["id"])
    momento = ahora_iso()
    cur = con.execute(
        f"""
        INSERT INTO {tabla} (texto, texto_norm, veces_usado, ultima_vez,
                             creado_en, actualizado_en)
        VALUES (?, ?, 0, NULL, ?, ?)
        """,
        (texto, normalizar(texto), momento, momento),
    )
    return int(cur.lastrowid)


def registrar_uso_termino(
    con: sqlite3.Connection, tabla: str, termino_id: int, cuando: str | None = None
) -> None:
    tabla = _validar_tabla(tabla)
    momento = cuando or ahora_iso()
    con.execute(
        f"""
        UPDATE {tabla}
           SET veces_usado = veces_usado + 1, ultima_vez = ?, actualizado_en = ?
         WHERE id = ?
        """,
        (momento, momento, termino_id),
    )


# Envoltorios con nombre propio, que es lo que van a llamar rutas.py y la interfaz.

def buscar_indicaciones(
    con: sqlite3.Connection, termino: str | None = "", limite: int = LIMITE_SUGERENCIAS
) -> list[sqlite3.Row]:
    return buscar_terminos(con, "indicaciones", termino, limite)


def buscar_diagnosticos(
    con: sqlite3.Connection, termino: str | None = "", limite: int = LIMITE_SUGERENCIAS
) -> list[sqlite3.Row]:
    return buscar_terminos(con, "diagnosticos", termino, limite)


def obtener_o_crear_indicacion(con: sqlite3.Connection, texto: str) -> int:
    return obtener_o_crear_termino(con, "indicaciones", texto)


def obtener_o_crear_diagnostico(con: sqlite3.Connection, texto: str) -> int:
    return obtener_o_crear_termino(con, "diagnosticos", texto)


# --------------------------------------------------------------------------
# Aprendizaje al guardar un récipe (§8)
# --------------------------------------------------------------------------

def aprender_terminos(
    con: sqlite3.Connection,
    diagnostico: str | None = None,
    items: Iterable[dict[str, Any]] | None = None,
    cuando: str | None = None,
) -> None:
    """Registra los términos usados en un récipe e incrementa `veces_usado`.

    `items` son diccionarios con las claves `medicamento`, `presentacion`,
    `dosis` e `indicaciones` (las que falten se ignoran). No valida nada
    clínico: solo aprende lo que el médico escribió.

    Se espera que quien llama esté dentro de la misma transacción del guardado.
    """
    momento = cuando or ahora_iso()
    if limpiar(diagnostico):
        registrar_uso_termino(
            con, "diagnosticos", obtener_o_crear_diagnostico(con, diagnostico), momento
        )
    for item in items or ():
        nombre = limpiar(item.get("medicamento"))
        if not nombre:
            continue
        medicamento_id = obtener_o_crear_medicamento(con, nombre, item.get("presentacion"))
        registrar_uso_medicamento(con, medicamento_id, momento)
        if limpiar(item.get("dosis")):
            registrar_uso_dosis(
                con, obtener_o_crear_dosis(con, medicamento_id, item["dosis"]), momento
            )
        if limpiar(item.get("indicaciones")):
            registrar_uso_termino(
                con, "indicaciones",
                obtener_o_crear_indicacion(con, item["indicaciones"]), momento,
            )


# --------------------------------------------------------------------------
# Récipes: lectura, renglones y anulación
#
# La creación del récipe (que asigna el código dentro de una transacción
# BEGIN IMMEDIATE junto con `contador_anual`) vive en codigos.py.
# --------------------------------------------------------------------------

def obtener_ultimo_secuencial(con: sqlite3.Connection, anio: int) -> int:
    """Último secuencial emitido en el año. 0 si el año todavía no arrancó."""
    fila = con.execute(
        "SELECT ultimo_secuencial FROM contador_anual WHERE anio = ?", (anio,)
    ).fetchone()
    return int(fila["ultimo_secuencial"]) if fila is not None else 0


def obtener_recipe(con: sqlite3.Connection, recipe_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()


def obtener_recipe_por_codigo(con: sqlite3.Connection, codigo: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM recipes WHERE codigo = ?", (limpiar(codigo),)).fetchone()


def obtener_recipe_completo(con: sqlite3.Connection, recipe_id: int) -> sqlite3.Row | None:
    """Un récipe con el nombre y la cédula del paciente, igual que `buscar_recipes`.

    Sirve para devolver un récipe suelto —el que se acaba de anular, por
    ejemplo— con exactamente la misma forma que las filas del Historial, sin
    que quien llama tenga que armar el JOIN por su cuenta.
    """
    return con.execute(
        """
        SELECT r.*, p.nombre AS paciente_nombre, p.cedula AS paciente_cedula,
               p.edad AS paciente_edad,
               (SELECT COUNT(*) FROM recipe_items ri WHERE ri.recipe_id = r.id) AS cantidad_items
          FROM recipes r
          JOIN pacientes p ON p.id = r.paciente_id
         WHERE r.id = ?
        """,
        (recipe_id,),
    ).fetchone()


def insertar_recipe_item(
    con: sqlite3.Connection,
    recipe_id: int,
    orden: int,
    medicamento: str,
    presentacion: str | None = "",
    cantidad: str | None = "",
    dosis: str | None = "",
    indicaciones: str | None = "",
) -> int:
    """Guarda un renglón con copia literal de los textos, sin referencias (§5)."""
    momento = ahora_iso()
    cur = con.execute(
        """
        INSERT INTO recipe_items (recipe_id, orden, medicamento, presentacion,
                                  cantidad, dosis, indicaciones,
                                  creado_en, actualizado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_id, orden, limpiar(medicamento), limpiar(presentacion),
            limpiar(cantidad), limpiar(dosis), limpiar(indicaciones), momento, momento,
        ),
    )
    return int(cur.lastrowid)


def obtener_items(con: sqlite3.Connection, recipe_id: int) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT * FROM recipe_items WHERE recipe_id = ? ORDER BY orden ASC", (recipe_id,)
    ))


def guardar_ruta_pdf(con: sqlite3.Connection, recipe_id: int, ruta_pdf: str) -> None:
    con.execute(
        "UPDATE recipes SET ruta_pdf = ?, actualizado_en = ? WHERE id = ?",
        (str(ruta_pdf), ahora_iso(), recipe_id),
    )


def buscar_recipes(
    con: sqlite3.Connection,
    termino: str | None = "",
    desde: str | None = None,
    hasta: str | None = None,
    incluir_anulados: bool = True,
    limite: int = 200,
) -> list[sqlite3.Row]:
    """Historial (§7-B): busca por código, paciente o medicamento y por fechas.

    `desde`/`hasta` son fechas ISO (`AAAA-MM-DD`), inclusive ambas.
    Devuelve además el nombre y la cédula del paciente y la cantidad de renglones.
    """
    condiciones: list[str] = []
    parametros: list[Any] = []

    if normalizar(termino):
        patron = _patron_like(termino)
        condiciones.append(
            """(norm(r.codigo) LIKE ? ESCAPE '\\'
                OR p.nombre_norm LIKE ? ESCAPE '\\'
                OR IFNULL(p.cedula, '') LIKE ? ESCAPE '\\'
                OR EXISTS (SELECT 1 FROM recipe_items ri
                            WHERE ri.recipe_id = r.id
                              AND norm(ri.medicamento) LIKE ? ESCAPE '\\'))"""
        )
        parametros.extend([patron, patron, patron, patron])
    if desde:
        condiciones.append("DATE(r.fecha_emision) >= DATE(?)")
        parametros.append(desde)
    if hasta:
        condiciones.append("DATE(r.fecha_emision) <= DATE(?)")
        parametros.append(hasta)
    if not incluir_anulados:
        condiciones.append("r.anulado = 0")

    donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    parametros.append(limite)
    return list(con.execute(
        f"""
        SELECT r.*, p.nombre AS paciente_nombre, p.cedula AS paciente_cedula,
               p.edad AS paciente_edad,
               (SELECT COUNT(*) FROM recipe_items ri WHERE ri.recipe_id = r.id) AS cantidad_items
          FROM recipes r
          JOIN pacientes p ON p.id = r.paciente_id
          {donde}
         ORDER BY r.fecha_emision DESC, r.id DESC
         LIMIT ?
        """,
        parametros,
    ))


def medicamentos_por_recipe(
    con: sqlite3.Connection, recipe_ids: Sequence[int]
) -> dict[int, list[str]]:
    """Nombres de los medicamentos de cada récipe, en el orden en que se recetaron.

    Es para el resumen del Historial (§7-B): la lista de resultados muestra
    "Amoxicilina, Ibuprofeno" al lado del código, sin abrir el récipe.

    Se resuelve en una sola consulta para los récipes que ya se buscaron —el
    Historial trae 200 como mucho— en vez de una consulta por fila. Se lee el
    texto **literal** de `recipe_items`, que es lo que se recetó ese día y no
    lo que hoy diga el catálogo (§5).
    """
    ids = [int(i) for i in recipe_ids]
    if not ids:
        return {}
    marcadores = ",".join("?" * len(ids))
    por_recipe: dict[int, list[str]] = {i: [] for i in ids}
    for fila in con.execute(
        f"""
        SELECT recipe_id, medicamento
          FROM recipe_items
         WHERE recipe_id IN ({marcadores})
         ORDER BY recipe_id ASC, orden ASC
        """,
        ids,
    ):
        por_recipe[int(fila["recipe_id"])].append(fila["medicamento"])
    return por_recipe


def anular_recipe(
    con: sqlite3.Connection, recipe_id: int, motivo: str, cuando: str | None = None
) -> None:
    """Marca el récipe como anulado. Nunca borra: el código queda quemado (§10)."""
    motivo = limpiar(motivo)
    if not motivo:
        raise ValueError("La anulación exige un motivo escrito.")
    momento = cuando or ahora_iso()
    cur = con.execute(
        """
        UPDATE recipes
           SET anulado = 1, motivo_anulacion = ?, fecha_anulacion = ?, actualizado_en = ?
         WHERE id = ? AND anulado = 0
        """,
        (motivo, momento, momento, recipe_id),
    )
    if cur.rowcount == 0:
        raise ValueError("El récipe no existe o ya estaba anulado.")


def listar_recipes(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Todos los récipes, para regenerar el Excel completo desde SQLite (§9)."""
    return buscar_recipes(con, "", limite=-1)


def listar_items_todos(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Un renglón por medicamento recetado, para la segunda hoja del Excel (§9)."""
    return list(con.execute(
        """
        SELECT r.codigo, r.fecha_emision, r.anulado, p.nombre AS paciente_nombre,
               ri.orden, ri.medicamento, ri.presentacion, ri.cantidad,
               ri.dosis, ri.indicaciones
          FROM recipe_items ri
          JOIN recipes r   ON r.id = ri.recipe_id
          JOIN pacientes p ON p.id = r.paciente_id
         ORDER BY r.fecha_emision DESC, r.id DESC, ri.orden ASC
        """
    ))


# --------------------------------------------------------------------------
# Ayuda para el resto del código
# --------------------------------------------------------------------------

def a_dict(filas: sqlite3.Row | Sequence[sqlite3.Row] | None) -> Any:
    """Convierte filas a dict/lista de dicts, listo para devolver como JSON."""
    if filas is None:
        return None
    if isinstance(filas, sqlite3.Row):
        return dict(filas)
    return [dict(f) for f in filas]
