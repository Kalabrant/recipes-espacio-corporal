"""Tests de `pdf_examenes.py` — la orden de análisis con el formato del récipe.

Lo que fija esta suite es el reparto entre mitades del §3 del contrato 2.1, que
es lo que se puede romper sin que nadie se dé cuenta hasta que la orden ya está
impresa y el paciente está parado en el laboratorio:

  - Mitad `Solicito:` (se entrega en el laboratorio): SÓLO la lista numerada de
    análisis con su muestra a la derecha del renglón. Sin preparaciones.
  - Mitad `Ind.` (la conserva el paciente): cada análisis repetido con SU MISMO
    NÚMERO y, debajo, su preparación. Sin muestra. Al final, separado, el
    bloque de indicaciones generales.

Y las dos invariantes que protegen la hoja y el papel del talonario:

  - lo que `medir_contenido` dice que ocupa el cuerpo es lo que realmente se
    dibuja (de esa cuenta depende que el texto no pise el bloque `Dr./CI/MPPS`
    ni el renglón `Paciente:`);
  - **`pdf_recipe` no cambió ni un punto**: este módulo lo subclasa y no lo
    toca. Al final se corre entera `tests/test_pdf_recipe.py` desde acá, que es
    la red de la que habla el contrato.

Mismo estilo que `test_pdf_recipe.py`: `unittest` de la stdlib y se espía
`_texto()`, que es por donde pasa toda la tinta de texto del módulo. Se agrega
además un PDF de verdad escrito a disco, y su texto se relee con PyMuPDF
cuando está instalado (si no, ese caso se saltea y el resto sigue valiendo).

Se corre con:  py -3 -m pytest tests/test_pdf_examenes.py -q
           o:  py -3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import inspect
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pdf_examenes  # noqa: E402
import pdf_recipe  # noqa: E402

try:  # el texto del PDF ya escrito; opcional, la suite anda igual sin él
    import fitz  # type: ignore  # noqa: E402  (PyMuPDF)
except ImportError:  # pragma: no cover - depende de la máquina
    fitz = None


#: Debajo de acá empieza el bloque Dr./CI/MPPS de la mitad izquierda.
TOPE_CUERPO_SOLICITO_MM = 168.0
#: Debajo de acá está el renglón Paciente:/Fecha: de la mitad Ind.
TOPE_CUERPO_IND_MM = 190.0


class _Espia(pdf_examenes._OrdenExamenes):
    """Igual que el compositor real, pero anota cada renglón que escribe."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trazos: list[tuple[float, float, str, str, float]] = []

    def _texto(self, x, base_y, texto, estilo, pt, color):
        self.trazos.append((x, base_y, texto, estilo, pt))
        return super()._texto(x, base_y, texto, estilo, pt, color)


def _item(examen, muestra="Sangre", indicaciones=""):
    return {"examen": examen, "muestra": muestra, "indicaciones": indicaciones}


def _datos(items, generales=""):
    return {
        # El código que se imprime es el DEL PACIENTE (dec. 2 de la 2.0):
        # 'EC-0001', sin año, el mismo en las dos mitades.
        "codigo": "EC-0001",
        "fecha_emision": "26/08/2026",
        "paciente_nombre": "Ana Pérez",
        "items": items,
        "indicaciones_generales": generales,
    }


ITEMS = [
    _item("Hematología completa", "Sangre", "No requiere ayuno."),
    _item("Glicemia en ayunas", "Sangre", "Ayuno de 8 a 12 horas."),
]
GENERALES = "Traer los resultados al control del 5 de septiembre."


