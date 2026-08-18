"""Tests de `pdf_recipe.py` — el reparto del contenido entre las dos mitades.

Lo que fija esta suite es la **decisión 5 del médico**, que es la que se puede
romper sin que nadie se dé cuenta hasta que el récipe ya está impreso:

  - Mitad `Rp.` (se presenta en la farmacia y a veces queda allí): SOLO la
    lista numerada con presentación y cantidad. Sin dosis y sin indicaciones.
  - Mitad `Ind.` (la conserva el paciente): cada medicamento repetido con SU
    MISMO NÚMERO y, debajo, su dosis y sus indicaciones. Sin cantidad. Al
    final, separado, el bloque de indicaciones generales.

También se verifica la invariante que protege la hoja: lo que `medir_contenido`
dice que ocupa el cuerpo tiene que ser lo que realmente se dibuja, porque de esa
cuenta depende que el texto no se meta encima del bloque `Dr./CI/MPPS` ni del
renglón `Paciente:`.

No se lee el PDF con un visor: se espía `_texto()`, que es por donde pasa toda
la tinta de texto del módulo. Así la suite sigue siendo `unittest` de la stdlib
y no agrega dependencias (§3 de las instrucciones).

Se corre con:  py -3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import pdf_recipe  # noqa: E402


#: Debajo de acá empieza el bloque Dr./CI/MPPS (raya del Dr. en 170,1).
TOPE_CUERPO_RP_MM = 168.0
#: Debajo de acá está el renglón Paciente:/Fecha: de la mitad Ind. (193,8).
TOPE_CUERPO_IND_MM = 190.0


class _Espia(pdf_recipe._Recipe):
    """Igual que el compositor real, pero anota cada renglón que escribe."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trazos: list[tuple[float, float, str, str, float]] = []

    def _texto(self, x, base_y, texto, estilo, pt, color):
        self.trazos.append((x, base_y, texto, estilo, pt))
        return super()._texto(x, base_y, texto, estilo, pt, color)


def _item(nombre, presentacion="Tabletas", cantidad="10 tabletas",
          dosis="", indicaciones=""):
    return {"medicamento": nombre, "presentacion": presentacion,
            "cantidad": cantidad, "dosis": dosis, "indicaciones": indicaciones}


def _datos(items, generales=""):
    return {
        "codigo": "EC-2026-0001",
        "fecha_emision": "14/08/2026",
        "paciente_nombre": "Ana Pérez",
        "items": items,
        "indicaciones_generales": generales,
    }


class ReparteElContenido(unittest.TestCase):
    """Base: compone un récipe y deja el cuerpo de cada mitad a mano."""

    def componer(self, datos):
        doc = _Espia(pdf_recipe.RUTA_LOGO_DEFECTO, pdf_recipe.DIR_FUENTES_DEFECTO)
        self.alto_rp, self.alto_ind = doc.componer(datos, dibujar=True)
        self.doc = doc
        return doc

    def _cuerpo(self, x0, x1, tope):
        """Renglones del cuerpo libre de una mitad, ordenados por altura.

        Se descarta el cromo fijo (código arriba, colegiatura y pie abajo)
        acotando la franja vertical al cuerpo.
        """
        return [t for t in self.doc.trazos
                if x0 <= t[0] < x1 and pdf_recipe.CUERPO_Y0_MM <= t[1] <= tope]

    def cuerpo_rp(self):
        return sorted(self._cuerpo(0.0, pdf_recipe.MITAD_ANCHO_MM,
                                   TOPE_CUERPO_RP_MM), key=lambda t: (t[1], t[0]))

    def cuerpo_ind(self):
        return sorted(self._cuerpo(pdf_recipe.MITAD_ANCHO_MM,
                                   pdf_recipe.PAGINA_ANCHO_MM,
                                   TOPE_CUERPO_IND_MM), key=lambda t: (t[1], t[0]))

    @staticmethod
    def texto(renglones):
        return " ".join(t[2] for t in renglones)

    @staticmethod
    def numeros(renglones):
        """Los marcadores «1.» «2.» ... en el orden en que se dibujaron."""
        return [t[2] for t in renglones
                if t[2].rstrip(".").isdigit() and t[2].endswith(".")]


