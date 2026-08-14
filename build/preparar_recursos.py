# -*- coding: utf-8 -*-
"""
Preparacion de los recursos graficos del proyecto (Fase 0b).

Implementa al pie de la letra la seccion 5 de la PARTE B de
`build/analisis-modelo.md`:

  * 5.1  Dos recortes de `referencias/Logo.jpg`:
           - recursos/logo.png           simbolo + "espacio CORPORAL"  (156,141)-(868,702)
           - recursos/logo_completo.png  lockup entero con bajada      (155,138)-(869,868)
  * 5.2  Sin reescalar: recorte 1:1, cero resampleo.
  * 5.3  Limpieza de fondo en dos pasos, sin tocar los pixeles < 242:
           1) luminancia >= 242  ->  R = G = B = luminancia   (mata el halo de croma 4:2:0)
           2) luminancia >= 252  ->  #FFFFFF exacto
  * 5.4  PNG-24 (RGB), sin canal alfa, sin perfil ICC, sin EXIF ni texto.
  * 5.6  build/icono.ico: simbolo solo (330,142)-(664,469), cuadrado con blanco,
         multirresolucion 16/32/48/64/128/256.

OJO: esto es un paso de preparacion de recurso que se corre a mano una sola vez.
NO es codigo de la app: Pillow y NumPy no entran en las dependencias de la seccion 3
de las instrucciones.

Uso:  py -3 "build/preparar_recursos.py"
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "referencias" / "Logo.jpg"
DIR_RECURSOS = RAIZ / "recursos"
DIR_BUILD = RAIZ / "build"

SALIDA_LOGO = DIR_RECURSOS / "logo.png"
SALIDA_LOGO_COMPLETO = DIR_RECURSOS / "logo_completo.png"
SALIDA_ICONO = DIR_BUILD / "icono.ico"

# --------------------------------------------------------------------------
# Cajas de recorte (analisis 5.1 y 5.6)
#
# Las cajas del analisis estan expresadas con AMBOS extremos INCLUSIVOS:
#   (156,141)-(868,702)  ->  868-156+1 = 713 px  x  702-141+1 = 562 px
# que es exactamente el tamano documentado (713 x 562). Por eso al pasarlas a
# Pillow -- que usa el extremo derecho/inferior EXCLUSIVO -- se les suma 1.
# --------------------------------------------------------------------------

CAJA_LOGO = (156, 141, 868, 702)            # simbolo + "espacio CORPORAL"
CAJA_LOGO_COMPLETO = (155, 138, 869, 868)   # lockup entero, con "Salud y Bienestar"
CAJA_SIMBOLO = (330, 142, 664, 469)         # solo el cuadrado verde con la "e"

TAMANOS_ICO = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# Umbrales de la limpieza de fondo (5.3)
UMBRAL_NEUTRALIZAR = 242
UMBRAL_BLANCO = 252

# Verificacion: desviacion de croma tolerada en los casi-blancos
MAX_DESVIACION_CROMA = 6


def caja_pillow(caja_inclusiva: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Convierte una caja de extremos inclusivos a la convencion de Pillow."""
    x0, y0, x1, y1 = caja_inclusiva
    return (x0, y0, x1 + 1, y1 + 1)


def luminancia(arr: np.ndarray) -> np.ndarray:
    """Luminancia Rec.601 (la misma que usa Pillow al convertir a 'L')."""
    return (
        0.299 * arr[:, :, 0].astype(np.float64)
        + 0.587 * arr[:, :, 1].astype(np.float64)
        + 0.114 * arr[:, :, 2].astype(np.float64)
    )


def limpiar_fondo(arr: np.ndarray) -> tuple[np.ndarray, dict]:
    """
    Limpieza de fondo de la seccion 5.3, en orden y sin tocar nada por debajo de 242.

    1. luminancia >= 242  ->  gris neutro del valor de la luminancia
    2. luminancia >= 252  ->  blanco puro #FFFFFF
    """
    lum = luminancia(arr)
    salida = arr.copy()

    mascara_neutralizar = lum >= UMBRAL_NEUTRALIZAR
    gris = np.clip(np.rint(lum), 0, 255).astype(np.uint8)
    for canal in range(3):
        salida[:, :, canal] = np.where(mascara_neutralizar, gris, salida[:, :, canal])

    mascara_blanco = lum >= UMBRAL_BLANCO
    salida[mascara_blanco] = 255

    # Estadistica solo informativa
    croma_antes = arr.max(axis=2).astype(np.int16) - arr.min(axis=2).astype(np.int16)
    stats = {
        "pixeles": int(arr.shape[0] * arr.shape[1]),
        "neutralizados": int(mascara_neutralizar.sum()),
        "blanqueados": int(mascara_blanco.sum()),
        "intactos": int((~mascara_neutralizar).sum()),
        "halo_antes": int((mascara_neutralizar & (croma_antes > MAX_DESVIACION_CROMA)).sum()),
    }
    return salida, stats