class ReparteElContenido(unittest.TestCase):
    """Base: compone una orden y deja el cuerpo de cada mitad a mano."""

    def componer(self, datos):
        doc = _Espia(pdf_examenes.RUTA_LOGO_DEFECTO,
                     pdf_examenes.DIR_FUENTES_DEFECTO)
        self.alto_solicito, self.alto_ind = doc.componer(datos, dibujar=True)
        self.doc = doc
        return doc

    def _cuerpo(self, x0, x1, tope):
        """Renglones del cuerpo libre de una mitad, ordenados por altura.

        Se descarta el cromo fijo (código arriba, colegiatura y pie abajo)
        acotando la franja vertical al cuerpo.
        """
        return [t for t in self.doc.trazos
                if x0 <= t[0] < x1 and pdf_examenes.CUERPO_Y0_MM <= t[1] <= tope]

    def cuerpo_solicito(self):
        return sorted(self._cuerpo(0.0, pdf_examenes.MITAD_ANCHO_MM,
                                   TOPE_CUERPO_SOLICITO_MM),
                      key=lambda t: (t[1], t[0]))

    def cuerpo_ind(self):
        return sorted(self._cuerpo(pdf_examenes.MITAD_ANCHO_MM,
                                   pdf_examenes.PAGINA_ANCHO_MM,
                                   TOPE_CUERPO_IND_MM), key=lambda t: (t[1], t[0]))

    @staticmethod
    def texto(renglones):
        return " ".join(t[2] for t in renglones)

    @staticmethod
    def numeros(renglones):
        """Los marcadores «1.» «2.» ... en el orden en que se dibujaron."""
        return [t[2] for t in renglones
                if t[2].rstrip(".").isdigit() and t[2].endswith(".")]


# =============================================================================
# El rótulo `Solicito:` — medido, no mirado
# =============================================================================

class RotuloSolicito(unittest.TestCase):
    """`Solicito:` es dos veces y media más ancho que `Rp.`: hay que medirlo."""

    def setUp(self):
        self.doc = pdf_examenes._OrdenExamenes(
            pdf_examenes.RUTA_LOGO_DEFECTO, pdf_examenes.DIR_FUENTES_DEFECTO)
        self.doc.add_page()
        self.medidas = self.doc.medidas_rotulo()

    def test_es_mucho_mas_ancho_que_el_del_recipe(self):
        """Si no lo fuera, esta suite no estaría probando nada."""
        ancho_rp = self.doc._ancho("Rp.", "BI", pdf_examenes.PT_RP)
        self.assertGreater(self.medidas["ancho_mm"], 2 * ancho_rp)

    def test_no_pisa_el_bloque_del_codigo(self):
        self.assertGreater(
            self.medidas["holgura_codigo_mm"], 0.0,
            "«Solicito:» se le monta al «N.º EC-0001» de la derecha")

    def test_no_se_pasa_de_la_guia_derecha(self):
        self.assertLessEqual(self.medidas["x1_mm"], pdf_examenes.GUIA_DER_MM)

    def test_no_pisa_el_logo(self):
        """El logo muere arriba del rótulo: entre los dos tiene que haber aire."""
        self.assertGreater(
            self.medidas["holgura_logo_mm"], 0.0,
            "el rótulo se le monta al logo que tiene encima")

    def test_entra_a_pt_rp_asi_que_no_se_le_baja_el_cuerpo(self):
        """Documenta la decisión: entra a 20 pt, no hizo falta achicarlo.

        Si algún día deja de entrar, este test lo dice antes que el papel y
        recién ahí hay que bajarle el cuerpo SÓLO a este rótulo.
        """
        self.assertAlmostEqual(23.79, self.medidas["ancho_mm"], places=1)
        self.assertGreater(self.medidas["holgura_codigo_mm"], 10.0)
        self.assertGreater(self.medidas["holgura_logo_mm"], 5.0)

    def test_el_rotulo_de_cada_mitad_es_el_del_contrato(self):
        self.assertEqual("Solicito:", pdf_examenes.ROTULO_SOLICITO)
        self.assertEqual("Ind.", pdf_examenes.ROTULO_IND)


# =============================================================================
# El PDF de verdad
# =============================================================================

