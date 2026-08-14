# -*- coding: utf-8 -*-
"""Punto de entrada del ejecutable congelado (PyInstaller, §11.1).

Existe por una sola razón: `--windowed` deja la app **sin consola**, y ahí
Windows no le da a Python ni `stdout` ni `stderr`. `sys.stdout` queda en `None`
y cualquier `sys.stdout.flush()` —el que hace `--solo-servidor`— o cualquier
`logging` de werkzeug reventaría con `AttributeError` antes de servir la primera
página. Se enchufa el vacío del sistema y recién ahí se llama a `app.main`, que
queda igual que corriendo desde el código fuente:

    RecipesMedicos.exe                                   # ventana normal
    RecipesMedicos.exe --solo-servidor --puerto 5411 --no-abrir-pdf

Ninguna otra diferencia con `py -3 -m app.main`: mismos argumentos, misma
carpeta de datos (`RECIPES_DIR` o `Documents\\Recipes`), cero red.
"""

import os
import sys


def _consola_muda() -> None:
    """`--windowed` no da consola: sin esto, el primer `print` de un módulo
    de terceros que no tolere `None` tumbaría la app."""
    for nombre in ("stdout", "stderr"):
        if getattr(sys, nombre, None) is None:
            try:
                setattr(sys, nombre, open(os.devnull, "w", encoding="utf-8"))
            except OSError:  # pragma: no cover - disco en un estado muy raro
                pass


if __name__ == "__main__":
    _consola_muda()
    from app.main import main

    raise SystemExit(main())
