# -*- coding: utf-8 -*-
"""Arranque de la app: carpeta de datos, Flask local y ventana pywebview.

Uso normal (lo que hace el acceso directo del escritorio)::

    py -3 -m app.main

Modo depuración, sin ventana, para el integrador y el dueño del proyecto::

    py -3 -m app.main --solo-servidor            # puerto libre al azar
    py -3 -m app.main --solo-servidor --puerto 5000

La carpeta de datos es ``%USERPROFILE%\\Documents\\Recipes`` y se puede mover
con la variable de entorno ``RECIPES_DIR`` (la usan los tests y, más adelante,
el cambio de carpeta desde Configuración, §7-C).

Restricciones que este módulo hace cumplir (§2 y §3):

- Flask escucha **solo** en ``127.0.0.1``, nunca en ``0.0.0.0``.
- El puerto es libre y al azar: lo elige el sistema operativo (bind al 0).
- No hay ni una llamada de red hacia afuera: ni CDN, ni fuentes remotas, ni
  verificación de actualizaciones, ni telemetría.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

try:  # como paquete (``py -3 -m app.main``)
    from . import basedatos, respaldo, rutas
except ImportError:  # ejecutado con ``app/`` en el sys.path (tests, scripts)
    import basedatos  # type: ignore[no-redef]
    import respaldo  # type: ignore[no-redef]
    import rutas  # type: ignore[no-redef]


# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

TITULO_VENTANA = "Récipes — Espacio Corporal"
ANCHO_VENTANA = 1200
ALTO_VENTANA = 800

def _raiz_recursos() -> Path:
    """Raíz de los archivos empaquetados (acá se usa para `recursos/logo.png`).

    Desde el código fuente, la raíz del proyecto. Congelado con PyInstaller
    `--onedir` (§11.1), lo que trajo `--add-data` vive en ``sys._MEIPASS``: la
    carpeta ``_internal`` que queda al lado del `.exe`.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


#: Raíz del proyecto (o de la carpeta instalada por PyInstaller `--onedir`).
RAIZ_PROYECTO = _raiz_recursos()

#: Subcarpetas de la carpeta de datos del médico (§4). Sin tildes ni eñes.
SUBCARPETAS = ("datos", "pdf", "registro", "respaldos", "recursos")

#: Recursos que se copian a la carpeta del médico en el primer arranque, para
#: que pueda reemplazarlos desde Configuración sin tocar la instalación.
RECURSOS_A_COPIAR = ("logo.png",)


# --------------------------------------------------------------------------
# Carpeta de datos
# --------------------------------------------------------------------------

def carpeta_datos() -> Path:
    """Dónde viven los datos del médico.

    ``RECIPES_DIR`` gana si está definida; si no,
    ``%USERPROFILE%\\Documents\\Recipes`` (§4).
    """
    desde_entorno = os.environ.get("RECIPES_DIR", "").strip()
    if desde_entorno:
        return Path(desde_entorno).expanduser().resolve()
    base = Path(os.environ.get("USERPROFILE") or Path.home())
    return base / "Documents" / "Recipes"


def preparar_carpeta_datos(destino: Path | None = None) -> Path:
    """Crea la estructura del primer arranque y devuelve la carpeta usada.

    Crea ``datos\\``, ``pdf\\``, ``registro\\``, ``respaldos\\`` y
    ``recursos\\``, y copia el logo empaquetado a ``recursos\\`` si todavía no
    está. Es idempotente: correrla en cada arranque no pisa nada. **Nunca**
    sobrescribe un recurso que el médico ya cambió (§11.3: instalar encima
    deja los datos intactos).
    """
    destino = Path(destino) if destino is not None else carpeta_datos()
    for sub in SUBCARPETAS:
        (destino / sub).mkdir(parents=True, exist_ok=True)

    for nombre in RECURSOS_A_COPIAR:
        origen = RAIZ_PROYECTO / "recursos" / nombre
        copia = destino / "recursos" / nombre
        if origen.is_file() and not copia.exists():
            shutil.copyfile(origen, copia)
    return destino