class ElPdfSeEscribe(unittest.TestCase):
    """Una página carta apaisada, válida, con las dos mitades adentro."""

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.ruta = pdf_examenes.generar_examenes(
            _datos(ITEMS, GENERALES),
            os.path.join(cls._dir.name, "sub", "EXAMENES_EC-0001.pdf"))

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def test_devuelve_la_ruta_y_crea_la_carpeta(self):
        self.assertTrue(os.path.isfile(self.ruta))
        self.assertGreater(os.path.getsize(self.ruta), 1000)

    def test_es_un_pdf(self):
        with open(self.ruta, "rb") as archivo:
            self.assertEqual(b"%PDF", archivo.read(4))

    @unittest.skipIf(fitz is None, "PyMuPDF no está instalado")
    def test_es_de_una_sola_pagina_carta_apaisada(self):
        with fitz.open(self.ruta) as pdf:
            self.assertEqual(1, pdf.page_count,
                             "la orden es UNA hoja con las dos mitades")
            caja = pdf[0].rect
            # 279,4 x 215,9 mm en puntos (1 pt = 25,4/72 mm) = 792 x 612
            self.assertAlmostEqual(792.0, caja.width, places=0)
            self.assertAlmostEqual(612.0, caja.height, places=0)

    @unittest.skipIf(fitz is None, "PyMuPDF no está instalado")
    def test_el_texto_del_pdf_trae_las_dos_mitades(self):
        with fitz.open(self.ruta) as pdf:
            texto = pdf[0].get_text()
        for esperado in ("Solicito:", "Ind.", "N.º", "EC-0001",
                         "Paciente:", "Fecha:", "26/08/2026", "Ana Pérez",
                         "Salud y Bienestar", "Dr.:", "CI:", "MPPS:",
                         "Hematología completa", "Glicemia en ayunas",
                         "Sangre", "Ayuno de 8 a 12 horas.",
                         "Traer los resultados"):
            self.assertIn(esperado, texto)

    @unittest.skipIf(fitz is None, "PyMuPDF no está instalado")
    def test_cada_analisis_sale_dos_veces_una_por_mitad(self):
        with fitz.open(self.ruta) as pdf:
            pagina = pdf[0]
            for examen in ("Hematología completa", "Glicemia en ayunas"):
                cajas = pagina.search_for(examen)
                self.assertEqual(2, len(cajas), examen)
                # una en cada mitad de la hoja (la línea de corte cae al medio)
                medio = 792.0 / 2.0
                self.assertTrue(any(c.x0 < medio for c in cajas))
                self.assertTrue(any(c.x0 > medio for c in cajas))


# =============================================================================
# Mitad `Solicito:`
# =============================================================================

