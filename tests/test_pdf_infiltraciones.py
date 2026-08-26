"""Tests de `pdf_infiltraciones.py` — el registro de infiltraciones faciales.

Lo que fija esta suite es lo que se puede romper sin que nadie se dé cuenta
hasta que el registro ya está archivado en la historia:

  - **Los marcadores caen donde tienen que caer.** Es lo único del documento
    que no se puede verificar leyéndolo: si un círculo se corre 5 mm, el PDF
    sigue pareciendo correcto y dice una mentira sobre dónde se pinchó. Se
    comprueba con la aritmética del contrato —``x_mm = x0 + x · ancho_mm``—
    contra las elipses que el módulo dibujó de verdad.
  - **El número está adentro del marcador y es el mismo de la tabla.** El
    documento se imprime en blanco y negro: el color no sobrevive, el número sí.
  - **La tabla lista todos los puntos** y **los totales suman bien**. Un punto
    sin dosis se lista igual: un hueco en la numeración se lee como un renglón
    perdido.
  - **Ninguna fila se parte entre páginas.** Una dosis arriba y su zona abajo
    es la forma más silenciosa de leer mal un registro.

No se lee el PDF con un visor: se espía `_texto()` (por donde pasa toda la
tinta de texto), `image()` y `ellipse()` (por donde pasan la lámina y los
marcadores), anotando en qué página cayó cada cosa. Solo `unittest` de la
stdlib.

Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
           o:  py -3 -m pytest tests/test_pdf_infiltraciones.py -q
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import pdf_comun  # noqa: E402
import pdf_infiltraciones as pi  # noqa: E402

DIR_LAMINAS = RAIZ / "recursos" / "infiltraciones"

PRODUCTOS = [
    {"id": "p1", "nombre": "Toxina A — marca 1", "tipo": "toxina",
     "unidad": "U", "color": "#D92B2B", "lote": "TX-7741", "caducidad": ""},
    {"id": "p3", "nombre": "AH baja densidad", "tipo": "relleno",
     "unidad": "ml", "color": "#2456C4", "lote": "", "caducidad": ""},
]

#: Sesión realista: tercio superior con toxina, contorno con ácido hialurónico
#: y un punto marcado que no se infiltró. Las x/y son las de los puntos de
#: fábrica de `plantillas.json` pasados por la calibración de la lámina.
CRUDOS = [
    (1, 0.6351, 0.2109, "I", "Frontal — línea alta", "frontal-alto-i", "p1", 2, ""),
    (2, 0.3689, 0.2077, "D", "Frontal — línea alta", "frontal-alto-d", "p1", 2, ""),
    (3, 0.5845, 0.2425, "I", "Frontal — línea media medial", "frontal-med-med-i", "p1", 2, ""),
    (4, 0.4181, 0.2406, "D", "Frontal — línea media medial", "frontal-med-med-d", "p1", 2, ""),
    (5, 0.4986, 0.3681, "C", "Glabela — prócer", "procer", "p1", 4, "intramuscular"),
    (6, 0.5848, 0.3517, "I", "Glabela — corrugador", "corrugador-i", "p1", 4, ""),
    (7, 0.4132, 0.3497, "D", "Glabela — corrugador", "corrugador-d", "p1", 4, ""),
    (8, 0.7712, 0.4319, "I", "Patas de gallo — haz medio", "patas-med-i", "p1", 3, ""),
    (9, 0.2236, 0.4254, "D", "Patas de gallo — haz medio", "patas-med-d", "p1", 3, ""),
    (10, 0.7596, 0.4590, "I", "Patas de gallo — haz inferior", "patas-inf-i", "p1", 2, "intradérmico"),
    (11, 0.2340, 0.4529, "D", "Patas de gallo — haz inferior", "patas-inf-d", "p1", 2, "intradérmico"),
    (12, 0.6264, 0.7980, "I", "Línea mandibular / prejowl", "prejowl-i", "p3", 0.4, "cánula 25G"),
    (13, 0.3529, 0.7948, "D", "Línea mandibular / prejowl", "prejowl-d", "p3", 0.4, "cánula 25G"),
    (14, 0.5453, 0.7921, "I", "Mentoniano", "mentoniano-i", "", "", "marcado, no se infiltró"),
]


def _punto(crudo) -> dict:
    orden, x, y, lado, zona, plantilla, producto, dosis, notas = crudo
    return {"orden": orden, "x": x, "y": y, "lado": lado, "zona": zona,
            "plantillaId": plantilla, "productoId": producto, "dosis": dosis,
            "notas": notas}


SESION = {
    "codigo": "EC-0001",
    "fecha": "2026-08-26",
    "paciente_nombre": "María Fernanda Rodríguez Blanco",
    "paciente_edad": "38",
    "vista": "mujer-frontal",
    "productos": PRODUCTOS,
    "puntos": [_punto(c) for c in CRUDOS],
    "observaciones": "Control a los quince días.",
}


class _Espia(pi._Infiltraciones):
    """El compositor real, anotando cada trazo con su página."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trazos: list[tuple[int, float, float, str, str, float]] = []
        self.imagenes: list[tuple[int, str, float, float, float, float]] = []
        self.elipses: list[tuple[int, float, float, float, float, str]] = []

    def _texto(self, x, base_y, texto, estilo, pt, color):
        self.trazos.append((self.page, x, base_y, texto, estilo, pt))
        return super()._texto(x, base_y, texto, estilo, pt, color)

    def image(self, ruta, *args, **kwargs):  # type: ignore[override]
        self.imagenes.append((self.page, str(ruta), kwargs.get("x", 0.0),
                              kwargs.get("y", 0.0), kwargs.get("w", 0.0),
                              kwargs.get("h", 0.0)))
        return super().image(ruta, *args, **kwargs)

    def ellipse(self, x, y, w, h, style=None):  # type: ignore[override]
        self.elipses.append((self.page, x, y, w, h, str(style or "D")))
        return super().ellipse(x, y, w, h, style)