def pin_configurado(con: sqlite3.Connection) -> bool:
    """¿Hay un PIN guardado en `config`? (§10)

    Con PIN, la interfaz arranca en la pantalla de bloqueo y pregunta por
    ``/api/pin/verificar``; sin PIN, abre derecho al formulario. El backend no
    tiene sesión ni middleware: es una barrera visual, no seguridad fuerte
    (§10), y la API escucha solo en 127.0.0.1.
    """
    return bool(basedatos.obtener_config(con, rutas.CLAVE_PIN))


def respaldo_de_la_semana(con: sqlite3.Connection, dir_datos: Path) -> None:
    """Respalda si esta semana todavía no hubo respaldo (§10).

    Corre al arrancar y **nunca impide abrir la app**: un disco lleno, una
    carpeta sincronizando o un antivirus mordiendo el ZIP no pueden dejar al
    médico sin poder emitir. Si falla, se anota en la consola y la semana queda
    pendiente: el próximo arranque lo reintenta, porque la marca en `config`
    se guarda recién con el ZIP escrito.
    """
    try:
        resultado = respaldo.toca_respaldo_semanal(con, dir_datos)
    except Exception as err:  # incluye RespaldoError y cualquier OSError
        print(f"Respaldo semanal: no se pudo hacer ({err}). Se reintenta al "
              "próximo arranque.")
        return
    if resultado["hecho"]:
        print(f"Respaldo semanal: {resultado['archivo']}")
        if resultado["eliminados"]:
            print(f"  respaldos viejos borrados: {len(resultado['eliminados'])}")
    else:
        print(f"Respaldo semanal: {resultado['motivo']} "
              f"(último: {resultado['ultimo_respaldo'] or 'ninguno'})")


# --------------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------------

def crear_servidor(app, puerto: int = 0):
    """Servidor werkzeug atado a `127.0.0.1`, nunca a `0.0.0.0` (§3).

    Con `puerto=0` lo elige el sistema operativo. Se devuelve ya escuchando,
    así que cuando la ventana abra la URL el socket ya está aceptando: no hay
    carrera ni pantalla en blanco del primer intento.
    """
    from werkzeug.serving import make_server

    return make_server("127.0.0.1", puerto, app, threaded=True)


def arrancar(dir_datos: Path, puerto: int = 0) -> tuple[Any, str]:
    """Deja el servidor corriendo en un hilo y devuelve `(servidor, url)`."""
    app = rutas.crear_app(dir_datos)
    servidor = crear_servidor(app, puerto)
    hilo = threading.Thread(target=servidor.serve_forever,
                            name="flask-recipes", daemon=True)
    hilo.start()
    return servidor, f"http://127.0.0.1:{servidor.server_port}"


# --------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------

def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="app.main", description="Récipes — Espacio Corporal",
    )
    analizador.add_argument(
        "--solo-servidor", action="store_true",
        help="Corre Flask sin ventana e imprime la URL (depuración).",
    )
    analizador.add_argument(
        "--puerto", type=int, default=0,
        help="Puerto fijo. Por defecto, uno libre que elige el sistema.",
    )
    analizador.add_argument(
        "--no-abrir-pdf", action="store_true",
        help="No abrir el PDF en el visor al guardar (pruebas automáticas).",
    )
    return analizador.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    opciones = _argumentos(argv)
    if opciones.no_abrir_pdf:
        os.environ["RECIPES_ABRIR_PDF"] = "0"

    dir_datos = preparar_carpeta_datos()

    # Primer toque a la base: crea el archivo y aplica las migraciones, para
    # que el primer pedido de la interfaz no encuentre una base a medias.
    con = basedatos.inicializar(dir_datos / "datos" / "recipes.db")
    try:
        # Primer arranque de la semana: ZIP de datos\ y registro\ (§10).
        respaldo_de_la_semana(con, dir_datos)
        # Si hay PIN, la interfaz arranca en la pantalla de bloqueo (§10).
        pin_configurado(con)
    finally:
        con.close()

    servidor, url = arrancar(dir_datos, opciones.puerto)

    if opciones.solo_servidor:
        print(f"Carpeta de datos: {dir_datos}")
        print(f"Servidor: {url}")
        print("Ctrl+C para cortar.")
        sys.stdout.flush()
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            servidor.shutdown()
        return 0

    import webview  # se importa acá para que --solo-servidor no lo necesite

    webview.create_window(TITULO_VENTANA, url,
                          width=ANCHO_VENTANA, height=ALTO_VENTANA)
    try:
        webview.start()
    finally:
        servidor.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