class MitadSolicito(ReparteElContenido):
    """La mitad que va al laboratorio dice QUÉ pedir y en qué muestra."""

    def setUp(self):
        self.componer(_datos(ITEMS, GENERALES))

    def test_lista_los_analisis_con_su_muestra(self):
        texto = self.texto(self.cuerpo_solicito())
        for esperado in ("Hematología completa", "Glicemia en ayunas", "Sangre"):
            self.assertIn(esperado, texto)

    def test_no_bajan_las_preparaciones(self):
        texto = self.texto(self.cuerpo_solicito())
        for prohibido in ("No requiere ayuno", "Ayuno de 8 a 12 horas"):
            self.assertNotIn(
                prohibido, texto,
                "la preparación es del paciente, no del laboratorio")

    def test_no_baja_el_bloque_de_indicaciones_generales(self):
        self.assertNotIn("Traer los resultados",
                         self.texto(self.cuerpo_solicito()))

    def test_numeracion_correlativa(self):
        self.assertEqual(["1.", "2."], self.numeros(self.cuerpo_solicito()))

    def test_el_analisis_va_en_negrita_y_la_muestra_en_cuerpo_menor(self):
        renglones = self.cuerpo_solicito()
        examen = next(t for t in renglones if t[2] == "Hematología completa")
        muestras = [t for t in renglones if t[2] == "Sangre"]
        self.assertEqual("B", examen[3])
        self.assertEqual(pdf_examenes.PT_CUERPO, examen[4])
        self.assertTrue(muestras)
        for muestra in muestras:
            self.assertEqual("", muestra[3])
            self.assertEqual(pdf_examenes.PT_CUERPO_MENOR, muestra[4])

    def test_la_muestra_se_alinea_contra_la_guia_derecha(self):
        """Va donde el récipe pone la cantidad: pegada a `GUIA_DER_MM`."""
        muestras = [t for t in self.cuerpo_solicito() if t[2] == "Sangre"]
        self.assertEqual(2, len(muestras))
        for x, _, texto, estilo, pt in muestras:
            ancho = self.doc._ancho(texto, estilo, pt)
            self.assertAlmostEqual(pdf_examenes.GUIA_DER_MM, x + ancho, places=2)

    def test_la_muestra_va_en_el_renglon_del_analisis(self):
        renglones = self.cuerpo_solicito()
        y_examen = next(t[1] for t in renglones if t[2] == "Hematología completa")
        y_muestra = min(t[1] for t in renglones if t[2] == "Sangre")
        self.assertAlmostEqual(y_examen, y_muestra, places=2)

    def test_un_nombre_largo_no_invade_la_columna_de_la_muestra(self):
        largo = ("Anticuerpos antinucleares por inmunofluorescencia indirecta "
                 "sobre células HEp-2 con titulación y patrón")
        self.componer(_datos([_item(largo, "Sangre")]))
        renglones = self.cuerpo_solicito()
        muestra = next(t for t in renglones if t[2] == "Sangre")
        x_muestra = muestra[0]
        for x, y, texto, estilo, pt in renglones:
            if texto == "Sangre" or not texto.strip():
                continue
            if abs(y - muestra[1]) > 0.01:
                continue
            fin = x + self.doc._ancho(texto, estilo, pt)
            self.assertLess(fin, x_muestra,
                            f"«{texto}» se le mete en la columna de la muestra")

    def test_un_analisis_sin_muestra_ocupa_todo_el_renglon(self):
        self.componer(_datos([_item("Electrocardiograma", "")]))
        texto = self.texto(self.cuerpo_solicito())
        self.assertIn("Electrocardiograma", texto)
        self.assertEqual(["1."], self.numeros(self.cuerpo_solicito()))


# =============================================================================
# Mitad `Ind.`
# =============================================================================

class MitadInd(ReparteElContenido):
    """La mitad que conserva el paciente repite el análisis y lo explica."""

    def setUp(self):
        self.componer(_datos(ITEMS, GENERALES))

    def test_repite_cada_analisis(self):
        texto = self.texto(self.cuerpo_ind())
        self.assertIn("Hematología completa", texto)
        self.assertIn("Glicemia en ayunas", texto)

    def test_trae_las_preparaciones(self):
        texto = self.texto(self.cuerpo_ind())
        self.assertIn("No requiere ayuno.", texto)
        self.assertIn("Ayuno de 8 a 12 horas.", texto)

    def test_no_repite_la_muestra(self):
        """La muestra es asunto del laboratorio: no se duplica acá."""
        self.assertNotIn("Sangre", self.texto(self.cuerpo_ind()))

    def test_usa_los_mismos_numeros_que_la_mitad_solicito(self):
        self.assertEqual(self.numeros(self.cuerpo_solicito()),
                         self.numeros(self.cuerpo_ind()))

    def test_la_preparacion_va_debajo_de_su_analisis(self):
        renglones = self.cuerpo_ind()
        y_examen = next(t[1] for t in renglones if t[2] == "Hematología completa")
        y_prep = next(t[1] for t in renglones
                      if t[2].startswith("No requiere ayuno"))
        self.assertGreater(y_prep, y_examen)
        self.assertAlmostEqual(pdf_examenes.INTERLINEA_MM, y_prep - y_examen,
                               places=2)

    def test_el_analisis_va_en_negrita_y_la_preparacion_en_redonda(self):
        renglones = self.cuerpo_ind()
        examen = next(t for t in renglones if t[2] == "Hematología completa")
        prep = next(t for t in renglones
                    if t[2].startswith("No requiere ayuno"))
        self.assertEqual("B", examen[3])
        self.assertEqual(pdf_examenes.PT_CUERPO, examen[4])
        self.assertEqual("", prep[3])
        self.assertEqual(pdf_examenes.PT_CUERPO_MENOR, prep[4])

    def test_las_generales_van_al_final_y_sin_numero(self):
        renglones = self.cuerpo_ind()
        y_general = next(t[1] for t in renglones
                         if t[2].startswith("Traer los resultados"))
        y_ultimo = max(t[1] for t in renglones
                       if t[2].startswith("Ayuno de 8 a 12 horas"))
        self.assertGreater(y_general, y_ultimo)
        # el bloque general arranca en el margen, no en la sangría de los ítems
        x_general = next(t[0] for t in renglones
                         if t[2].startswith("Traer los resultados"))
        self.assertAlmostEqual(
            pdf_examenes.MITAD_ANCHO_MM + pdf_examenes.MARGEN_IZQ_MM,
            x_general, places=2)

    def test_las_generales_se_separan_mas_que_dos_analisis(self):
        renglones = self.cuerpo_ind()
        y_general = next(t[1] for t in renglones
                         if t[2].startswith("Traer los resultados"))
        y_ultimo = max(t[1] for t in renglones
                       if t[2].startswith("Ayuno de 8 a 12 horas"))
        salto_item = pdf_examenes.INTERLINEA_MM + pdf_examenes.SEPARACION_ITEM_MM
        self.assertGreater(y_general - y_ultimo, salto_item)


