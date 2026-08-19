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

Y, para la evolucion 2.0 (informe medico firmado, decision 9):

  * F.1  recursos/firma.png: la firma escaneada del Dr. Eleazar Shiera Bastidas,
         extraida de `referencias/informe medico plantilla.docx` (un .docx es un ZIP:
         la imagen vive en `word/media/image2.png`, 86.249 bytes, md5 4b544560...).
         Misma limpieza de fondo de 5.3 (umbrales 242/252, nada por debajo de 242 se
         toca) + blanqueo de las motas grises que quedan lejos de todo trazo, y
         mismo formato de 5.4 (PNG-24 RGB, sin alfa, sin metadatos).
         Ver las notas al pie de este archivo para las decisiones de recorte y fondo.

OJO: esto es un paso de preparacion de recurso que se corre a mano una sola vez.
NO es codigo de la app: Pillow y NumPy no entran en las dependencias de la seccion 3
de las instrucciones.

Uso:  py -3 "build/preparar_recursos.py"
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
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

# Firma escaneada (F.1)
ORIGEN_FIRMA_DOCX = RAIZ / "referencias" / "informe medico plantilla.docx"
MIEMBRO_FIRMA = "word/media/image2.png"
FIRMA_BYTES = 86_249
FIRMA_MD5 = "4b544560adf8674790971f2b3b9d5d1c"
FIRMA_TAMANO = (753, 321)
# La plantilla coloca esa imagen entera a 86,8 x 37,0 mm => 220,4 px/pulgada.
FIRMA_DPI_PLANTILLA = 753 / (86.8 / 25.4)
SALIDA_FIRMA = DIR_RECURSOS / "firma.png"

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

# Hasta cuantos px de un trazo se considera antialias (se conserva) y no fondo
RADIO_ANTIALIAS = 2


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


def extraer_firma(docx: Path) -> np.ndarray:
    """
    Saca `word/media/image2.png` del .docx de referencia y lo devuelve como RGB.

    Un .docx es un ZIP: no hace falta python-docx ni ninguna dependencia nueva.
    Se verifica tamano en bytes + md5 + dimensiones para no confundirla con
    `image1.png`, que es el logo de la clinica (86.917 bytes, md5 9446f437...).

    El PNG viene en RGBA pero con el canal alfa COMPLETAMENTE opaco (255 en los
    241.713 pixeles): el "quitar fondo" de Word no esta en el PNG sino en el
    `hdphoto1.wdp` que lo acompana, y su residuo si quedo horneado en el RGB como
    un velo amarillento (pixeles R=G=255 con B entre 224 y 254). Ese velo es lo
    que limpia `limpiar_fondo()`.
    """
    with zipfile.ZipFile(docx) as z:
        crudo = z.read(MIEMBRO_FIRMA)

    md5 = hashlib.md5(crudo).hexdigest()
    assert len(crudo) == FIRMA_BYTES, f"{MIEMBRO_FIRMA}: {len(crudo)} bytes, esperaba {FIRMA_BYTES}"
    assert md5 == FIRMA_MD5, f"{MIEMBRO_FIRMA}: md5 {md5}, esperaba {FIRMA_MD5}"

    with Image.open(io.BytesIO(crudo)) as imagen:
        imagen.load()
        assert imagen.size == FIRMA_TAMANO, f"firma: {imagen.size}, esperaba {FIRMA_TAMANO}"
        alfa = np.asarray(imagen.getchannel("A"), dtype=np.uint8) if "A" in imagen.getbands() else None
        rgb = np.asarray(imagen.convert("RGB"), dtype=np.uint8)

    if alfa is not None:
        assert int(alfa.min()) == 255, "la firma trae alfa parcial; revisar antes de aplanar"
    return rgb


def caja_de_tinta(arr: np.ndarray, umbral: int = UMBRAL_NEUTRALIZAR) -> tuple[int, int, int, int]:
    """
    Caja inclusiva de la tinta: todo pixel con luminancia < `umbral`.

    Se calcula SOBRE LA IMAGEN YA LIMPIA, asi el velo amarillento del recorte de
    Word (que llega hasta el borde del lienzo) no infla la caja.
    """
    tinta = luminancia(arr) < umbral
    filas = np.nonzero(tinta.any(axis=1))[0]
    columnas = np.nonzero(tinta.any(axis=0))[0]
    return (int(columnas[0]), int(filas[0]), int(columnas[-1]), int(filas[-1]))


def dilatar(mascara: np.ndarray, radio: int) -> np.ndarray:
    """Dilatacion cuadrada (Chebyshev) de una mascara booleana."""
    salida = mascara.copy()
    for dy in range(-radio, radio + 1):
        for dx in range(-radio, radio + 1):
            salida |= np.roll(np.roll(mascara, dy, axis=0), dx, axis=1)
    return salida