class MitadRp(ReparteElContenido):
    """La mitad que va a la farmacia dice QUÉ despachar, y nada más."""

    ITEMS = [
        _item("Amoxicilina 500 mg", "Cápsulas", "14 cápsulas",
              dosis="1 cápsula cada 8 horas durante 7 días.",
              indicaciones="Tomar con las comidas."),
        _item("Ibuprofeno 400 mg", "Comprimidos", "20 comprimidos",
              dosis="1 comprimido cada 8 horas si hay dolor.",
              indicaciones="No tomar en ayunas."),
    ]

    def setUp(self):
        self.componer(_datos(self.ITEMS, "Reposo relativo por 48 horas."))

    def test_lista_medicamento_presentacion_y_cantidad(self):
        texto = self.texto(self.cuerpo_rp())
        for esperado in ("Amoxicilina 500 mg", "Cápsulas", "14 cápsulas",
                         "Ibuprofeno 400 mg", "Comprimidos", "20 comprimidos"):
            self.assertIn(esperado, texto)

    def test_no_baja_la_dosis(self):
        texto = self.texto(self.cuerpo_rp())
        for prohibido in ("cada 8 horas", "durante 7 días", "si hay dolor"):
            self.assertNotIn(prohibido, texto,
                             "la dosis no va en la mitad que queda en la farmacia")

    def test_no_bajan_las_indicaciones(self):
        texto = self.texto(self.cuerpo_rp())
        for prohibido in ("Tomar con las comidas", "No tomar en ayunas"):
            self.assertNotIn(prohibido, texto)

    def test_no_baja_el_bloque_de_indicaciones_generales(self):
        self.assertNotIn("Reposo relativo", self.texto(self.cuerpo_rp()))

    def test_numeracion_correlativa(self):
        self.assertEqual(["1.", "2."], self.numeros(self.cuerpo_rp()))

    def test_la_cantidad_se_alinea_contra_la_guia_derecha(self):
        """La cantidad va pegada a `GUIA_DER_MM`, que es donde mueren las rayas."""
        cantidades = [t for t in self.cuerpo_rp() if t[2] == "14 cápsulas"]
        self.assertEqual(1, len(cantidades))
        x, _, texto, estilo, pt = cantidades[0]
        ancho = self.doc._ancho(texto, estilo, pt)
        self.assertAlmostEqual(pdf_recipe.GUIA_DER_MM, x + ancho, places=2)