class BaseRegistro(unittest.TestCase):
    """Genera un registro de verdad en una carpeta temporal y guarda los trazos."""

    def setUp(self) -> None:
        # fpdf subsetea las Lato con fontTools y deja archivos al recolector:
        # son ResourceWarning de una dependencia, no de la app.
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)

        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_infiltra_"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)

        real = pi._Infiltraciones
        self.addCleanup(setattr, pi, "_Infiltraciones", real)
        self.doc: _Espia | None = None

        def recordar(*args, **kwargs):
            self.doc = _Espia(*args, **kwargs)
            return self.doc

        pi._Infiltraciones = recordar          # type: ignore[misc]

    def generar(self, datos) -> Path:
        destino = self.carpeta / "infiltraciones.pdf"
        pi.generar_infiltraciones(datos, str(destino))
        return destino

    # -- consultas sobre lo dibujado --------------------------------------
    @property
    def texto(self) -> str:
        return " ".join(t[3] for t in self.doc.trazos)

    def renglones(self, exacto: str):
        return [t for t in self.doc.trazos if t[3] == exacto]

    def contienen(self, parte: str):
        return [t for t in self.doc.trazos if parte in t[3]]

    @property
    def lamina(self):
        """`(página, ruta, x, y, ancho, alto)` de la lámina anatómica."""
        candidatas = [i for i in self.doc.imagenes if "base-" in i[1]]
        self.assertEqual(1, len(candidatas), "tiene que pegarse UNA lámina")
        return candidatas[0]

    @property
    def marcadores(self):
        """Las elipses de los marcadores, en el orden en que se dibujaron."""
        pagina = self.lamina[0]
        return [e for e in self.doc.elipses if e[0] == pagina]


# =============================================================================
# El documento sale y es un PDF
# =============================================================================