# =============================================================================
# Ítems incompletos
# =============================================================================

class AnalisisSinPreparacion(ReparteElContenido):
    """Un análisis sin preparación no puede perder su número."""

    def setUp(self):
        self.componer(_datos([
            _item("Hematología completa", "Sangre", "No requiere ayuno."),
            _item("Grupo sanguíneo y factor Rh", "Sangre", ""),
            _item("Glicemia en ayunas", "Sangre", "Ayuno de 8 a 12 horas."),
        ]))

    def test_se_lista_igual_en_las_dos_mitades(self):
        self.assertIn("Grupo sanguíneo y factor Rh",
                      self.texto(self.cuerpo_solicito()))
        self.assertIn("Grupo sanguíneo y factor Rh",
                      self.texto(self.cuerpo_ind()))

    def test_la_numeracion_no_tiene_huecos(self):
        self.assertEqual(["1.", "2.", "3."], self.numeros(self.cuerpo_solicito()))
        self.assertEqual(["1.", "2.", "3."], self.numeros(self.cuerpo_ind()))

    def test_no_deja_un_renglon_en_blanco(self):
        renglones = self.cuerpo_ind()
        y2 = next(t[1] for t in renglones
                  if t[2] == "Grupo sanguíneo y factor Rh")
        y3 = next(t[1] for t in renglones if t[2] == "Glicemia en ayunas")
        self.assertAlmostEqual(
            pdf_examenes.INTERLINEA_MM + pdf_examenes.SEPARACION_ITEM_MM,
            y3 - y2, places=2,
            msg="un análisis pelado no debe dejar un renglón en blanco")

    def test_solo_generales_sin_ningun_analisis(self):
        self.componer(_datos([], GENERALES))
        self.assertEqual([], self.cuerpo_solicito())
        self.assertIn("Traer los resultados", self.texto(self.cuerpo_ind()))
        self.assertEqual(0.0, self.alto_solicito)
        self.assertGreater(self.alto_ind, 0.0)

    def test_orden_vacia_no_ocupa_nada(self):
        self.componer(_datos([], ""))
        self.assertEqual([], self.cuerpo_solicito())
        self.assertEqual([], self.cuerpo_ind())
        self.assertEqual((0.0, 0.0), (self.alto_solicito, self.alto_ind))


# =============================================================================
# Lo medido es lo dibujado
# =============================================================================

