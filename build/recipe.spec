# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado de «Récipes — Espacio Corporal» (§11.1).

    py -3 -m PyInstaller build/recipe.spec --noconfirm \
        --distpath build/dist --workpath build/tmp

Resultado: `build/dist/RecipesMedicos/RecipesMedicos.exe` más la carpeta
`_internal/` con Python, las bibliotecas, la interfaz y los recursos.

Tres decisiones que no se cambian sin releer §11:

1. **`--onedir`, nunca `--onefile`.** `--onefile` descomprime todo en `%TEMP%`
   en cada arranque (lento) y es el patrón que más falsos positivos dispara en
   Windows Defender. Una carpeta con archivos a la vista arranca al toque y se
   deja revisar.
2. **`--windowed`**: la app es una ventana, no una terminal. Por eso el punto
   de entrada es `lanzador.py`, que le tapa el agujero de `stdout`/`stderr`.
3. **Sin red, nada que descargar** (§2.1): la interfaz, el logo y las cuatro
   Lato viajan adentro del paquete.

Exclusiones: `numpy` y `PyMuPDF` (`fitz`) están instalados en la máquina de
desarrollo —se usaron para medir el PDF modelo en la Fase 0 y para verificar los
PDF en las pruebas— pero **ningún módulo de `app/` los importa** (verificado
sobre los `import` de los diez módulos). Adentro del paquete solo sumarían
decenas de megas. `tkinter` tampoco: la ventana la pone pywebview.

`Pillow` sí viaja adentro desde la 2.0: la bandeja de mediciones y los anexos lo
usan en caliente (miniaturas, medidas y orientación EXIF) y la página de anexo
del informe también. Se importa con `from PIL import Image` adentro de las
funciones, así que PyInstaller lo detecta solo; no hace falta listarlo.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

RAIZ = os.path.dirname(SPECPATH)          # SPECPATH = <raíz>/build
APP = os.path.join(RAIZ, "app")
RECURSOS = os.path.join(RAIZ, "recursos")

# --- lo que viaja adentro -------------------------------------------------
# Destino relativo a `_internal/`, que es lo que `sys._MEIPASS` apunta con
# `--onedir`; `rutas.py`, `pdf_recipe.py` y `main.py` lo resuelven así.
datas = [
    (os.path.join(APP, "web"), "web"),                       # index/estilos/js
    (os.path.join(RECURSOS, "logo.png"), "recursos"),        # encabezado del PDF
    (os.path.join(RECURSOS, "firma.png"), "recursos"),       # firma del informe (dec. 9)
    (os.path.join(RECURSOS, "fuentes"), "recursos/fuentes"), # Lato embebida
    # 2.1: las dos láminas anatómicas del mapa de infiltraciones y el catálogo
    # de 35 puntos. Van como archivos, no horneadas en base64 adentro del HTML
    # como en el programa suelto del que salieron: acá la interfaz corre sobre
    # http://127.0.0.1 y las pide con un <img src> normal.
    (os.path.join(RECURSOS, "infiltraciones"), "recursos/infiltraciones"),
]
# Perfil de color sRGB de fpdf2: no lo detecta el análisis de imports.
datas += collect_data_files("fpdf")

hiddenimports = [
    # `app/` es un paquete de espacio de nombres (sin `__init__.py`) y los
    # módulos se importan con un `try` relativo y un `except` plano: se listan
    # a mano para que el análisis no se pierda ninguna de las dos ramas.
    "app",
    "app.main",
    "app.basedatos",
    "app.codigos",
    "app.excel",
    "app.pdf_comun",
    "app.pdf_examenes",
    "app.pdf_historia",
    "app.pdf_infiltraciones",
    "app.pdf_informe",
    "app.pdf_recipe",
    "app.respaldo",
    "app.rutas",
]

excludes = [
    "numpy",            # solo desarrollo
    "fitz",             # PyMuPDF: solo desarrollo (medición del PDF modelo)
    "pymupdf",
    "fitz_old",
    "tkinter",          # la ventana la pone pywebview
    "tests",            # la suite no se distribuye
    "test_basedatos_2_1",
    "test_codigos",     # los tests viven al lado de `app/` y comparten pathex:
    "test_examenes_api",
    "test_excel",       # se nombran uno por uno para que ninguno se cuele
    "test_historia",
    "test_infiltraciones_api",
    "test_pdf_comun",
    "test_pdf_examenes",
    "test_pdf_historia",
    "test_pdf_infiltraciones",
    "test_pdf_informe",
    "test_pdf_recipe",
    "test_respaldo",
    "test_rutas",
    "matplotlib",
    "pandas",
    "scipy",
    "IPython",
    "pytest",
    "setuptools",
    "pip",
]


a = Analysis(
    [os.path.join(RAIZ, "build", "lanzador.py")],
    pathex=[RAIZ, APP],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RecipesMedicos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX es otra bandera roja para los antivirus
    console=False,           # --windowed (§11.1)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(RAIZ, "build", "icono.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RecipesMedicos",   # --onedir: build/dist/RecipesMedicos/ (§11.1)
)