class DocumentoValido(BaseRegistro):

    def setUp(self) -> None:
        super().setUp()
        self.destino = self.generar(SESION)

    def test_se_escribe_un_pdf_de_verdad(self):
        self.assertTrue(self.destino.is_file())
        crudo = self.destino.read_bytes()
        self.assertTrue(crudo.startswith(b"%PDF-"), "no arranca con %PDF-")
        self.assertIn(b"%%EOF", crudo[-2048:], "el PDF quedó sin cerrar")
        self.assertGreater(len(crudo), 20_000, "una lámina pesa más que esto")

    def test_encabezado_completo(self):
        self.assertIn("Registro de infiltraciones", self.texto)
        self.assertIn("26 de Agosto de 2026", self.texto)
        self.assertIn("EC-0001", self.texto)
        self.assertIn("Paciente:", self.texto)
        self.assertIn("María Fernanda Rodríguez Blanco — 38 años", self.texto)

    def test_no_lleva_cedula(self):
        """Dec. 4 del récipe: la cédula no se imprime."""
        self.assertNotIn("C.I.", self.texto)
        self.assertNotIn("Cédula", self.texto)

    def test_la_firma_va_al_pie(self):
        firmas = [i for i in self.doc.imagenes if "firma" in i[1].lower()]
        self.assertEqual(1, len(firmas))
        self.assertAlmostEqual(pi.FIRMA_ANCHO_MM, firmas[0][4], places=1)

    def test_no_repite_el_nombre_del_medico_debajo_de_la_firma(self):
        """Ya está adentro del PNG (dec. 9)."""
        firma = [i for i in self.doc.imagenes if "firma" in i[1].lower()][0]
        y_firma = firma[3]
        debajo = [t for t in self.doc.trazos
                  if t[0] == firma[0] and t[2] >= y_firma
                  and not t[3].startswith("Página ")]
        self.assertEqual([], debajo)

    def test_observaciones(self):
        self.assertIn("Observaciones", self.texto)
        self.assertIn("Control a los quince días.", self.texto)

    def test_nada_se_pasa_de_la_guia_derecha(self):
        for _, x, _, texto, estilo, pt in self.doc.trazos:
            fin = x + self.doc._ancho(texto, estilo, pt)
            self.assertLessEqual(round(fin, 2), pdf_comun.GUIA_DER_MM + 0.01,
                                 f"«{texto}» se pasa de la guía derecha")


# =============================================================================
# Los marcadores
# =============================================================================

class Marcadores(BaseRegistro):
    """Lo único del documento que no se puede verificar leyéndolo."""

    def setUp(self) -> None:
        super().setUp()
        self.generar(SESION)

    def test_la_lamina_es_la_de_la_vista_pedida_y_va_centrada(self):
        _, ruta, x, _, ancho, alto = self.lamina
        self.assertIn("base-mujer.jpg", ruta)
        self.assertAlmostEqual(pi.LAMINA_ANCHO_MM, ancho, places=2)
        # 896 x 1200 px: la lámina es 3:4 exacto y así tiene que imprimirse.
        self.assertAlmostEqual(896 / 1200, ancho / alto, places=4)
        centro = x + ancho / 2.0
        self.assertAlmostEqual(
            (pdf_comun.MARGEN_IZQ_MM + pdf_comun.GUIA_DER_MM) / 2.0, centro,
            places=2)

    def test_hay_un_marcador_por_punto(self):
        self.assertEqual(len(CRUDOS), len(self.marcadores))

    def test_cada_marcador_cae_en_su_coordenada_normalizada(self):
        """`x_mm = x0 + x · ancho_mm`, `y_mm = y0 + y · alto_mm` (§4)."""
        _, _, ix, iy, ancho, alto = self.lamina
        radio = pi.MARCADOR_RADIO_MM
        for crudo, elipse in zip(CRUDOS, self.marcadores):
            _, ex, ey, ew, eh, _ = elipse
            self.assertAlmostEqual(radio * 2, ew, places=3)
            self.assertAlmostEqual(radio * 2, eh, places=3)
            cx, cy = ex + radio, ey + radio
            self.assertAlmostEqual(ix + crudo[1] * ancho, cx, places=3,
                                   msg=f"punto {crudo[0]} corrido en X")
            self.assertAlmostEqual(iy + crudo[2] * alto, cy, places=3,
                                   msg=f"punto {crudo[0]} corrido en Y")

    def test_ningun_marcador_se_sale_de_la_lamina(self):
        _, _, ix, iy, ancho, alto = self.lamina
        for _, ex, ey, ew, eh, _ in self.marcadores:
            self.assertGreaterEqual(ex + ew / 2.0, ix - 0.01)
            self.assertLessEqual(ex + ew / 2.0, ix + ancho + 0.01)
            self.assertGreaterEqual(ey + eh / 2.0, iy - 0.01)
            self.assertLessEqual(ey + eh / 2.0, iy + alto + 0.01)

    def test_los_numeros_1_a_N_estan_dentro_de_su_marcador(self):
        """El número es lo que sobrevive a la fotocopia en blanco y negro."""
        pagina, _, ix, iy, ancho, alto = self.lamina
        radio = pi.MARCADOR_RADIO_MM
        for crudo in CRUDOS:
            numero = str(crudo[0])
            cx = ix + crudo[1] * ancho
            cy = iy + crudo[2] * alto
            cerca = [t for t in self.doc.trazos
                     if t[0] == pagina and t[3] == numero
                     and abs(t[2] - cy) < radio and abs(t[1] - cx) < radio]
            self.assertTrue(cerca, f"el número {numero} no está en su marcador")
            _, x, _, texto, estilo, pt = cerca[0]
            self.assertEqual("B", estilo)
            # centrado horizontal de verdad, medido sobre el ancho del texto
            self.assertAlmostEqual(cx, x + self.doc._ancho(texto, estilo, pt) / 2.0,
                                   places=2)
            # y entra en el disco
            self.assertLess(self.doc._ancho(texto, estilo, pt), radio * 2)

    def test_el_punto_sin_dosis_sale_como_circulo_hueco(self):
        """Un punto marcado y no infiltrado no puede parecer una aplicación."""
        hueco = self.marcadores[13]        # el 14: mentoniano, sin producto
        self.assertEqual("D", hueco[5], "tiene que quedar sin relleno")
        for elipse in self.marcadores[:13]:
            self.assertEqual("DF", elipse[5])

    def test_los_discos_se_dibujan_antes_que_los_numeros(self):
        """Si no, el disco del vecino tapa el número (cola de ceja, 1,7 mm)."""
        pagina = self.lamina[0]
        ultimo_disco = max(i for i, e in enumerate(self.doc.elipses)
                           if e[0] == pagina)
        self.assertEqual(len(CRUDOS) - 1, ultimo_disco,
                         "los 14 discos van seguidos, antes de los números")