class LoMedidoEsLoDibujado(ReparteElContenido):
    """`medir_contenido` es lo único que evita que el cuerpo pise el pie."""

    CASOS = {
        "un análisis pelado": _datos([_item("Hematología completa")]),
        "análisis con preparación": _datos([
            _item(f"Análisis {i}", "Sangre",
                  "Ayuno de 8 a 12 horas. No ingerir alcohol las 24 horas "
                  "previas al estudio.")
            for i in range(1, 6)]),
        "análisis y bloque general": _datos(
            [_item(f"Análisis {i}", "Sangre", "No requiere ayuno.")
             for i in range(1, 4)],
            "Traer los resultados al control. Presentar la orden en el "
            "laboratorio con la cédula."),
        "sólo bloque general": _datos([], GENERALES),
    }

    def test_el_alto_declarado_coincide_con_el_ultimo_renglon(self):
        """`usado` = última línea de base + una interlínea, en las dos mitades."""
        for nombre, datos in self.CASOS.items():
            with self.subTest(caso=nombre):
                self.componer(datos)
                for mitad, renglones, usado in (
                        ("Solicito", self.cuerpo_solicito(), self.alto_solicito),
                        ("Ind.", self.cuerpo_ind(), self.alto_ind)):
                    if not renglones:
                        self.assertEqual(0.0, usado)
                        continue
                    ultimo = max(t[1] for t in renglones)
                    real = (ultimo + pdf_examenes.INTERLINEA_MM
                            - pdf_examenes.CUERPO_Y0_MM)
                    self.assertAlmostEqual(
                        real, usado, places=2,
                        msg=f"{mitad}: medido {usado:.2f} vs dibujado {real:.2f}")

    def test_el_cuerpo_nunca_pisa_el_cromo_de_la_hoja(self):
        for nombre, datos in self.CASOS.items():
            with self.subTest(caso=nombre):
                self.componer(datos)
                for renglones, limite in (
                        (self.cuerpo_solicito(), pdf_recipe.CUERPO_RP_Y1_MM),
                        (self.cuerpo_ind(), pdf_recipe.CUERPO_IND_Y1_MM)):
                    for _, y, texto, _, _ in renglones:
                        self.assertLessEqual(y, limite, texto)

    def test_ninguna_linea_se_pasa_de_la_guia_derecha(self):
        self.componer(_datos([
            _item("Anticuerpos antinucleares (ANA) con patrón y titulación",
                  "Sangre",
                  "No requiere ayuno. Avisar si está tomando corticoides o "
                  "inmunosupresores en este momento.")],
            "Traer los resultados al control del 5 de septiembre, o antes si "
            "aparece fiebre que no cede."))
        for mitad, ox, renglones in (
                ("Solicito", 0.0, self.cuerpo_solicito()),
                ("Ind.", pdf_examenes.MITAD_ANCHO_MM, self.cuerpo_ind())):
            for x, _, texto, estilo, pt in renglones:
                fin = x + self.doc._ancho(texto, estilo, pt) - ox
                self.assertLessEqual(round(fin, 2), pdf_examenes.GUIA_DER_MM,
                                     f"{mitad}: «{texto}» se pasa de la guía")


# =============================================================================
# Capacidad y errores
# =============================================================================

