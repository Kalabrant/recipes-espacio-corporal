"""Base de datos de la app de récipes médicos.

Un solo archivo SQLite, sin servicio y sin dependencias fuera de la stdlib.
Acá viven el esquema, las migraciones por versión y las consultas que usan
las demás piezas (rutas.py, codigos.py, pdf_recipe.py, excel.py).

Reglas que este módulo respeta y que no hay que romper:
  - Ningún récipe se borra: se anula (§2.4 y §10 de las instrucciones).
  - `recipe_items` guarda copia literal de los textos, nunca referencias (§5).
  - La asignación del código vive en codigos.py, no acá; este módulo provee
    los contadores (`contador_anual`, `contador_pacientes`) y el contexto
    `transaccion(...)` con BEGIN IMMEDIATE para que sea atómica (§6.3).

Evolución 2.0 (decisiones del médico del 2026-08-18):
  - El código es **del paciente** y correlativo de por vida (`EC-0001`): se
    asigna al darlo de alta y todos sus récipes lo llevan impreso (dec. 1 y 2).
  - La historia clínica se reparte en `historias` (lo que se llena una vez por
    paciente) y `consultas` + `signos_vitales` (lo que se repite cada visita),
    con `anexos`, `mediciones` e `informes` colgando del paciente (dec. 3 a 13).
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any, ContextManager, Iterable, Iterator, Sequence

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

#: Cantidad máxima de sugerencias del autocompletado (§8).
LIMITE_SUGERENCIAS = 8

#: Tablas de términos globales que aprende la app.
TABLAS_TERMINOS = ("indicaciones", "diagnosticos")

#: Denominadores impresos del cuestionario de alimentación (Parte A §2.4 del
#: análisis). El médico anota el numerador; el denominador es fijo y la
#: interfaz lo muestra al lado del selector: `Comidas al día [2]/3`.
DENOMINADORES_ALIMENTACION: dict[str, int] = {
    "alim_comidas_dia": 3,
    "alim_frutas_verduras": 7,
    "alim_pollo": 7,
    "alim_pescado": 7,
    "alim_carnes_rojas": 7,
    "alim_carbohidratos": 7,
    "alim_litros_agua": 2,
}

#: Los dos informes de la Parte B del análisis (dec. 10).
TIPOS_INFORME = ("clinico", "aseguradora")

#: Tipos de anexo que ofrece la bandeja de imágenes (dec. 11).
TIPOS_ANEXO = ("medicion", "laboratorio", "imagen", "otro")

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


def transaccion_si_hace_falta(con: sqlite3.Connection) -> ContextManager[sqlite3.Connection]:
    """`BEGIN IMMEDIATE`, salvo que quien llama ya haya abierto la suya.

    Es lo que permite que una operación (dar de alta un paciente, guardar un
    récipe) sea atómica por sí sola y además se pueda meter dentro de una
    transacción más grande —la que abre `rutas.py` al emitir—. Si quien llama
    ya abrió la suya, esa tiene que ser inmediata: de ahí sale la garantía de
    §6.3.
    """
    if con.in_transaction:
        return nullcontext(con)
    return transaccion(con, inmediata=True)


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

    # -- versión 3: el código pasa a ser del paciente + historia clínica ----
    # Decisiones del médico del 2026-08-18 (build/decisiones-evolucion.md):
    #   1. Código correlativo de por vida por paciente, sin año: EC-0001.
    #   2. El récipe imprime EL CÓDIGO DEL PACIENTE; `recipes.codigo` deja de
    #      ser único y `anio`/`secuencial` quedan de legado (nullable) para
    #      las filas viejas, que conservan el código con el que se imprimieron.
    #   3 a 13. Historia clínica repartida en ficha + antecedentes (una vez
    #      por paciente) y consultas con signos vitales (cada visita), más
    #      anexos, mediciones e informes.
    #
    # SQLite no sabe soltar un UNIQUE con ALTER TABLE: `recipes` se reconstruye
    # copiando los datos. Por eso `migrar` apaga las claves foráneas mientras
    # corre: con ellas encendidas, el DROP de la tabla vieja dispararía el
    # ON DELETE CASCADE de `recipe_items` y se llevaría los renglones puestos.
    """
    ---------------------------------------------------------------- pacientes
    ALTER TABLE pacientes ADD COLUMN codigo TEXT;
    -- Único cuando tiene valor, igual que la cédula.
    CREATE UNIQUE INDEX IF NOT EXISTS ix_pacientes_codigo
        ON pacientes(codigo) WHERE codigo IS NOT NULL AND codigo <> '';

    -- Un solo renglón: el correlativo de pacientes no reinicia nunca (dec. 1),
    -- así que no lleva año como `contador_anual`.
    CREATE TABLE IF NOT EXISTS contador_pacientes (
        id                INTEGER PRIMARY KEY CHECK (id = 1),
        ultimo_secuencial INTEGER NOT NULL DEFAULT 0,
        creado_en         TEXT    NOT NULL,
        actualizado_en    TEXT    NOT NULL
    );

    -- Los pacientes que ya estaban reciben código por orden de id, que es el
    -- orden en que se dieron de alta. El prefijo es el vigente en `config`;
    -- si estuviera corrupto se cae a EC, igual que `codigos.obtener_prefijo`.
    WITH orden AS (
        SELECT id AS pid, ROW_NUMBER() OVER (ORDER BY id) AS n FROM pacientes
    )
    UPDATE pacientes
       SET codigo = IFNULL(
               (SELECT CASE
                         WHEN REPLACE(TRIM(valor), ' ', '') <> ''
                          AND LENGTH(REPLACE(TRIM(valor), ' ', '')) <= 10
                          AND REPLACE(TRIM(valor), ' ', '') NOT GLOB '*[^A-Za-z0-9]*'
                         THEN UPPER(REPLACE(TRIM(valor), ' ', ''))
                       END
                  FROM config WHERE clave = 'prefijo_codigo'), 'EC')
            || '-'
            || (SELECT CASE WHEN n < 10000
                            THEN SUBSTR('0000' || n, -4)
                            ELSE CAST(n AS TEXT)
                       END
                  FROM orden WHERE pid = pacientes.id),
           actualizado_en = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')
     WHERE codigo IS NULL OR codigo = '';

    INSERT INTO contador_pacientes (id, ultimo_secuencial, creado_en, actualizado_en)
    SELECT 1, COUNT(*),
           STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'),
           STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')
      FROM pacientes;

    ---------------------------------------------------- historia: lo de una vez
    -- 1 a 1 con el paciente. De la ficha del papel quedan solo estado civil,
    -- ocupación y tipo de sangre (dec. 4 y 6); la vivienda es nota libre
    -- (dec. 5) y la alimentación son los 7 numeradores del formulario.
    CREATE TABLE IF NOT EXISTS historias (
        id                    INTEGER PRIMARY KEY,
        paciente_id           INTEGER NOT NULL UNIQUE
                              REFERENCES pacientes(id) ON DELETE CASCADE,

        estado_civil          TEXT    NOT NULL DEFAULT '',
        ocupacion             TEXT    NOT NULL DEFAULT '',
        tipo_sangre           TEXT    NOT NULL DEFAULT '',

        fam_madre             TEXT    NOT NULL DEFAULT '',
        fam_padre             TEXT    NOT NULL DEFAULT '',
        fam_hermanos          TEXT    NOT NULL DEFAULT '',
        fam_hijos             TEXT    NOT NULL DEFAULT '',

        alim_comidas_dia      INTEGER,
        alim_frutas_verduras  INTEGER,
        alim_pollo            INTEGER,
        alim_pescado          INTEGER,
        alim_carnes_rojas     INTEGER,
        alim_carbohidratos    INTEGER,
        alim_litros_agua      INTEGER,
        alimentacion_notas    TEXT    NOT NULL DEFAULT '',
        habitacion            TEXT    NOT NULL DEFAULT '',
        actividad_fisica      TEXT    NOT NULL DEFAULT '',

        cronico_degenerativos TEXT    NOT NULL DEFAULT '',
        alcoholismo           TEXT    NOT NULL DEFAULT '',
        tabaquismo            TEXT    NOT NULL DEFAULT '',
        toxicomanias          TEXT    NOT NULL DEFAULT '',
        quirurgicos           TEXT    NOT NULL DEFAULT '',
        traumaticos           TEXT    NOT NULL DEFAULT '',
        ginecologicos         TEXT    NOT NULL DEFAULT '',
        hospitalizaciones     TEXT    NOT NULL DEFAULT '',
        transfusiones         TEXT    NOT NULL DEFAULT '',
        alergias              TEXT    NOT NULL DEFAULT '',

        notas_generales       TEXT    NOT NULL DEFAULT '',
        creado_en             TEXT    NOT NULL,
        actualizado_en        TEXT    NOT NULL
    );

    ------------------------------------------------- historia: lo que se repite
    CREATE TABLE IF NOT EXISTS consultas (
        id             INTEGER PRIMARY KEY,
        paciente_id    INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        fecha          TEXT    NOT NULL,
        motivo         TEXT    NOT NULL DEFAULT '',
        examen_fisico  TEXT    NOT NULL DEFAULT '',
        evolucion      TEXT    NOT NULL DEFAULT '',
        diagnostico    TEXT    NOT NULL DEFAULT '',
        plan           TEXT    NOT NULL DEFAULT '',
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_consultas_paciente
        ON consultas(paciente_id, fecha DESC);

    -- La tabla del papel (Parte A §2.7), una sola vez por consulta: es lo que
    -- cambia entre visitas y lo que el médico va a querer comparar.
    CREATE TABLE IF NOT EXISTS signos_vitales (
        id             INTEGER PRIMARY KEY,
        consulta_id    INTEGER NOT NULL UNIQUE
                       REFERENCES consultas(id) ON DELETE CASCADE,
        ta_sistolica   INTEGER,   -- mmHg
        ta_diastolica  INTEGER,   -- mmHg
        fc             INTEGER,   -- lpm
        fr             INTEGER,   -- rpm
        temperatura    REAL,      -- °C
        tam            REAL,      -- mmHg, calculable de la TA
        dxtx           INTEGER,   -- mg/dL, glucemia capilar
        tfg            REAL,      -- mL/min/1.73m²
        spo2           INTEGER,   -- %
        peso           REAL,      -- kg
        talla          REAL,      -- m
        imc            REAL,      -- calculable de peso y talla
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL
    );

    ------------------------------------------------------- anexos y mediciones
    -- Copia del archivo que llega por WhatsApp (dec. 11). El original nunca se
    -- toca; acá va la ruta RELATIVA a la carpeta de datos, para que mover
    -- Documents\\Recipes a otro disco no rompa nada. `sha256` es único: hace de
    -- deduplicación y de marca de "ya procesada" para la bandeja.
    CREATE TABLE IF NOT EXISTS anexos (
        id             INTEGER PRIMARY KEY,
        paciente_id    INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        consulta_id    INTEGER REFERENCES consultas(id) ON DELETE SET NULL,
        ruta_relativa  TEXT    NOT NULL,
        sha256         TEXT    NOT NULL UNIQUE,
        fecha_medicion TEXT    NOT NULL,   -- la que confirmó el médico, no la del archivo
        tipo           TEXT    NOT NULL DEFAULT 'medicion',
        nota           TEXT    NOT NULL DEFAULT '',
        ancho_px       INTEGER,
        alto_px        INTEGER,
        bytes          INTEGER,
        origen         TEXT    NOT NULL DEFAULT '',   -- de dónde se copió
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_anexos_paciente
        ON anexos(paciente_id, fecha_medicion DESC);
    CREATE INDEX IF NOT EXISTS ix_anexos_consulta ON anexos(consulta_id);

    -- Los valores clave tipeados a mano de una medición (dec. 13). Opcional
    -- siempre: sirven para el gráfico de evolución. Si el anexo se borra, la
    -- medición queda: los números ya los tipeó el médico.
    CREATE TABLE IF NOT EXISTS mediciones (
        id             INTEGER PRIMARY KEY,
        paciente_id    INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        anexo_id       INTEGER REFERENCES anexos(id) ON DELETE SET NULL,
        fecha          TEXT    NOT NULL,
        peso           REAL,      -- kg
        imc            REAL,      -- kg/m²
        grasa_pct      REAL,      -- %
        musculo_kg     REAL,      -- kg
        grasa_visceral REAL,
        creado_en      TEXT    NOT NULL,
        actualizado_en TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_mediciones_paciente
        ON mediciones(paciente_id, fecha DESC);

    ------------------------------------------------------------------ informes
    -- Los dos tipos de la Parte B del análisis (dec. 10): el clínico en prosa
    -- (plantilla B) y el de la aseguradora por campos (plantilla A). Se
    -- guardan en la historia con su texto final y su PDF, y se anulan como los
    -- récipes: nunca se borran. `codigo_paciente` es copia literal al emitir,
    -- porque un documento emitido es histórico.
    CREATE TABLE IF NOT EXISTS informes (
        id                   INTEGER PRIMARY KEY,
        paciente_id          INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        consulta_id          INTEGER REFERENCES consultas(id) ON DELETE SET NULL,
        tipo                 TEXT    NOT NULL DEFAULT 'clinico'
                             CHECK (tipo IN ('clinico', 'aseguradora')),
        codigo_paciente      TEXT    NOT NULL DEFAULT '',
        fecha                TEXT    NOT NULL,

        cuerpo               TEXT    NOT NULL DEFAULT '',   -- prosa (plantilla B)
        diagnostico          TEXT    NOT NULL DEFAULT '',
        tratamiento          TEXT    NOT NULL DEFAULT '',
        ciudad               TEXT    NOT NULL DEFAULT '',

        especialidad         TEXT    NOT NULL DEFAULT '',   -- plantilla A
        numero_poliza        TEXT    NOT NULL DEFAULT '',
        prestacion_sanitaria TEXT    NOT NULL DEFAULT '',
        antecedentes         TEXT    NOT NULL DEFAULT '',
        motivo_consulta      TEXT    NOT NULL DEFAULT '',
        evolucion            TEXT    NOT NULL DEFAULT '',

        ruta_pdf             TEXT,
        anulado              INTEGER NOT NULL DEFAULT 0 CHECK (anulado IN (0, 1)),
        motivo_anulacion     TEXT,
        fecha_anulacion      TEXT,
        creado_en            TEXT    NOT NULL,
        actualizado_en       TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_informes_paciente ON informes(paciente_id, fecha DESC);

    -- La página de anexo es OPT-IN por informe (dec. 12): acá queda qué eligió
    -- el médico al generar, para poder reimprimir el mismo PDF.
    CREATE TABLE IF NOT EXISTS informe_anexos (
        informe_id INTEGER NOT NULL REFERENCES informes(id) ON DELETE CASCADE,
        anexo_id   INTEGER NOT NULL REFERENCES anexos(id)   ON DELETE CASCADE,
        orden      INTEGER NOT NULL DEFAULT 1,
        creado_en  TEXT    NOT NULL,
        PRIMARY KEY (informe_id, anexo_id)
    );

    ------------------------------------------------------- récipes reconstruidos
    -- `codigo` pasa a ser el del paciente: deja de ser único (dos récipes del
    -- mismo paciente llevan el mismo) y `anio`/`secuencial` quedan nullable,
    -- solo con lo que ya traían las filas viejas. El UNIQUE(anio, secuencial)
    -- se conserva para que la numeración vieja siga siendo consistente; las
    -- filas nuevas van con NULL, que SQLite considera siempre distinto.
    CREATE TABLE recipes_nueva (
        id                INTEGER PRIMARY KEY,
        codigo            TEXT    NOT NULL,
        anio              INTEGER,
        secuencial        INTEGER,
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
        indicaciones_generales TEXT,
        consulta_id       INTEGER REFERENCES consultas(id) ON DELETE SET NULL,
        UNIQUE (anio, secuencial)
    );

    INSERT INTO recipes_nueva (id, codigo, anio, secuencial, paciente_id, fecha_emision,
                               diagnostico, notas, ruta_pdf, anulado, motivo_anulacion,
                               fecha_anulacion, creado_en, actualizado_en,
                               indicaciones_generales, consulta_id)
    SELECT id, codigo, anio, secuencial, paciente_id, fecha_emision,
           diagnostico, notas, ruta_pdf, anulado, motivo_anulacion,
           fecha_anulacion, creado_en, actualizado_en,
           indicaciones_generales, NULL
      FROM recipes;

    DROP TABLE recipes;
    ALTER TABLE recipes_nueva RENAME TO recipes;

    CREATE INDEX IF NOT EXISTS ix_recipes_fecha    ON recipes(fecha_emision DESC);
    CREATE INDEX IF NOT EXISTS ix_recipes_paciente ON recipes(paciente_id);
    CREATE INDEX IF NOT EXISTS ix_recipes_codigo   ON recipes(codigo);
    CREATE INDEX IF NOT EXISTS ix_recipes_consulta ON recipes(consulta_id);
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
    if version == VERSION_ESQUEMA:
        return VERSION_ESQUEMA

    # Reconstruir una tabla (la v3 rehace `recipes` para soltarle el UNIQUE del
    # código) exige las claves foráneas APAGADAS: con ellas encendidas, el DROP
    # de la tabla vieja dispara el ON DELETE CASCADE de `recipe_items` y se
    # lleva los renglones puestos. El PRAGMA no tiene efecto dentro de una
    # transacción, así que se apaga acá afuera y se restaura al terminar.
    fk_previo = int(con.execute("PRAGMA foreign_keys").fetchone()[0])
    con.execute("PRAGMA foreign_keys = OFF")
    if int(con.execute("PRAGMA foreign_keys").fetchone()[0]):
        raise RuntimeError(
            "No se pudieron apagar las claves foráneas para migrar: ¿quedó una "
            "transacción abierta en esta conexión? Cerrala y volvé a abrir la app."
        )
    try:
        for indice in range(version, VERSION_ESQUEMA):
            guion = (
                f"BEGIN;\n{MIGRACIONES[indice]}\n"
                f"PRAGMA user_version = {indice + 1};\nCOMMIT;"
            )
            try:
                con.executescript(guion)
            except BaseException:
                # Si el script se cortó a la mitad, la transacción sigue
                # abierta: se cierra acá para no dejar la conexión (ni el
                # archivo) tomada.
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
    finally:
        con.execute(f"PRAGMA foreign_keys = {'ON' if fk_previo else 'OFF'}")
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
# `codigo` queda fuera a propósito: se asigna una vez al dar de alta y no se
# corrige nunca (dec. 1). Cambiarlo dejaría documentos impresos huérfanos.


def _codigos() -> Any:
    """Importa `codigos` en el momento de usarlo, no al cargar el módulo.

    `codigos` importa a `basedatos`, así que importarlo acá arriba sería un
    ciclo. La numeración sigue viviendo allá —este módulo solo la llama para
    que dar de alta un paciente y reservar su código sean una sola operación—.
    """
    try:  # como paquete (``from app import basedatos``)
        from . import codigos
    except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
        import codigos  # type: ignore[no-redef]
    return codigos


def buscar_pacientes(
    con: sqlite3.Connection, termino: str | None = "", limite: int = LIMITE_SUGERENCIAS
) -> list[sqlite3.Row]:
    """Autocompletado de pacientes: subcadena en nombre, cédula o código.

    Orden `veces_atendido DESC, ultima_vez DESC`, máximo 8 (§8). Con término
    vacío devuelve los más frecuentes, que es lo que conviene mostrar al
    entrar al campo. El código entra en la búsqueda porque es lo que el médico
    tiene a mano cuando mira un récipe o un informe impreso (dec. 1 y 2);
    `LIKE` es insensible a mayúsculas en ASCII, así que buscar `ec-1` alcanza.
    """
    if normalizar(termino):
        sql = """
            SELECT * FROM pacientes
            WHERE nombre_norm LIKE ? ESCAPE '\\'
               OR IFNULL(cedula, '') LIKE ? ESCAPE '\\'
               OR IFNULL(codigo, '') LIKE ? ESCAPE '\\'
            ORDER BY veces_atendido DESC, ultima_vez DESC, nombre_norm ASC
            LIMIT ?
        """
        patron = _patron_like(termino)
        parametros: tuple[Any, ...] = (patron, patron, patron, limite)
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


def obtener_paciente_por_codigo(con: sqlite3.Connection, codigo: str | None) -> sqlite3.Row | None:
    """El paciente dueño de un código (`EC-0001`). El código es único (dec. 1)."""
    codigo = limpiar(codigo)
    if not codigo:
        return None
    return con.execute("SELECT * FROM pacientes WHERE codigo = ?", (codigo,)).fetchone()


def obtener_ultimo_secuencial_paciente(con: sqlite3.Connection) -> int:
    """Último código de paciente reservado. 0 si todavía no hay ninguno.

    Espejo de `obtener_ultimo_secuencial`, pero sin año: el correlativo de
    pacientes es de por vida y no reinicia nunca (dec. 1).
    """
    fila = con.execute(
        "SELECT ultimo_secuencial FROM contador_pacientes WHERE id = 1"
    ).fetchone()
    return int(fila["ultimo_secuencial"]) if fila is not None else 0


def crear_paciente(
    con: sqlite3.Connection,
    nombre: str,
    cedula: str | None = None,
    fecha_nacimiento: str | None = None,
    edad: int | None = None,
    sexo: str | None = None,
    telefono: str | None = None,
    notas: str | None = None,
    codigo: str | None = None,
) -> int:
    """Da de alta un paciente y devuelve su id. La cédula vacía se guarda NULL.

    Le asigna además su **código de por vida** (`EC-0001`, dec. 1), en la misma
    transacción de escritura que el alta: si el insert falla, el número no
    queda quemado. `codigo` explícito es para casos de restauración; el flujo
    normal deja que lo asigne `codigos.asignar_codigo_paciente`.
    """
    nombre = limpiar(nombre)
    if not nombre:
        raise ValueError("El paciente necesita un nombre.")
    codigo = limpiar(codigo)
    with transaccion_si_hace_falta(con):
        if not codigo:
            codigo = _codigos().asignar_codigo_paciente(con)[1]
        momento = ahora_iso()
        cur = con.execute(
            """
            INSERT INTO pacientes (nombre, nombre_norm, codigo, cedula, fecha_nacimiento,
                                   edad, sexo, telefono, notas, veces_atendido, ultima_vez,
                                   creado_en, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
            """,
            (
                nombre, normalizar(nombre), codigo, limpiar(cedula) or None,
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
    de a poco) sin pisar los que ya tenían valor. Si no existe, lo crea —y al
    crearlo le asigna su código de por vida (dec. 1)—.
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
    """El récipe **más reciente** emitido con ese código.

    Desde la 2.0 el código es el del paciente y lo comparten todos sus récipes
    (dec. 2), así que un código ya no identifica un documento: para la lista
    completa está `listar_recipes_por_codigo`. Se sigue devolviendo uno solo
    porque es lo que necesitan las búsquedas rápidas y los códigos viejos
    —los que salieron impresos con la numeración por récipe— siguen siendo
    únicos y devuelven exactamente el suyo.
    """
    return con.execute(
        """
        SELECT * FROM recipes WHERE codigo = ?
         ORDER BY fecha_emision DESC, id DESC LIMIT 1
        """,
        (limpiar(codigo),),
    ).fetchone()


def listar_recipes_por_codigo(con: sqlite3.Connection, codigo: str) -> list[sqlite3.Row]:
    """Todos los récipes que llevan ese código, del más nuevo al más viejo."""
    return list(con.execute(
        """
        SELECT * FROM recipes WHERE codigo = ?
         ORDER BY fecha_emision DESC, id DESC
        """,
        (limpiar(codigo),),
    ))


def listar_recipes_de_paciente(
    con: sqlite3.Connection, paciente_id: int, incluir_anulados: bool = True
) -> list[sqlite3.Row]:
    """Los récipes de un paciente, del más nuevo al más viejo."""
    condicion = "" if incluir_anulados else "AND anulado = 0"
    return list(con.execute(
        f"""
        SELECT * FROM recipes WHERE paciente_id = ? {condicion}
         ORDER BY fecha_emision DESC, id DESC
        """,
        (paciente_id,),
    ))


def ultimo_recipe_de_paciente(
    con: sqlite3.Connection, paciente_id: int, incluir_anulados: bool = False
) -> sqlite3.Row | None:
    """El último récipe emitido a ese paciente.

    Es de donde sale el botón "volcar el tratamiento del último récipe" del
    informe (dec. 10): con el id en la mano, `obtener_items` da los renglones.
    """
    recipes = listar_recipes_de_paciente(con, paciente_id, incluir_anulados)
    return recipes[0] if recipes else None


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
    """Un renglón por medicamento recetado, para la segunda hoja del Excel (§9).

    Viaja también `recipe_id`: desde la 2.0 el `codigo` es el del paciente y se
    repite en todos sus récipes (dec. 2), así que hace falta el id para saber a
    cuál de ellos pertenece cada renglón.
    """
    return list(con.execute(
        """
        SELECT r.id AS recipe_id, r.codigo, r.fecha_emision, r.anulado,
               p.nombre AS paciente_nombre,
               ri.orden, ri.medicamento, ri.presentacion, ri.cantidad,
               ri.dosis, ri.indicaciones
          FROM recipe_items ri
          JOIN recipes r   ON r.id = ri.recipe_id
          JOIN pacientes p ON p.id = r.paciente_id
         ORDER BY r.fecha_emision DESC, r.id DESC, ri.orden ASC
        """
    ))


# --------------------------------------------------------------------------
# Historia clínica: piezas comunes
#
# Las seis tablas nuevas (historias, consultas, signos_vitales, anexos,
# mediciones, informes) se llenan y se corrigen igual: llegan diccionarios de
# la interfaz con algunos campos y hay que limpiarlos según su tipo antes de
# escribirlos. En vez de repetir seis veces el mismo bucle de `UPDATE`, cada
# tabla declara acá su lista de columnas editables con el tipo de limpieza que
# le corresponde, y esa lista es además lo que la interfaz puede leer para
# saber qué campos existen.
# --------------------------------------------------------------------------

_TEXTO = "texto"            # se colapsan los espacios; None queda en ''
_MULTILINEA = "multilinea"  # se respetan los renglones que escribió el médico
_ENTERO = "entero"          # vacío queda en NULL, no en 0
_REAL = "real"
_ID = "id"                  # clave foránea opcional

CAMPOS_HISTORIA: dict[str, str] = {
    "estado_civil": _TEXTO, "ocupacion": _TEXTO, "tipo_sangre": _TEXTO,
    "fam_madre": _MULTILINEA, "fam_padre": _MULTILINEA,
    "fam_hermanos": _MULTILINEA, "fam_hijos": _MULTILINEA,
    "alim_comidas_dia": _ENTERO, "alim_frutas_verduras": _ENTERO,
    "alim_pollo": _ENTERO, "alim_pescado": _ENTERO, "alim_carnes_rojas": _ENTERO,
    "alim_carbohidratos": _ENTERO, "alim_litros_agua": _ENTERO,
    "alimentacion_notas": _MULTILINEA, "habitacion": _MULTILINEA,
    "actividad_fisica": _MULTILINEA,
    "cronico_degenerativos": _MULTILINEA, "alcoholismo": _MULTILINEA,
    "tabaquismo": _MULTILINEA, "toxicomanias": _MULTILINEA,
    "quirurgicos": _MULTILINEA, "traumaticos": _MULTILINEA,
    "ginecologicos": _MULTILINEA, "hospitalizaciones": _MULTILINEA,
    "transfusiones": _MULTILINEA, "alergias": _MULTILINEA,
    "notas_generales": _MULTILINEA,
}

CAMPOS_CONSULTA: dict[str, str] = {
    "fecha": _TEXTO, "motivo": _MULTILINEA, "examen_fisico": _MULTILINEA,
    "evolucion": _MULTILINEA, "diagnostico": _MULTILINEA, "plan": _MULTILINEA,
}

CAMPOS_SIGNOS_VITALES: dict[str, str] = {
    "ta_sistolica": _ENTERO, "ta_diastolica": _ENTERO, "fc": _ENTERO, "fr": _ENTERO,
    "temperatura": _REAL, "tam": _REAL, "dxtx": _ENTERO, "tfg": _REAL,
    "spo2": _ENTERO, "peso": _REAL, "talla": _REAL, "imc": _REAL,
}

CAMPOS_ANEXO: dict[str, str] = {
    "consulta_id": _ID, "ruta_relativa": _TEXTO, "sha256": _TEXTO,
    "fecha_medicion": _TEXTO, "tipo": _TEXTO, "nota": _MULTILINEA,
    "ancho_px": _ENTERO, "alto_px": _ENTERO, "bytes": _ENTERO, "origen": _TEXTO,
}

CAMPOS_MEDICION: dict[str, str] = {
    "anexo_id": _ID, "fecha": _TEXTO, "peso": _REAL, "imc": _REAL,
    "grasa_pct": _REAL, "musculo_kg": _REAL, "grasa_visceral": _REAL,
}

CAMPOS_INFORME: dict[str, str] = {
    "consulta_id": _ID, "tipo": _TEXTO, "codigo_paciente": _TEXTO, "fecha": _TEXTO,
    "cuerpo": _MULTILINEA, "diagnostico": _MULTILINEA, "tratamiento": _MULTILINEA,
    "ciudad": _TEXTO, "especialidad": _TEXTO, "numero_poliza": _TEXTO,
    "prestacion_sanitaria": _TEXTO, "antecedentes": _MULTILINEA,
    "motivo_consulta": _MULTILINEA, "evolucion": _MULTILINEA,
}

#: Lista blanca: el nombre de tabla se interpola en el SQL de los ayudantes.
_ESQUEMAS: dict[str, dict[str, str]] = {
    "historias": CAMPOS_HISTORIA,
    "consultas": CAMPOS_CONSULTA,
    "signos_vitales": CAMPOS_SIGNOS_VITALES,
    "anexos": CAMPOS_ANEXO,
    "mediciones": CAMPOS_MEDICION,
    "informes": CAMPOS_INFORME,
}


def _valor(tipo: str, valor: Any) -> Any:
    """Limpia un valor según el tipo declarado en el esquema de su tabla."""
    if tipo == _TEXTO:
        return limpiar(valor)
    if tipo == _MULTILINEA:
        return limpiar_multilinea(valor)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo in (_ENTERO, _ID):
        return int(valor)
    return float(valor)


def _esquema(tabla: str) -> dict[str, str]:
    if tabla not in _ESQUEMAS:
        raise ValueError(f"Tabla desconocida: {tabla!r}")
    return _ESQUEMAS[tabla]


def _insertar(con: sqlite3.Connection, tabla: str, fijos: dict[str, Any],
              campos: dict[str, Any]) -> int:
    """INSERT con `creado_en`/`actualizado_en` y limpieza por tipo."""
    esquema = _esquema(tabla)
    datos: dict[str, Any] = dict(fijos)
    for clave, bruto in campos.items():
        if clave not in esquema:
            raise ValueError(f"{tabla}: no existe el campo {clave!r}.")
        datos[clave] = _valor(esquema[clave], bruto)
    momento = ahora_iso()
    datos["creado_en"] = momento
    datos["actualizado_en"] = momento
    columnas = ", ".join(datos)
    marcadores = ", ".join("?" * len(datos))
    cur = con.execute(
        f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})", list(datos.values())
    )
    return int(cur.lastrowid)


def _actualizar(con: sqlite3.Connection, tabla: str, columna_id: str, id_valor: Any,
                campos: dict[str, Any]) -> int:
    """UPDATE de los campos pasados. Devuelve cuántas filas cambió."""
    esquema = _esquema(tabla)
    asignaciones: list[str] = []
    valores: list[Any] = []
    for clave, bruto in campos.items():
        if clave not in esquema:
            raise ValueError(f"{tabla}: no existe el campo {clave!r}.")
        asignaciones.append(f"{clave} = ?")
        valores.append(_valor(esquema[clave], bruto))
    if not asignaciones:
        return 0
    asignaciones.append("actualizado_en = ?")
    valores.extend([ahora_iso(), id_valor])
    cur = con.execute(
        f"UPDATE {tabla} SET {', '.join(asignaciones)} WHERE {columna_id} = ?", valores
    )
    return int(cur.rowcount)


def _fecha(valor: Any) -> str:
    """Fecha en ISO, con las mismas reglas que la fecha de emisión del récipe."""
    return _codigos().normalizar_fecha(valor)


def calcular_imc(peso: float | None, talla: float | None) -> float | None:
    """IMC = peso / talla². Acepta la talla en metros o en centímetros.

    Se **guarda** el resultado (no se recalcula al mostrar): si el médico lo
    corrige a mano, gana lo que él escribió (Parte A §5.3 del análisis).
    """
    try:
        peso = float(peso)  # type: ignore[arg-type]
        talla = float(talla)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if peso <= 0 or talla <= 0:
        return None
    if talla > 3:  # vino en centímetros
        talla = talla / 100.0
    return round(peso / (talla * talla), 1)


def calcular_tam(sistolica: int | None, diastolica: int | None) -> float | None:
    """Tensión arterial media = (sistólica + 2 × diastólica) / 3."""
    try:
        sistolica = int(sistolica)  # type: ignore[arg-type]
        diastolica = int(diastolica)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if sistolica <= 0 or diastolica <= 0:
        return None
    return round((sistolica + 2 * diastolica) / 3.0, 1)


# --------------------------------------------------------------------------
# Historia: ficha y antecedentes (una vez por paciente, dec. 3)
# --------------------------------------------------------------------------

def obtener_historia(con: sqlite3.Connection, paciente_id: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM historias WHERE paciente_id = ?", (paciente_id,)
    ).fetchone()


def obtener_o_crear_historia(con: sqlite3.Connection, paciente_id: int) -> int:
    """Id de la historia del paciente, creándola vacía si todavía no está."""
    fila = obtener_historia(con, paciente_id)
    if fila is not None:
        return int(fila["id"])
    return _insertar(con, "historias", {"paciente_id": paciente_id}, {})


def guardar_historia(con: sqlite3.Connection, paciente_id: int, **campos: Any) -> int:
    """Crea o corrige la historia del paciente. Devuelve su id.

    Se guarda **solo lo que llega**: la pantalla edita de a una sección y lo
    que no se tocó no se pisa.
    """
    with transaccion_si_hace_falta(con):
        historia_id = obtener_o_crear_historia(con, paciente_id)
        if campos:
            _actualizar(con, "historias", "id", historia_id, campos)
        return historia_id


def tiene_alergias(con: sqlite3.Connection, paciente_id: int) -> str:
    """Las alergias del paciente, o `''`.

    Es lo único de la historia que puede hacer daño si no se ve, así que la
    pantalla las muestra fijas en el encabezado (Parte A §6 del análisis).
    """
    fila = obtener_historia(con, paciente_id)
    return limpiar_multilinea(fila["alergias"]) if fila is not None else ""


# --------------------------------------------------------------------------
# Historia: consultas y signos vitales (cada visita, dec. 3)
# --------------------------------------------------------------------------

def crear_consulta(
    con: sqlite3.Connection,
    paciente_id: int,
    fecha: Any = None,
    **campos: Any,
) -> int:
    """Abre una consulta y devuelve su id. Sin fecha, la de hoy."""
    campos["fecha"] = _fecha(fecha)
    return _insertar(con, "consultas", {"paciente_id": paciente_id}, campos)


def actualizar_consulta(con: sqlite3.Connection, consulta_id: int, **campos: Any) -> None:
    if "fecha" in campos:
        campos["fecha"] = _fecha(campos["fecha"])
    _actualizar(con, "consultas", "id", consulta_id, campos)


def obtener_consulta(con: sqlite3.Connection, consulta_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM consultas WHERE id = ?", (consulta_id,)).fetchone()


def listar_consultas(
    con: sqlite3.Connection, paciente_id: int, limite: int = 200
) -> list[sqlite3.Row]:
    """La línea de tiempo del paciente, de la visita más nueva a la más vieja.

    Trae de una vez lo que la lista colapsada muestra en cada renglón: los
    signos vitales de esa consulta y cuántos anexos, récipes e informes
    colgaron de ella.
    """
    return list(con.execute(
        """
        SELECT c.*, s.ta_sistolica, s.ta_diastolica, s.fc, s.fr, s.temperatura,
               s.tam, s.dxtx, s.tfg, s.spo2, s.peso, s.talla, s.imc,
               (SELECT COUNT(*) FROM anexos   a WHERE a.consulta_id = c.id) AS cantidad_anexos,
               (SELECT COUNT(*) FROM recipes  r WHERE r.consulta_id = c.id) AS cantidad_recipes,
               (SELECT COUNT(*) FROM informes i WHERE i.consulta_id = c.id) AS cantidad_informes
          FROM consultas c
          LEFT JOIN signos_vitales s ON s.consulta_id = c.id
         WHERE c.paciente_id = ?
         ORDER BY c.fecha DESC, c.id DESC
         LIMIT ?
        """,
        (paciente_id, limite),
    ))


def ultima_consulta(con: sqlite3.Connection, paciente_id: int) -> sqlite3.Row | None:
    """La visita más reciente. De acá salen el peso y la talla prellenados."""
    consultas = listar_consultas(con, paciente_id, limite=1)
    return consultas[0] if consultas else None


def obtener_signos_vitales(con: sqlite3.Connection, consulta_id: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM signos_vitales WHERE consulta_id = ?", (consulta_id,)
    ).fetchone()


def guardar_signos_vitales(con: sqlite3.Connection, consulta_id: int, **campos: Any) -> int:
    """Crea o corrige los signos vitales de la consulta (1 a 1). Devuelve su id.

    Si llegan peso y talla sin IMC, o TA sin TAM, se calculan y se guardan; si
    el médico los escribió a mano, gana lo suyo.

    La talla se guarda SIEMPRE en metros (la columna lo declara): si viene en
    centímetros (> 3, mismo umbral que calcular_imc) se convierte acá, para
    que la pantalla y el PDF de la historia — que rotulan "Talla (m)" — nunca
    impriman 164,00 bajo un rótulo en metros.
    """
    talla = campos.get("talla")
    if talla is not None:
        try:
            talla = float(talla)
        except (TypeError, ValueError):
            talla = None
        if talla is not None and talla > 3:
            campos["talla"] = round(talla / 100.0, 2)
    if not campos.get("imc"):
        calculado = calcular_imc(campos.get("peso"), campos.get("talla"))
        if calculado is not None:
            campos["imc"] = calculado
    if not campos.get("tam"):
        calculado = calcular_tam(campos.get("ta_sistolica"), campos.get("ta_diastolica"))
        if calculado is not None:
            campos["tam"] = calculado

    with transaccion_si_hace_falta(con):
        fila = obtener_signos_vitales(con, consulta_id)
        if fila is None:
            return _insertar(con, "signos_vitales", {"consulta_id": consulta_id}, campos)
        if campos:
            _actualizar(con, "signos_vitales", "id", int(fila["id"]), campos)
        return int(fila["id"])


def historico_signos_vitales(
    con: sqlite3.Connection, paciente_id: int, limite: int = 200
) -> list[sqlite3.Row]:
    """Los signos vitales de todas las visitas, de la más vieja a la más nueva.

    En ese orden porque es como se grafica la evolución de peso e IMC.
    """
    return list(con.execute(
        """
        SELECT s.*, c.fecha, c.motivo
          FROM signos_vitales s
          JOIN consultas c ON c.id = s.consulta_id
         WHERE c.paciente_id = ?
         ORDER BY c.fecha ASC, c.id ASC
         LIMIT ?
        """,
        (paciente_id, limite),
    ))


# --------------------------------------------------------------------------
# Anexos: las imágenes que llegan por WhatsApp (dec. 11)
# --------------------------------------------------------------------------

def crear_anexo(
    con: sqlite3.Connection,
    paciente_id: int,
    ruta_relativa: str,
    sha256: str,
    fecha_medicion: Any,
    tipo: str = "medicion",
    **campos: Any,
) -> int:
    """Registra una copia ya hecha en disco. Devuelve su id.

    Este módulo no copia archivos: eso es de la capa de arriba. Acá se guardan
    la ruta **relativa** a la carpeta de datos y el `sha256` del original, que
    es único —si el médico anexa dos veces la misma imagen, la base lo frena
    con `sqlite3.IntegrityError` y la bandeja puede avisarle—.

    `fecha_medicion` es la que el médico confirmó, nunca la del archivo: entre
    una y otra hubo cuatro días de diferencia en el ejemplo real.
    """
    ruta_relativa = limpiar(ruta_relativa)
    sha256 = limpiar(sha256).lower()
    if not ruta_relativa or not sha256:
        raise ValueError("El anexo necesita su ruta relativa y su sha256.")
    campos.update({
        "ruta_relativa": ruta_relativa,
        "sha256": sha256,
        "fecha_medicion": _fecha(fecha_medicion),
        "tipo": limpiar(tipo) or "medicion",
    })
    return _insertar(con, "anexos", {"paciente_id": paciente_id}, campos)


def actualizar_anexo(con: sqlite3.Connection, anexo_id: int, **campos: Any) -> None:
    if "fecha_medicion" in campos:
        campos["fecha_medicion"] = _fecha(campos["fecha_medicion"])
    _actualizar(con, "anexos", "id", anexo_id, campos)


def obtener_anexo(con: sqlite3.Connection, anexo_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM anexos WHERE id = ?", (anexo_id,)).fetchone()


def obtener_anexo_por_sha256(con: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    """Con qué paciente quedó ya anexado ese archivo. `None` si es nuevo."""
    sha256 = limpiar(sha256).lower()
    if not sha256:
        return None
    return con.execute("SELECT * FROM anexos WHERE sha256 = ?", (sha256,)).fetchone()


def sha256_anexados(con: sqlite3.Connection) -> set[str]:
    """Los hashes ya anexados: la bandeja los usa para no volver a ofrecerlos."""
    return {f["sha256"] for f in con.execute("SELECT sha256 FROM anexos")}


def listar_anexos(
    con: sqlite3.Connection, paciente_id: int, limite: int = 200
) -> list[sqlite3.Row]:
    return list(con.execute(
        """
        SELECT * FROM anexos WHERE paciente_id = ?
         ORDER BY fecha_medicion DESC, id DESC LIMIT ?
        """,
        (paciente_id, limite),
    ))


def listar_anexos_de_consulta(con: sqlite3.Connection, consulta_id: int) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT * FROM anexos WHERE consulta_id = ? ORDER BY fecha_medicion DESC, id DESC",
        (consulta_id,),
    ))


# --------------------------------------------------------------------------
# Mediciones: los valores clave tipeados a mano (dec. 13)
# --------------------------------------------------------------------------

def crear_medicion(
    con: sqlite3.Connection, paciente_id: int, fecha: Any = None, **campos: Any
) -> int:
    """Guarda peso, IMC, % de grasa, músculo y grasa visceral de una medición.

    Todo opcional: es un ofrecimiento al anexar la imagen, nunca un requisito.
    """
    campos["fecha"] = _fecha(fecha)
    return _insertar(con, "mediciones", {"paciente_id": paciente_id}, campos)


def actualizar_medicion(con: sqlite3.Connection, medicion_id: int, **campos: Any) -> None:
    if "fecha" in campos:
        campos["fecha"] = _fecha(campos["fecha"])
    _actualizar(con, "mediciones", "id", medicion_id, campos)


def obtener_medicion(con: sqlite3.Connection, medicion_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM mediciones WHERE id = ?", (medicion_id,)).fetchone()


def listar_mediciones(
    con: sqlite3.Connection, paciente_id: int, limite: int = 200
) -> list[sqlite3.Row]:
    """De la más vieja a la más nueva: es el orden del gráfico de evolución."""
    return list(con.execute(
        """
        SELECT * FROM mediciones WHERE paciente_id = ?
         ORDER BY fecha ASC, id ASC LIMIT ?
        """,
        (paciente_id, limite),
    ))


# --------------------------------------------------------------------------
# Informes (dec. 9 a 12)
# --------------------------------------------------------------------------

def crear_informe(
    con: sqlite3.Connection,
    paciente_id: int,
    tipo: str = "clinico",
    fecha: Any = None,
    anexos: Sequence[int] | None = None,
    **campos: Any,
) -> int:
    """Guarda un informe emitido y devuelve su id.

    `tipo` es `clinico` (la carta en prosa, plantilla B) o `aseguradora` (el
    formulario por campos, plantilla A). El código del paciente se copia
    literal en el momento de emitir, como los textos del récipe: si mañana
    cambia la ficha, el documento emitido no se mueve.

    `anexos` son los ids que el médico marcó para que salgan como páginas al
    final del PDF (dec. 12); se guardan para poder reimprimir el mismo PDF.
    """
    tipo = limpiar(tipo).lower() or "clinico"
    if tipo not in TIPOS_INFORME:
        raise ValueError(f"Tipo de informe desconocido: {tipo!r}. Es uno de {TIPOS_INFORME}.")
    with transaccion_si_hace_falta(con):
        if not limpiar(campos.get("codigo_paciente")):
            paciente = obtener_paciente(con, paciente_id)
            campos["codigo_paciente"] = (paciente["codigo"] or "") if paciente else ""
        campos["tipo"] = tipo
        campos["fecha"] = _fecha(fecha)
        informe_id = _insertar(con, "informes", {"paciente_id": paciente_id}, campos)
        if anexos:
            vincular_anexos_informe(con, informe_id, anexos)
        return informe_id


def actualizar_informe(con: sqlite3.Connection, informe_id: int, **campos: Any) -> None:
    if "fecha" in campos:
        campos["fecha"] = _fecha(campos["fecha"])
    if "tipo" in campos:
        tipo = limpiar(campos["tipo"]).lower()
        if tipo not in TIPOS_INFORME:
            raise ValueError(f"Tipo de informe desconocido: {tipo!r}.")
        campos["tipo"] = tipo
    _actualizar(con, "informes", "id", informe_id, campos)


def obtener_informe(con: sqlite3.Connection, informe_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM informes WHERE id = ?", (informe_id,)).fetchone()


def listar_informes(
    con: sqlite3.Connection, paciente_id: int, limite: int = 200
) -> list[sqlite3.Row]:
    return list(con.execute(
        """
        SELECT * FROM informes WHERE paciente_id = ?
         ORDER BY fecha DESC, id DESC LIMIT ?
        """,
        (paciente_id, limite),
    ))


def guardar_ruta_pdf_informe(con: sqlite3.Connection, informe_id: int, ruta_pdf: str) -> None:
    con.execute(
        "UPDATE informes SET ruta_pdf = ?, actualizado_en = ? WHERE id = ?",
        (str(ruta_pdf), ahora_iso(), informe_id),
    )


def anular_informe(
    con: sqlite3.Connection, informe_id: int, motivo: str, cuando: str | None = None
) -> None:
    """Como los récipes: se anula con motivo escrito, nunca se borra (§2.4)."""
    motivo = limpiar(motivo)
    if not motivo:
        raise ValueError("La anulación exige un motivo escrito.")
    momento = cuando or ahora_iso()
    cur = con.execute(
        """
        UPDATE informes
           SET anulado = 1, motivo_anulacion = ?, fecha_anulacion = ?, actualizado_en = ?
         WHERE id = ? AND anulado = 0
        """,
        (motivo, momento, momento, informe_id),
    )
    if cur.rowcount == 0:
        raise ValueError("El informe no existe o ya estaba anulado.")


def vincular_anexos_informe(
    con: sqlite3.Connection, informe_id: int, anexo_ids: Sequence[int]
) -> None:
    """Deja el informe con exactamente esos anexos, en ese orden (dec. 12)."""
    momento = ahora_iso()
    with transaccion_si_hace_falta(con):
        con.execute("DELETE FROM informe_anexos WHERE informe_id = ?", (informe_id,))
        for orden, anexo_id in enumerate(anexo_ids, start=1):
            con.execute(
                """
                INSERT INTO informe_anexos (informe_id, anexo_id, orden, creado_en)
                VALUES (?, ?, ?, ?)
                """,
                (informe_id, int(anexo_id), orden, momento),
            )


def listar_anexos_de_informe(con: sqlite3.Connection, informe_id: int) -> list[sqlite3.Row]:
    return list(con.execute(
        """
        SELECT a.*, ia.orden
          FROM informe_anexos ia
          JOIN anexos a ON a.id = ia.anexo_id
         WHERE ia.informe_id = ?
         ORDER BY ia.orden ASC
        """,
        (informe_id,),
    ))


def anexos_por_informe(
    con: sqlite3.Connection, informe_ids: Sequence[int]
) -> dict[int, int]:
    """Cuántos anexos lleva cada informe, en una sola consulta.

    Es el `📎2` de la lista de informes de la historia: se necesita para todos
    los informes del paciente a la vez, y pedirlos de a uno sería una consulta
    por renglón. Mismo criterio que `medicamentos_por_recipe`.

    Los informes sin anexos vienen igual, con cero: quien llama arma la lista
    sin tener que preguntarse si la clave está.
    """
    ids = [int(i) for i in informe_ids]
    if not ids:
        return {}
    marcadores = ",".join("?" * len(ids))
    cuenta: dict[int, int] = {i: 0 for i in ids}
    for fila in con.execute(
        f"""
        SELECT informe_id, COUNT(*) AS cuantos
          FROM informe_anexos
         WHERE informe_id IN ({marcadores})
         GROUP BY informe_id
        """,
        ids,
    ):
        cuenta[int(fila["informe_id"])] = int(fila["cuantos"])
    return cuenta


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