def guardar_png(arr: np.ndarray, destino: Path) -> None:
    """PNG-24 RGB, sin alfa, sin ICC, sin EXIF ni texto."""
    # Se construye una imagen nueva a partir del array: asi el diccionario `info`
    # nace vacio y Pillow no arrastra el perfil ICC del JPEG de origen.
    imagen = Image.frombytes("RGB", (arr.shape[1], arr.shape[0]), arr.tobytes())
    assert not imagen.info, f"la imagen arrastra metadatos: {sorted(imagen.info)}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(destino, format="PNG", optimize=True)


def cuadrar_con_blanco(arr: np.ndarray) -> np.ndarray:
    """Centra el recorte en un lienzo cuadrado de blanco puro."""
    alto, ancho = arr.shape[:2]
    lado = max(alto, ancho)
    lienzo = np.full((lado, lado, 3), 255, dtype=np.uint8)
    y = (lado - alto) // 2
    x = (lado - ancho) // 2
    lienzo[y : y + alto, x : x + ancho] = arr
    return lienzo


def guardar_ico(arr_cuadrado: np.ndarray, destino: Path) -> list[tuple[int, int]]:
    """
    ICO multirresolucion 16/32/48/64/128/256 (5.6).

    Cada resolucion se reduce con LANCZOS desde el cuadrado a tamano nativo y
    DESPUES se le vuelve a pasar la limpieza de 5.3: el remuestreo mezcla el verde
    del simbolo con el blanco del fondo y reintroduce halo de croma en los
    casi-blancos, asi que hay que neutralizarlo resolucion por resolucion.
    """
    base = Image.frombytes(
        "RGB", (arr_cuadrado.shape[1], arr_cuadrado.shape[0]), arr_cuadrado.tobytes()
    )
    marcos = []
    for tam in TAMANOS_ICO:
        reducido = np.asarray(
            base.resize(tam, Image.Resampling.LANCZOS), dtype=np.uint8
        )
        limpio, _ = limpiar_fondo(reducido)
        marcos.append(
            Image.frombytes("RGB", (limpio.shape[1], limpio.shape[0]), limpio.tobytes())
        )

    # La imagen base tiene que ser la grande: Pillow descarta toda resolucion
    # mayor que `im.size`. Los marcos ya limpios van en `append_images` y Pillow
    # los usa tal cual porque coinciden exacto con cada tamano pedido.
    destino.parent.mkdir(parents=True, exist_ok=True)
    base.save(
        destino,
        format="ICO",
        sizes=TAMANOS_ICO,
        append_images=marcos,
    )
    return TAMANOS_ICO


def main() -> int:
    if not ORIGEN.exists():
        print(f"ERROR: no encuentro el origen {ORIGEN}", file=sys.stderr)
        return 1

    with Image.open(ORIGEN) as original:
        original.load()
        print(f"Origen : {ORIGEN}")
        print(f"         {original.size[0]} x {original.size[1]} px, modo {original.mode}, "
              f"ICC {'si' if original.info.get('icc_profile') else 'no'}")
        base = original.convert("RGB")
        arr_original = np.asarray(base, dtype=np.uint8)

    tareas = [
        ("recursos/logo.png", CAJA_LOGO, SALIDA_LOGO, False),
        ("recursos/logo_completo.png", CAJA_LOGO_COMPLETO, SALIDA_LOGO_COMPLETO, False),
        ("build/icono.ico", CAJA_SIMBOLO, SALIDA_ICONO, True),
    ]

    for nombre, caja, destino, es_icono in tareas:
        x0, y0, x1, y1 = caja_pillow(caja)
        recorte = arr_original[y0:y1, x0:x1]           # 5.2: recorte 1:1, sin resampleo
        limpio, stats = limpiar_fondo(recorte)         # 5.3

        if es_icono:
            limpio = cuadrar_con_blanco(limpio)        # 5.6
            guardar_ico(limpio, destino)
        else:
            guardar_png(limpio, destino)               # 5.4

        print(
            f"\n{nombre}\n"
            f"  caja inclusiva {caja} -> {limpio.shape[1]} x {limpio.shape[0]} px\n"
            f"  pixeles intactos (<{UMBRAL_NEUTRALIZAR}): {stats['intactos']:,}"
            f" | neutralizados (>={UMBRAL_NEUTRALIZAR}): {stats['neutralizados']:,}"
            f" | blanco puro (>={UMBRAL_BLANCO}): {stats['blanqueados']:,}\n"
            f"  halo de croma previo (casi-blancos con desviacion >{MAX_DESVIACION_CROMA}): "
            f"{stats['halo_antes']:,}\n"
            f"  peso: {destino.stat().st_size:,} bytes"
        )

    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