class MitadInd(ReparteElContenido):
    """La mitad que conserva el paciente repite el medicamento y explica."""

    ITEMS = [
        _item("Amoxicilina 500 mg", "Cápsulas", "14 cápsulas",
              dosis="1 cápsula cada 8 horas durante 7 días.",
              indicaciones="Tomar con las comidas."),
        _item("Ibuprofeno 400 mg", "Comprimidos", "20 comprimidos",
              dosis="1 comprimido cada 8 horas si hay dolor.",
              indicaciones="No tomar en ayunas."),
    ]

    def setUp(self):
        self.componer(_datos(self.ITEMS, "Reposo relativo por 48 horas."))

    def test_repite_cada_medicamento(self):
        texto = self.texto(self.cuerpo_ind())
        self.assertIn("Amoxicilina 500 mg", texto)
        self.assertIn("Ibuprofeno 400 mg", texto)

    def test_trae_dosis_e_indicaciones(self):
        texto = self.texto(self.cuerpo_ind())
        for esperado in ("1 cápsula cada 8 horas durante 7 días.",
                         "Tomar con las comidas.",
                         "1 comprimido cada 8 horas si hay dolor.",
                         "No tomar en ayunas."):
            self.assertIn(esperado, texto)

    def test_no_repite_la_cantidad(self):
        """La cantidad es asunto de la farmacia: no se duplica acá."""
        texto = self.texto(self.cuerpo_ind())
        self.assertNotIn("14 cápsulas", texto)
        self.assertNotIn("20 comprimidos", texto)

    def test_no_repite_la_presentacion(self):
        texto = self.texto(self.cuerpo_ind())
        self.assertNotIn("Cápsulas", texto)
        self.assertNotIn("Comprimidos", texto)

    def test_usa_los_mismos_numeros_que_el_rp(self):
        self.assertEqual(self.numeros(self.cuerpo_rp()),
                         self.numeros(self.cuerpo_ind()))

    def test_la_dosis_va_debajo_de_su_medicamento(self):
        renglones = self.cuerpo_ind()
        y_nombre = next(t[1] for t in renglones if t[2] == "Amoxicilina 500 mg")
        y_dosis = next(t[1] for t in renglones
                       if t[2].startswith("1 cápsula cada 8 horas"))
        self.assertGreater(y_dosis, y_nombre)
        self.assertAlmostEqual(pdf_recipe.INTERLINEA_MM, y_dosis - y_nombre,
                               places=2)

    def test_el_medicamento_va_en_negrita_y_el_detalle_en_redonda(self):
        renglones = self.cuerpo_ind()
        nombre = next(t for t in renglones if t[2] == "Amoxicilina 500 mg")
        dosis = next(t for t in renglones
                     if t[2].startswith("1 cápsula cada 8 horas"))
        self.assertEqual("B", nombre[3])
        self.assertEqual(pdf_recipe.PT_CUERPO, nombre[4])
        self.assertEqual("", dosis[3])
        self.assertEqual(pdf_recipe.PT_CUERPO_MENOR, dosis[4])

    def test_las_generales_van_al_final_y_sin_numero(self):
        renglones = self.cuerpo_ind()
        y_general = next(t[1] for t in renglones
                         if t[2].startswith("Reposo relativo"))
        y_ultimo_item = max(t[1] for t in renglones
                            if t[2].startswith("No tomar en ayunas"))
        self.assertGreater(y_general, y_ultimo_item)
        # el bloque general arranca en el margen, no en la sangría de los items
        x_general = next(t[0] for t in renglones
                         if t[2].startswith("Reposo relativo"))
        self.assertAlmostEqual(pdf_recipe.MITAD_ANCHO_MM + pdf_recipe.MARGEN_IZQ_MM,
                               x_general, places=2)

    def test_las_generales_se_separan_mas_que_dos_items(self):
        renglones = self.cuerpo_ind()
        y_general = next(t[1] for t in renglones
                         if t[2].startswith("Reposo relativo"))
        y_ultimo = max(t[1] for t in renglones
                       if t[2].startswith("No tomar en ayunas"))
        salto_general = y_general - y_ultimo
        salto_item = pdf_recipe.INTERLINEA_MM + pdf_recipe.SEPARACION_ITEM_MM
        self.assertGreater(salto_general, salto_item)