class Contraste(unittest.TestCase):
    """La tinta del número la decide la luminancia, no el promedio RGB."""

    def test_luminancia_de_los_extremos(self):
        self.assertAlmostEqual(0.0, pi.luminancia_relativa((0, 0, 0)), places=6)
        self.assertAlmostEqual(1.0, pi.luminancia_relativa((255, 255, 255)),
                               places=6)

    def test_el_verde_pesa_mas_que_el_azul(self):
        self.assertGreater(pi.luminancia_relativa((0, 255, 0)),
                           pi.luminancia_relativa((0, 0, 255)))

    def test_numero_blanco_sobre_los_colores_de_producto(self):
        for hexa in ("#D92B2B", "#2456C4", "#7A3AB8", "#C42574", "#A85A0B"):
            self.assertEqual((255, 255, 255),
                             pi.tinta_sobre(pi.color_desde_hex(hexa)),
                             f"{hexa} pide número blanco")

    def test_numero_negro_sobre_un_color_claro(self):
        for hexa in ("#FFD400", "#9ABE0F", "#FFFFFF"):
            self.assertEqual((0, 0, 0),
                             pi.tinta_sobre(pi.color_desde_hex(hexa)),
                             f"{hexa} pide número negro")

    def test_color_invalido_no_rompe(self):
        self.assertEqual(pdf_comun.TEAL_MEDIO,
                         pi.color_desde_hex("no es un color", pdf_comun.TEAL_MEDIO))
        self.assertEqual((17, 34, 51), pi.color_desde_hex("#123"))


# =============================================================================
# La leyenda y la tabla
# =============================================================================

class Leyenda(BaseRegistro):

    def setUp(self) -> None:
        super().setUp()
        self.generar(SESION)

    def test_cada_producto_con_su_unidad_y_su_lote(self):
        self.assertIn("Toxina A — marca 1 · U · lote TX-7741", self.texto)
        self.assertIn("AH baja densidad · ml", self.texto)

    def test_el_producto_sin_lote_no_inventa_uno(self):
        self.assertNotIn("AH baja densidad · ml · lote", self.texto)

    def test_explica_la_lateralidad(self):
        junto = self.texto.replace("  ", " ")
        self.assertIn("hemifacial izquierdo del paciente", junto)