def blanquear_campo_abierto(arr: np.ndarray, radio: int = RADIO_ANTIALIAS) -> tuple[np.ndarray, int]:
    """
    Tercer paso, solo para la firma: fondo BLANCO PURO de verdad.

    Despues de 5.3 el fondo abierto ya quedo blanco casi entero, pero sobreviven
    unas motas grises de 247-251 (restos del escaneo y del recorte de Word) que
    no llegan al umbral de blanqueo de 252. Se fuerzan a blanco SOLO si ademas
    estan a mas de `radio` px de cualquier trazo. Por construccion este paso no
    puede comerse tinta: opera unicamente sobre pixeles con luminancia >= 242,
    que es justo el piso que 5.3 declara intocable.
    """
    lum = luminancia(arr)
    tinta = lum < UMBRAL_NEUTRALIZAR
    campo_abierto = ~dilatar(tinta, radio)
    blanco_puro = (arr[:, :, 0] == 255) & (arr[:, :, 1] == 255) & (arr[:, :, 2] == 255)
    objetivo = campo_abierto & ~blanco_puro

    salida = arr.copy()
    salida[objetivo] = 255
    return salida, int(objetivo.sum())


def auditar_fondo(arr: np.ndarray) -> dict:
    """Verificacion posterior a la limpieza: que no quede halo ni fondo sucio."""
    lum = luminancia(arr)
    croma = arr.max(axis=2).astype(np.int16) - arr.min(axis=2).astype(np.int16)
    casi_blanco = lum >= UMBRAL_NEUTRALIZAR
    blanco_puro = (arr[:, :, 0] == 255) & (arr[:, :, 1] == 255) & (arr[:, :, 2] == 255)

    # "Campo abierto" = a mas de RADIO_ANTIALIAS px de cualquier trazo. Ahi el fondo
    # tiene que ser blanco puro si o si; pegado al trazo se acepta el gris del
    # antialias, que es borde de la pluma y no fondo.
    tinta = lum < UMBRAL_NEUTRALIZAR
    vecindad = dilatar(tinta, RADIO_ANTIALIAS)

    return {
        "halo": int((casi_blanco & (croma > MAX_DESVIACION_CROMA)).sum()),
        "amarillento": int(((arr[:, :, 0] == 255) & (arr[:, :, 1] == 255) & (arr[:, :, 2] < 255)).sum()),
        "fondo_sucio": int((~blanco_puro & ~vecindad).sum()),
        "antialias": int((~blanco_puro & vecindad & ~tinta).sum()),
        "tinta": int(tinta.sum()),
    }


def preparar_firma() -> None:
    """F.1 — recursos/firma.png lista para el PDF del informe."""
    print(f"\nOrigen : {ORIGEN_FIRMA_DOCX}::{MIEMBRO_FIRMA}")
    arr_original = extraer_firma(ORIGEN_FIRMA_DOCX)
    print(f"         {arr_original.shape[1]} x {arr_original.shape[0]} px, alfa opaco (aplanado a RGB)")

    limpio, stats = limpiar_fondo(arr_original)          # 5.3, mismos umbrales 242/252
    limpio, motas = blanquear_campo_abierto(limpio)      # F.1: motas grises del escaneo
    caja = caja_de_tinta(limpio)                          # recorte del margen muerto
    x0, y0, x1, y1 = caja_pillow(caja)
    recorte = limpio[y0:y1, x0:x1]                        # 5.2: recorte 1:1, sin resampleo
    guardar_png(recorte, SALIDA_FIRMA)                    # 5.4: PNG-24 RGB, sin alfa

    auditoria = auditar_fondo(recorte)
    alto, ancho = recorte.shape[:2]
    mm_ancho = ancho / FIRMA_DPI_PLANTILLA * 25.4
    mm_alto = alto / FIRMA_DPI_PLANTILLA * 25.4

    print(
        f"\nrecursos/firma.png\n"
        f"  caja de tinta {caja} -> {ancho} x {alto} px"
        f"  (margen muerto quitado: {caja[0]}px izq, {FIRMA_TAMANO[0] - 1 - caja[2]}px der,"
        f" {caja[1]}px arriba, {FIRMA_TAMANO[1] - 1 - caja[3]}px abajo)\n"
        f"  tamano natural a la escala de la plantilla ({FIRMA_DPI_PLANTILLA:.1f} dpi): "
        f"{mm_ancho:.1f} x {mm_alto:.1f} mm\n"
        f"  pixeles intactos (<{UMBRAL_NEUTRALIZAR}): {stats['intactos']:,}"
        f" | neutralizados (>={UMBRAL_NEUTRALIZAR}): {stats['neutralizados']:,}"
        f" | blanco puro (>={UMBRAL_BLANCO}): {stats['blanqueados']:,}\n"
        f"  velo amarillento previo (R=G=255, B<255): "
        f"{int(((arr_original[:, :, 0] == 255) & (arr_original[:, :, 1] == 255) & (arr_original[:, :, 2] < 255)).sum()):,} px"
        f" | motas grises forzadas a blanco (a >{RADIO_ANTIALIAS}px de todo trazo): {motas}\n"
        f"  VERIFICACION -> halo de croma: {auditoria['halo']}"
        f" | amarillento restante: {auditoria['amarillento']}"
        f" | fondo sucio en campo abierto: {auditoria['fondo_sucio']}\n"
        f"  trazo: {auditoria['tinta']:,} px de tinta + {auditoria['antialias']:,} px de antialias conservados\n"
        f"  peso: {SALIDA_FIRMA.stat().st_size:,} bytes"
    )

    assert auditoria["halo"] == 0, "quedo halo de croma en la firma"
    assert auditoria["amarillento"] == 0, "quedo velo amarillento en la firma"
    assert auditoria["fondo_sucio"] == 0, "el fondo no quedo blanco puro"