class ItemsIncompletos(ReparteElContenido):
    """Un renglón sin dosis o sin indicaciones no puede perder su número."""

    def test_item_sin_indicaciones_conserva_su_numero(self):
        self.componer(_datos([
            _item("Amoxicilina 500 mg", dosis="1 cada 8 horas.",
                  indicaciones="Con las comidas."),
            _item("Solución salina 0,9 %", "Spray nasal 30 ml", "1 frasco",
                  dosis="2 aplicaciones por fosa nasal.", indicaciones=""),
            _item("Loratadina 10 mg", dosis="1 en la noche.",
                  indicaciones="Puede dar somnolencia."),
        ]))
        self.assertEqual(["1.", "2.", "3."], self.numeros(self.cuerpo_ind()))
        self.assertEqual(["1.", "2.", "3."], self.numeros(self.cuerpo_rp()))
        self.assertIn("Solución salina 0,9 %", self.texto(self.cuerpo_ind()))

    def test_item_sin_dosis_ni_indicaciones_sale_solo_con_el_nombre(self):
        self.componer(_datos([
            _item("Amoxicilina 500 mg", dosis="", indicaciones=""),
            _item("Ibuprofeno 400 mg", dosis="1 cada 8 horas.",
                  indicaciones=""),
        ]))
        renglones = self.cuerpo_ind()
        self.assertEqual(["1.", "2."], self.numeros(renglones))
        # el item 1 no arrastra ningún renglón subordinado
        y1 = next(t[1] for t in renglones if t[2] == "Amoxicilina 500 mg")
        y2 = next(t[1] for t in renglones if t[2] == "Ibuprofeno 400 mg")
        self.assertAlmostEqual(
            pdf_recipe.INTERLINEA_MM + pdf_recipe.SEPARACION_ITEM_MM, y2 - y1,
            places=2, msg="un item pelado no debe dejar un renglón en blanco")

    def test_solo_generales_sin_ningun_medicamento(self):
        self.componer(_datos([], "Reposo relativo por 48 horas."))
        self.assertEqual([], self.cuerpo_rp())
        self.assertIn("Reposo relativo", self.texto(self.cuerpo_ind()))
        self.assertEqual(0.0, self.alto_rp)
        self.assertGreater(self.alto_ind, 0.0)

    def test_receta_vacia_no_ocupa_nada(self):
        self.componer(_datos([], ""))
        self.assertEqual([], self.cuerpo_rp())
        self.assertEqual([], self.cuerpo_ind())
        self.assertEqual((0.0, 0.0), (self.alto_rp, self.alto_ind))


class LoMedidoEsLoDibujado(ReparteElContenido):
    """`medir_contenido` es lo único que evita que el cuerpo pise el pie."""

    CASOS = {
        "un item pelado": _datos([_item("Amoxicilina 500 mg")]),
        "items con dosis e indicaciones": _datos([
            _item(f"Medicamento {i} 500 mg",
                  dosis="1 tableta cada 8 horas durante 7 días.",
                  indicaciones="Tomar con las comidas, nunca en ayunas.")
            for i in range(1, 6)]),
        "items y bloque general": _datos(
            [_item(f"Medicamento {i}", dosis="1 cada 8 horas.") for i in range(1, 4)],
            "Reposo relativo por 48 horas. Abundantes líquidos durante el día."),
        "solo bloque general": _datos([], "Reposo relativo por 48 horas."),
    }

    def test_el_alto_declarado_coincide_con_el_ultimo_renglon(self):
        """`usado` = última línea de base + una interlínea, en las dos mitades."""
        for nombre, datos in self.CASOS.items():
            with self.subTest(caso=nombre):
                self.componer(datos)
                for mitad, renglones, usado in (
                        ("Rp.", self.cuerpo_rp(), self.alto_rp),
                        ("Ind.", self.cuerpo_ind(), self.alto_ind)):
                    if not renglones:
                        self.assertEqual(0.0, usado)
                        continue
                    ultimo = max(t[1] for t in renglones)
                    real = ultimo + pdf_recipe.INTERLINEA_MM - pdf_recipe.CUERPO_Y0_MM
                    self.assertAlmostEqual(
                        real, usado, places=2,
                        msg=f"{mitad}: medido {usado:.2f} vs dibujado {real:.2f}")

    def test_el_cuerpo_nunca_pisa_el_cromo_de_la_hoja(self):
        for nombre, datos in self.CASOS.items():
            with self.subTest(caso=nombre):
                self.componer(datos)
                for renglones, limite in ((self.cuerpo_rp(),
                                           pdf_recipe.CUERPO_RP_Y1_MM),
                                          (self.cuerpo_ind(),
                                           pdf_recipe.CUERPO_IND_Y1_MM)):
                    for _, y, texto, _, _ in renglones:
                        self.assertLessEqual(y, limite, texto)

    def test_ninguna_linea_se_pasa_de_la_guia_derecha(self):
        datos = _datos([
            _item("Amoxicilina / Ácido clavulánico 875/125 mg",
                  "Tabletas recubiertas", "14 tabletas",
                  dosis="1 tableta vía oral cada 12 horas durante 7 días.",
                  indicaciones="Tomar con las comidas para reducir la molestia "
                               "estomacal y completar el tratamiento entero.")],
            "Control en consulta dentro de 8 días, o antes si aparece fiebre "
            "que no cede o dificultad para respirar.")
        self.componer(datos)
        for mitad, ox, renglones in (("Rp.", 0.0, self.cuerpo_rp()),
                                     ("Ind.", pdf_recipe.MITAD_ANCHO_MM,
                                      self.cuerpo_ind())):
            for x, _, texto, estilo, pt in renglones:
                fin = x + self.doc._ancho(texto, estilo, pt) - ox
                self.assertLessEqual(round(fin, 2), pdf_recipe.GUIA_DER_MM,
                                     f"{mitad}: «{texto}» se pasa de la guía")