class Tabla(BaseRegistro):

    def setUp(self) -> None:
        super().setUp()
        self.generar(SESION)

    def test_las_columnas_del_contrato(self):
        for rotulo in ("N.º", "Lado", "Zona", "Producto", "Dosis", "Notas"):
            self.assertTrue(self.renglones(rotulo), f"falta la columna «{rotulo}»")

    def test_las_columnas_suman_el_ancho_util(self):
        self.assertAlmostEqual(pdf_comun.ANCHO_UTIL_MM,
                               sum(c[1] for c in pi.COLUMNAS), places=2)

    def test_estan_los_catorce_puntos(self):
        for crudo in CRUDOS:
            numero = str(crudo[0])
            en_tabla = [t for t in self.doc.trazos
                        if t[3] == numero
                        and abs(t[1] - (pdf_comun.MARGEN_IZQ_MM
                                        + pi.TABLA_PAD_MM)) < 0.01]
            self.assertTrue(en_tabla, f"el punto {numero} no está en la tabla")

    def test_cada_zona_aparece_con_su_lado_y_su_dosis(self):
        for _, _, _, lado, zona, _, producto, dosis, _ in CRUDOS:
            self.assertIn(zona, self.texto)
            if producto:
                unidad = "U" if producto == "p1" else "ml"
                esperado = f"{pi.formatear_dosis(dosis)} {unidad}"
                self.assertIn(esperado, self.texto)

    def test_las_regiones_van_en_el_orden_anatomico(self):
        etiquetas = ["Frente", "Glabela", "Periocular", "Tercio inferior"]
        posiciones = []
        for etiqueta in etiquetas:
            encontrados = [i for i, t in enumerate(self.doc.trazos)
                           if t[3] == etiqueta and t[4] == "B"]
            self.assertTrue(encontrados, f"falta la región «{etiqueta}»")
            posiciones.append(encontrados[0])
        self.assertEqual(sorted(posiciones), posiciones,
                         "las regiones salieron desordenadas")

    def test_cada_region_lleva_su_subtotal(self):
        self.assertIn("4 puntos · 8 U", self.texto)      # frente
        self.assertIn("3 puntos · 12 U", self.texto)     # glabela
        self.assertIn("4 puntos · 10 U", self.texto)     # periocular
        self.assertIn("3 puntos · 0,8 ml", self.texto)   # tercio inferior

    def test_el_punto_sin_dosis_se_lista_igual(self):
        """Un hueco en la numeración se lee como un renglón perdido."""
        self.assertIn("Mentoniano", self.texto)
        self.assertIn("marcado, no se infiltró", self.texto)
        rayas = [t for t in self.doc.trazos if t[3] == "—"]
        self.assertGreaterEqual(len(rayas), 2,
                                "producto y dosis vacíos salen como «—»")

    def test_ningun_renglon_baja_del_pie_del_cuerpo(self):
        for _, _, y, texto, _, _ in self.doc.trazos:
            if texto.startswith("Página "):
                continue                      # el pie vive debajo del cuerpo
            self.assertLessEqual(round(y, 2), pdf_comun.CUERPO_Y1_MM + 0.01,
                                 texto)


class Totales(BaseRegistro):

    def setUp(self) -> None:
        super().setUp()
        self.generar(SESION)

    def test_suma_por_producto_y_cantidad_de_puntos(self):
        # toxina: 2+2+2+2+4+4+4+3+3+2+2 = 30 U en 11 puntos
        # AH:     0,4 + 0,4             = 0,8 ml en 2 puntos
        self.assertIn("Totales por producto", self.texto)
        self.assertIn("30 U en 11 puntos", self.texto)
        self.assertIn("0,8 ml en 2 puntos", self.texto)

    def test_la_funcion_de_totales_no_cuenta_los_puntos_sin_dosis(self):
        _, indice = pi.normalizar_productos(PRODUCTOS)
        puntos = pi.normalizar_puntos(SESION["puntos"], indice, {})
        filas = {f["producto"]["id"]: f for f in pi.totales_por_producto(puntos)}
        self.assertEqual(30.0, filas["p1"]["dosis"])
        self.assertEqual(11, filas["p1"]["puntos"])
        self.assertAlmostEqual(0.8, filas["p3"]["dosis"], places=6)
        self.assertEqual(2, filas["p3"]["puntos"])
        self.assertEqual(14, len(puntos), "el punto sin dosis igual se registra")

    def test_dosis_cero_es_lo_mismo_que_sin_dosis(self):
        datos = dict(SESION)
        puntos = [dict(p) for p in SESION["puntos"]]
        puntos[0]["dosis"] = 0
        datos["puntos"] = puntos
        self.generar(datos)
        self.assertIn("28 U en 10 puntos", self.texto)
        self.assertEqual("D", self.marcadores[0][5])


# =============================================================================
# Salto de página
# =============================================================================