class NoEntraEnLaHoja(unittest.TestCase):
    """El desborde se avisa, no se imprime cortado."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.destino = os.path.join(self._dir.name, "_no_deberia.pdf")

    def tearDown(self):
        self._dir.cleanup()

    def test_medir_devuelve_las_mismas_claves_que_el_recipe(self):
        datos = _datos(ITEMS, GENERALES)
        mias = set(pdf_examenes.medir_contenido(datos))
        suyas = set(pdf_recipe.medir_contenido({
            "codigo": "EC-0001", "fecha_emision": "26/08/2026",
            "paciente_nombre": "Ana Pérez", "items": [],
            "indicaciones_generales": ""}))
        self.assertEqual(suyas, mias)

    def test_una_orden_normal_entra_holgada(self):
        medida = pdf_examenes.medir_contenido(_datos(ITEMS, GENERALES))
        self.assertTrue(medida["entra"])
        self.assertEqual("completo", medida["nombre_estado"])
        self.assertEqual("Ana Pérez", medida["nombre_impreso"])
        self.assertLess(medida["rp_usado_mm"], medida["rp_disponible_mm"])
        self.assertLess(medida["ind_usado_mm"], medida["ind_disponible_mm"])

    def test_muchas_preparaciones_desbordan_la_mitad_ind(self):
        largo = ("Ayuno estricto de 12 horas, sin ingerir alcohol ni comidas "
                 "grasas las 24 horas previas al estudio. ") * 4
        datos = _datos([_item(f"Análisis {i}", "Sangre", largo)
                        for i in range(1, 5)])
        medida = pdf_examenes.medir_contenido(datos)
        self.assertFalse(medida["entra"])
        self.assertGreater(medida["ind_usado_mm"], medida["ind_disponible_mm"])
        self.assertLess(medida["rp_usado_mm"], medida["rp_disponible_mm"],
                        "la mitad Solicito: no tiene por qué desbordar")
        with self.assertRaises(pdf_examenes.ContenidoNoCabeError) as caja:
            pdf_examenes.generar_examenes(datos, self.destino)
        self.assertEqual(pdf_examenes.MITAD_IND, caja.exception.mitad)
        self.assertFalse(os.path.exists(self.destino),
                         "una orden que no entra no se escribe a disco")

    def test_muchos_analisis_desbordan_la_mitad_solicito(self):
        datos = _datos([_item(f"Análisis {i}", "Sangre")
                        for i in range(1, 26)])
        medida = pdf_examenes.medir_contenido(datos)
        self.assertFalse(medida["entra"])
        self.assertGreater(medida["rp_usado_mm"], medida["rp_disponible_mm"])
        with self.assertRaises(pdf_examenes.ContenidoNoCabeError) as caja:
            pdf_examenes.generar_examenes(datos, self.destino)
        self.assertEqual(pdf_examenes.MITAD_SOLICITO, caja.exception.mitad)
        self.assertGreater(caja.exception.usado_mm, caja.exception.disponible_mm)

    def test_el_nombre_que_no_entra_ni_abreviado_se_rechaza(self):
        nombre = "Wolfeschlegelsteinhausenbergerdorff " * 3
        datos = _datos(ITEMS)
        datos["paciente_nombre"] = nombre.strip()
        medida = pdf_examenes.medir_contenido(datos)
        self.assertEqual("truncado", medida["nombre_estado"])
        self.assertFalse(medida["entra"])
        with self.assertRaises(pdf_examenes.NombreNoCabeError) as caja:
            pdf_examenes.generar_examenes(datos, self.destino)
        self.assertEqual(nombre.strip(), caja.exception.nombre)
        self.assertTrue(caja.exception.impreso.endswith("…"))

    def test_falta_el_logo(self):
        with self.assertRaises(pdf_examenes.RecursoFaltanteError) as caja:
            pdf_examenes.generar_examenes(
                _datos(ITEMS), self.destino,
                ruta_logo=os.path.join(self._dir.name, "no-existe.png"))
        self.assertIn("logo", str(caja.exception))

    def test_faltan_las_fuentes(self):
        with self.assertRaises(pdf_examenes.RecursoFaltanteError):
            pdf_examenes.generar_examenes(
                _datos(ITEMS), self.destino,
                dir_fuentes=os.path.join(self._dir.name, "sin-fuentes"))

    def test_la_familia_de_errores_cuelga_del_tronco_comun(self):
        """`rutas.py` engancha un manejador por tipo; el molde es el del récipe."""
        import pdf_comun
        self.assertTrue(issubclass(pdf_examenes.ExamenesError,
                                   pdf_comun.DocumentoError))
        for error in (pdf_examenes.RecursoFaltanteError,
                      pdf_examenes.ContenidoNoCabeError,
                      pdf_examenes.NombreNoCabeError):
            self.assertTrue(issubclass(error, pdf_examenes.ExamenesError), error)
            self.assertFalse(issubclass(error, pdf_recipe.RecipeError),
                             f"{error.__name__} no puede caer en el manejador "
                             f"del récipe: diría lo que no es")
        self.assertTrue(issubclass(pdf_examenes.RecursoFaltanteError,
                                   pdf_comun.RecursoFaltanteError))

    def test_los_mensajes_son_los_del_recipe(self):
        mio = pdf_examenes.ContenidoNoCabeError("Ind.", 140.0, 129.0)
        suyo = pdf_recipe.ContenidoNoCabeError("Ind.", 140.0, 129.0)
        self.assertEqual(str(suyo), str(mio))
        self.assertEqual((suyo.mitad, suyo.usado_mm, suyo.disponible_mm),
                         (mio.mitad, mio.usado_mm, mio.disponible_mm))
        mio = pdf_examenes.NombreNoCabeError("Nombre Larguísimo", "Nombre…")
        suyo = pdf_recipe.NombreNoCabeError("Nombre Larguísimo", "Nombre…")
        self.assertEqual(str(suyo), str(mio))
        self.assertEqual((suyo.nombre, suyo.impreso), (mio.nombre, mio.impreso))


# =============================================================================
# El récipe sigue intacto
# =============================================================================

class NoRompeElRecipe(unittest.TestCase):
    """Regla 0 del contrato: la salida del récipe no cambia ni un punto."""

    #: Lo único que `pdf_examenes` puede reescribir (§3 del contrato).
    REESCRITOS = {"componer", "_cuerpo_ind"}

    def test_reusa_la_geometria_en_vez_de_copiarla(self):
        """Las constantes que reexporta son LAS del récipe, no copias."""
        for nombre in ("MARGEN_IZQ_MM", "GUIA_DER_MM", "SANGRIA_MM",
                       "INTERLINEA_MM", "SEPARACION_ITEM_MM",
                       "SEPARACION_GENERAL_MM", "CUERPO_Y0_MM", "PIE_RP",
                       "PIE_IND", "LOGO_X_MM", "SALUD_X_MM", "RP_X_MM",
                       "LOGO_X_IND_MM", "SALUD_X_IND_MM", "RP_X_IND_MM",
                       "ALTO_DISPONIBLE_RP_MM", "ALTO_DISPONIBLE_IND_MM",
                       "PT_CUERPO", "PT_CUERPO_MENOR", "PT_RP",
                       "MITAD_ANCHO_MM", "PAGINA_ANCHO_MM", "PAGINA_ALTO_MM"):
            with self.subTest(constante=nombre):
                self.assertEqual(getattr(pdf_recipe, nombre),
                                 getattr(pdf_examenes, nombre))

    def test_hereda_el_cromo_de_la_hoja_sin_reimplementarlo(self):
        """Si alguno dejara de ser el heredado, es que se copió y pegó."""
        for metodo in ("_pintar_ornamento", "_linea_corte", "_encabezado",
                       "_colegiatura", "_pie_paciente", "_ajustar_nombre",
                       "_ancho_nombre_mm", "_abreviar_nombre"):
            with self.subTest(metodo=metodo):
                self.assertIs(getattr(pdf_examenes._OrdenExamenes, metodo),
                              getattr(pdf_recipe._Recipe, metodo))

    def test_solo_reescribe_componer_y_los_cuerpos(self):
        propios = {n for n, v in vars(pdf_examenes._OrdenExamenes).items()
                   if inspect.isfunction(v) and not n.startswith("__")}
        # `_cuerpo_solicito` y `medidas_rotulo` son nuevos, no reescrituras.
        heredados = set(vars(pdf_recipe._Recipe))
        self.assertEqual(self.REESCRITOS, propios & heredados)

    def test_es_una_subclase_del_recipe(self):
        self.assertTrue(issubclass(pdf_examenes._OrdenExamenes,
                                   pdf_recipe._Recipe))

    def test_la_suite_del_recipe_sigue_pasando(self):
        """Corre `tests/test_pdf_recipe.py` entera, que es la red del contrato."""
        import test_pdf_recipe  # noqa: WPS433  (la suite vecina)
        suite = unittest.defaultTestLoader.loadTestsFromModule(test_pdf_recipe)
        salida = io.StringIO()
        resultado = unittest.TextTestRunner(stream=salida, verbosity=0).run(suite)
        self.assertTrue(resultado.wasSuccessful(),
                        "pdf_examenes rompió el récipe:\n" + salida.getvalue())
        self.assertGreater(resultado.testsRun, 10)


if __name__ == "__main__":
    unittest.main()