class NoEntraEnLaHoja(unittest.TestCase):
    """El desborde se avisa, no se imprime cortado."""

    @staticmethod
    def medir(datos):
        return pdf_recipe.medir_contenido(datos)

    def test_muchas_indicaciones_desbordan_la_mitad_ind(self):
        largo = ("Tomar con abundante agua y nunca en ayunas, evitando los "
                 "lácteos en la hora previa y posterior a cada toma. ") * 4
        datos = _datos([_item(f"Medicamento {i}", dosis="1 cada 8 horas.",
                              indicaciones=largo) for i in range(1, 5)])
        medida = self.medir(datos)
        self.assertFalse(medida["entra"])
        self.assertGreater(medida["ind_usado_mm"], medida["ind_disponible_mm"])
        self.assertLess(medida["rp_usado_mm"], medida["rp_disponible_mm"],
                        "la mitad Rp. no tiene por qué desbordar: no lleva texto")
        with self.assertRaises(pdf_recipe.ContenidoNoCabeError) as caja:
            pdf_recipe.generar_recipe(datos, str(RAIZ / "build" / "_no_deberia.pdf"))
        self.assertEqual("Ind.", caja.exception.mitad)

    def test_muchos_medicamentos_desbordan_la_mitad_rp(self):
        datos = _datos([_item(f"Medicamento {i}") for i in range(1, 26)])
        medida = self.medir(datos)
        self.assertFalse(medida["entra"])
        self.assertGreater(medida["rp_usado_mm"], medida["rp_disponible_mm"])
        with self.assertRaises(pdf_recipe.ContenidoNoCabeError) as caja:
            pdf_recipe.generar_recipe(datos, str(RAIZ / "build" / "_no_deberia.pdf"))
        self.assertEqual("Rp.", caja.exception.mitad)

    def test_un_recipe_normal_entra_holgado(self):
        datos = _datos([
            _item("Amoxicilina 500 mg", "Cápsulas", "14 cápsulas",
                  dosis="1 cápsula cada 8 horas durante 7 días.",
                  indicaciones="Tomar con las comidas."),
            _item("Ibuprofeno 400 mg", "Comprimidos", "20 comprimidos",
                  dosis="1 comprimido cada 8 horas si hay dolor.",
                  indicaciones="No tomar en ayunas."),
        ], "Reposo relativo por 48 horas.")
        medida = self.medir(datos)
        self.assertTrue(medida["entra"])
        self.assertEqual("completo", medida["nombre_estado"])


if __name__ == "__main__":
    unittest.main()