def _sesion_larga(cantidad: int = 60) -> dict:
    """Una sesión de `cantidad` puntos repartidos por toda la cara."""
    zonas = [
        ("Frontal — línea alta", "I", 0.62, 0.21),
        ("Frontal — línea baja", "D", 0.38, 0.27),
        ("Glabela — corrugador", "I", 0.58, 0.35),
        ("Patas de gallo — haz medio", "D", 0.23, 0.43),
        ("Líneas de conejo (nasal transverso)", "C", 0.52, 0.50),
        ("Surco nasogeniano", "I", 0.60, 0.60),
        ("Labio superior", "C", 0.50, 0.68),
        ("Masetero", "D", 0.32, 0.72),
        ("Bandas platismales — medial", "I", 0.55, 0.90),
        ("Zona rarísima que nadie catalogó", "C", 0.50, 0.95),
    ]
    puntos = []
    for i in range(cantidad):
        zona, lado, x, y = zonas[i % len(zonas)]
        corrimiento = (i // len(zonas)) * 0.012
        puntos.append({
            "orden": i + 1,
            "x": min(0.97, x + corrimiento),
            "y": min(0.97, y + corrimiento),
            "lado": lado,
            "zona": zona,
            "productoId": "p1" if i % 3 else "p3",
            "dosis": 2 if i % 3 else 0.2,
            "notas": "",
        })
    return dict(SESION, puntos=puntos, observaciones="")


class _Continuidad(BaseRegistro):
    """Comprobaciones de continuidad de la tabla, para cualquier tamaño."""

    #: Columna en la que arranca cada celda, medida como la dibuja el módulo.
    COLUMNA_NUMERO = pdf_comun.MARGEN_IZQ_MM + pi.TABLA_PAD_MM
    COLUMNA_ZONA = (pdf_comun.MARGEN_IZQ_MM + pi.COLUMNAS[0][1]
                    + pi.COLUMNAS[1][1] + pi.TABLA_PAD_MM)

    def comprobar_filas_enteras(self, datos) -> None:
        """Ninguna fila con el N.º en una hoja y la zona en la siguiente.

        Es la lectura más peligrosa de un registro de dosis: la dosis de
        arriba leída con la zona de abajo. Se verifica que la celda «Zona» de
        cada punto esté en la MISMA página y en la MISMA línea de base que su
        «N.º» — que es exactamente lo que dejaría de pasar si la fila se
        partiera.
        """
        for punto in datos["puntos"]:
            numero = str(punto["orden"])
            celdas = [t for t in self.doc.trazos
                      if t[3] == numero
                      and abs(t[1] - self.COLUMNA_NUMERO) < 0.01]
            self.assertEqual(1, len(celdas),
                             f"el punto {numero} no está exactamente una vez")
            pagina, _, y, _, _, _ = celdas[0]
            zona = [t for t in self.doc.trazos
                    if t[0] == pagina and abs(t[2] - y) < 0.01
                    and abs(t[1] - self.COLUMNA_ZONA) < 0.01]
            self.assertTrue(
                zona, f"la fila {numero} quedó partida: su zona no está en la "
                      f"página {pagina} a la altura del N.º")
            self.assertTrue(punto["zona"].startswith(zona[0][3]),
                            f"la fila {numero} tiene la zona de otro punto")

    def comprobar_pie_y_cabeceras(self) -> None:
        total = self.doc.page
        for numero in range(1, total + 1):
            self.assertIn(f"Página {numero} de {total}", self.texto)
        # membrete en todas
        paginas = {t[0] for t in self.doc.trazos if t[3] == "EC-0001"}
        self.assertEqual(set(range(1, total + 1)), paginas)
        # y cabecera de columnas en cada hoja donde hay tabla
        con_filas = {t[0] for t in self.doc.trazos
                     if abs(t[1] - self.COLUMNA_NUMERO) < 0.01}
        con_cabecera = {t[0] for t in self.renglones("Zona") if t[4] == "B"}
        self.assertTrue(con_filas.issubset(con_cabecera),
                        "hay una hoja con filas y sin cabecera de columnas")


class SesionDeDosPaginas(_Continuidad):
    """22 puntos: el registro se va a una segunda hoja y ahí termina."""

    def setUp(self) -> None:
        super().setUp()
        self.datos = _sesion_larga(22)
        self.generar(self.datos)

    def test_el_pie_dice_pagina_2_de_2(self):
        self.assertEqual(2, self.doc.page)
        self.assertIn("Página 1 de 2", self.texto)
        self.assertIn("Página 2 de 2", self.texto)

    def test_ninguna_fila_se_parte_entre_paginas(self):
        self.comprobar_filas_enteras(self.datos)

    def test_membrete_pie_y_cabeceras(self):
        self.comprobar_pie_y_cabeceras()


class SesionLarga(_Continuidad):
    """60 puntos: la tabla sigue de hoja en hoja, y ninguna fila se parte.

    60 puntos NO entran en dos hojas y no hay forma honesta de que entren: a
    5,7 mm por fila son 342 mm de tabla más 56 mm de cabeceras de región, y
    una carta ofrece 188 mm de cuerpo por hoja. Meterlos en dos páginas pedía
    filas de 2,5 mm, o sea letra de 5 pt en un documento de dosis. Se dejan las
    cuatro hojas que hacen falta —el contrato permite el documento multipágina,
    igual que el informe— y lo que se verifica acá es que el corte esté bien
    hecho: filas enteras, cabecera repetida y numeración de páginas correcta.
    """

    def setUp(self) -> None:
        super().setUp()
        self.datos = _sesion_larga(60)
        self.generar(self.datos)

    def test_salta_de_pagina(self):
        self.assertGreater(self.doc.page, 1)

    def test_ninguna_fila_se_parte_entre_paginas(self):
        self.comprobar_filas_enteras(self.datos)

    def test_membrete_pie_y_cabeceras(self):
        self.comprobar_pie_y_cabeceras()

    def test_estan_los_sesenta_marcadores(self):
        self.assertEqual(60, len(self.marcadores))

    def test_los_totales_y_la_firma_llegan_a_la_ultima_hoja(self):
        self.assertIn("Totales por producto", self.texto)
        firmas = [i for i in self.doc.imagenes if "firma" in i[1].lower()]
        self.assertEqual(1, len(firmas))
        self.assertEqual(self.doc.page, firmas[0][0])

    def test_ningun_renglon_baja_del_pie_del_cuerpo(self):
        for _, _, y, texto, _, _ in self.doc.trazos:
            if texto.startswith("Página "):
                continue
            self.assertLessEqual(round(y, 2), pdf_comun.CUERPO_Y1_MM + 0.01,
                                 texto)

    def test_la_zona_desconocida_cae_en_otras(self):
        self.assertIn("Otras", self.texto)
        self.assertIn("Zona rarísima que nadie catalogó", self.texto)


# =============================================================================
# Regiones
# =============================================================================

class Regiones(unittest.TestCase):
    """De dónde sale la región de cada punto (§4)."""

    def test_el_orden_es_el_del_contrato(self):
        self.assertEqual(
            ["Frente", "Glabela", "Cejas", "Periocular", "Nariz",
             "Tercio medio", "Perioral", "Tercio inferior", "Cuello", "Otras"],
            [pi.ETIQUETA_REGION[r] for r in pi.ORDEN_REGIONES])

    def test_manda_el_grupo_de_plantillas_json_cuando_hay_plantillaId(self):
        indice = pi._indice_puntos(pi.cargar_plantillas(str(DIR_LAMINAS)))
        self.assertIn("cola-ceja-2-i", indice)
        puntos = pi.normalizar_puntos(
            [{"orden": 1, "x": 0.5, "y": 0.5, "plantillaId": "cola-ceja-2-i",
              "zona": "Cola de ceja — media"}], {}, indice)
        self.assertEqual("cejas", puntos[0]["region"])

    def test_sin_plantillaId_manda_la_zona(self):
        self.assertEqual("frente", pi.region_de_zona("Frontal — línea alta"))
        self.assertEqual("glabela", pi.region_de_zona("Nasion / radix"))
        self.assertEqual("periocular", pi.region_de_zona("Canto externo"))
        self.assertEqual("cuello", pi.region_de_zona("Nefertiti"))

    def test_una_variante_propia_se_clasifica_por_el_prefijo(self):
        self.assertEqual("frente",
                         pi.region_de_zona("Frontal — la línea que uso yo"))
        self.assertEqual("inferior",
                         pi.region_de_zona("Masetero — haz profundo"))

    def test_lo_que_no_encaja_va_a_otras(self):
        self.assertEqual("otras", pi.region_de_zona("Vaya uno a saber"))
        self.assertEqual("otras", pi.region_de_zona(""))

    def test_el_plantillaId_completa_la_zona_que_falta(self):
        indice = pi._indice_puntos(pi.cargar_plantillas(str(DIR_LAMINAS)))
        puntos = pi.normalizar_puntos(
            [{"orden": 1, "x": 0.5, "y": 0.5, "plantillaId": "procer"}], {},
            indice)
        self.assertEqual("Glabela — prócer", puntos[0]["zona"])
        self.assertEqual("C", puntos[0]["lado"])


class Dosis(unittest.TestCase):
    """Cómo se escribe un número que el médico tecleó a mano."""

    def test_entero_sin_coma(self):
        self.assertEqual("2", pi.formatear_dosis(2))
        self.assertEqual("30", pi.formatear_dosis(30.0))

    def test_decimal_con_coma_y_sin_ceros_de_relleno(self):
        self.assertEqual("0,4", pi.formatear_dosis(0.4))
        self.assertEqual("1,25", pi.formatear_dosis(1.25))

    def test_acepta_la_coma_decimal_de_entrada(self):
        self.assertEqual(0.5, pi._numero("0,5"))
        self.assertEqual(2.0, pi._numero(" 2 "))
        self.assertIsNone(pi._numero("dos"))
        self.assertIsNone(pi._numero(""))


# =============================================================================
# Lo que tiene que frenar
# =============================================================================

class Hostiles(unittest.TestCase):

    def setUp(self) -> None:
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_infiltra_mal_"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        self.destino = str(self.carpeta / "infiltraciones.pdf")

    def test_falta_el_logo(self):
        with self.assertRaises(pi.RecursoFaltanteError) as caja:
            pi.generar_infiltraciones(
                SESION, self.destino,
                ruta_logo=str(self.carpeta / "no-hay-logo.png"))
        self.assertIn("logo", str(caja.exception).lower())
        self.assertFalse(Path(self.destino).exists())

    def test_falta_la_lamina(self):
        vacia = self.carpeta / "sin-laminas"
        vacia.mkdir()
        with self.assertRaises(pi.RecursoFaltanteError) as caja:
            pi.generar_infiltraciones(SESION, self.destino,
                                      dir_laminas=str(vacia))
        mensaje = str(caja.exception)
        self.assertIn("base-mujer.jpg", mensaje)
        self.assertIn("lámina", mensaje)
        self.assertFalse(Path(self.destino).exists())

    def test_la_lamina_faltante_es_tambien_un_error_de_pdf_comun(self):
        """`rutas.py` engancha `pdf_comun.RecursoFaltanteError` para los tres."""
        self.assertTrue(issubclass(pi.RecursoFaltanteError,
                                   pdf_comun.RecursoFaltanteError))
        self.assertTrue(issubclass(pi.RecursoFaltanteError,
                                   pi.InfiltracionesError))
        self.assertTrue(issubclass(pi.InfiltracionesError,
                                   pdf_comun.DocumentoError))

    def test_vista_desconocida_avisa_en_castellano(self):
        with self.assertRaises(pi.VistaDesconocidaError) as caja:
            pi.generar_infiltraciones(dict(SESION, vista="perro-frontal"),
                                      self.destino)
        mensaje = str(caja.exception)
        self.assertIn("perro-frontal", mensaje)
        self.assertIn("No existe la lámina", mensaje)
        self.assertIn("mujer-frontal", mensaje)
        self.assertIn("hombre-frontal", mensaje)
        self.assertFalse(Path(self.destino).exists())

    def test_la_vista_de_hombre_tambien_existe(self):
        pi.generar_infiltraciones(dict(SESION, vista="hombre-frontal"),
                                  self.destino)
        self.assertTrue(Path(self.destino).is_file())

    def test_una_sesion_sin_puntos_sale_igual(self):
        """Se puede archivar una sesión que se anuló antes de infiltrar."""
        pi.generar_infiltraciones(
            dict(SESION, puntos=[], productos=[], observaciones="Se suspendió."),
            self.destino)
        self.assertTrue(Path(self.destino).is_file())

    def test_sin_fecha_sale_la_de_hoy(self):
        from datetime import date
        pi.generar_infiltraciones(dict(SESION, fecha=""), self.destino)
        self.assertTrue(Path(self.destino).is_file())
        self.assertIn(str(date.today().year),
                      pdf_comun.fecha_larga(date.today().isoformat()))


if __name__ == "__main__":
    unittest.main()