def main() -> int:
    if not ORIGEN.exists():
        print(f"ERROR: no encuentro el origen {ORIGEN}", file=sys.stderr)
        return 1
    if not ORIGEN_FIRMA_DOCX.exists():
        print(f"ERROR: no encuentro el origen {ORIGEN_FIRMA_DOCX}", file=sys.stderr)
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

    preparar_firma()

    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --------------------------------------------------------------------------
# Notas de decision sobre recursos/firma.png (F.1)
# --------------------------------------------------------------------------
#
# 1. QUE ENTRA EN LA IMAGEN: la rubrica CON el bloque de datos.
#    El bloque "Dr. Eleazar Shiera Bastidas / R:I.F.: V.- 7769162 / M.P.P.S. 34846 /
#    COMEZU: 7414" NO se puede separar de la rubrica: el trazo largo de la firma
#    atraviesa por dentro de las letras de la primera linea (se comprobo por
#    componentes conexos: rubrica y renglon del nombre son UN SOLO componente de
#    9.554 px, x 42-677, y 64-191). Recortar el bloque partiria la firma al medio.
#    Por eso la imagen se deja completa, que ademas es exactamente como la usa la
#    plantilla: una sola imagen flotante al pie, sin repetir esos datos como texto.
#    CONSECUENCIA PARA EL INFORME: los datos del medico que la decision 9 pide
#    editables en Configuracion (nombre, COMEZU, MPPS, RIF) van en la CABECERA del
#    informe -- como en la plantilla, que los pone en la tabla de arriba --, no
#    debajo de la firma; si se imprimieran tambien al pie quedarian duplicados.
#    Si el medico cambia de colegiatura hay que rescanear la firma.
#
# 2. RECORTE: caja de tinta exacta, sin margen de cortesia. El original trae
#    42 px muertos a la izquierda, 75 a la derecha, 64 arriba y 39 abajo; todo eso
#    es lienzo blanco del escaneo. Se quitan enteros para que el PDF pueda apoyar
#    la firma en una coordenada y que esa coordenada signifique el borde real de la
#    tinta. La caja se mide DESPUES de limpiar, con el mismo umbral 242 de 5.3.
#
# 3. FONDO BLANCO OPACO, NO TRANSPARENCIA. Razones, en orden:
#      a) El PNG de la plantilla ya venia RGBA pero con alfa 255 en TODOS los
#         pixeles: la transparencia nunca estuvo en el archivo, la simulaba Word
#         con el `hdphoto1.wdp`. Al abrirlo fuera de Word (o al imprimir desde
#         otra maquina) aparecia el velo amarillento. Hornear blanco puro es
#         justamente lo que arregla ese defecto.
#      b) El informe se imprime sobre papel blanco y el PDF se compone sobre fondo
#         blanco: opaco y transparente se ven identicos, pero el opaco no depende
#         de como cada visor o impresora componga el alfa.
#      c) Es el mismo criterio de 5.4 que ya siguen logo.png y logo_completo.png,
#         y lo que espera fpdf2 en `app/pdf_recipe.py` (PNG-24 sin alfa).
#    Si algun dia la firma tuviera que ir sobre un fondo de color, hay que
#    regenerarla con alfa; hoy no hay ningun caso asi.
#
# 4. UMBRALES: los mismos 242/252 de 5.3, sin aflojarlos. Medido sobre el recorte:
#    de los 712 px que caen en la banda 242-252 (los que se neutralizan a gris
#    pero no se blanquean), 709 estan a menos de 2 px de un trazo -- son antialias
#    del borde de la pluma, no fondo -- y solo 3 estan en campo abierto. El velo
#    amarillento, en cambio, vive entero por encima de 252 (R=G=255, B 224-254),
#    asi que el paso de blanqueo se lo come completo sin tocar ni un trazo fino.
#    Esos 3 px sueltos (gris 247-251, a 3-4 px del trazo mas cercano) son los que
#    limpia `blanquear_campo_abierto()`, que por construccion solo puede tocar
#    pixeles ya por encima de 242. Resultado: fondo blanco puro absoluto, 709 px
#    de antialias conservados y 21.943 px de tinta intactos.
#    El componente de tinta mas chico que sobrevive es de 6 px (el puntito en
#    x 176-178, y 106-108 del original): nada de la firma se perdio.
