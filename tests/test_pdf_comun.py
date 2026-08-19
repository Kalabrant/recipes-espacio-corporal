"""Tests de `pdf_comun.py` — los ladrillos que comparten los tres PDF.

Lo que se fija acá es lo que, si se rompe, se rompe en los tres documentos a la
vez y de forma silenciosa: cómo se parte un texto en renglones, cómo se encaja
una imagen en su caja, cómo se lee una fecha larga, y —lo más importante— que
al pasar de página el membrete se vuelva a poner. Una hoja suelta de una
historia sin logo y sin código de paciente no es un detalle estético: no se
sabe de quién es.

Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import re
import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import pdf_comun  # noqa: E402


class _Espia(pdf_comun.HojaCarta):
    """Igual que la hoja real, pero anota cada renglón y en qué página cayó."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trazos: list[tuple[int, float, float, str, str, float]] = []

    def _texto(self, x, base_y, texto, estilo, pt, color):
        self.trazos.append((self.page, x, base_y, texto, estilo, pt))
        return super()._texto(x, base_y, texto, estilo, pt, color)


def _hoja(codigo: str = "EC-0001") -> _Espia:
    return _Espia(pdf_comun.RUTA_LOGO_DEFECTO, pdf_comun.DIR_FUENTES_DEFECTO,
                  codigo)


class Fechas(unittest.TestCase):
    """El pie de la carta clínica dice «Maracaibo; 18 de Agosto de 2026»."""

    def test_fecha_corta_desde_iso_y_desde_date(self):
        self.assertEqual("18/08/2026", pdf_comun.formatear_fecha("2026-08-18"))
        self.assertEqual("18/08/2026",
                         pdf_comun.formatear_fecha(date(2026, 8, 18)))
        self.assertEqual("18/08/2026", pdf_comun.formatear_fecha("18/08/2026"))

    def test_fecha_larga_con_el_mes_en_mayuscula(self):
        """Como el ejemplo real de la plantilla: «07 de Junio de 2026»."""
        self.assertEqual("18 de Agosto de 2026",
                         pdf_comun.fecha_larga("2026-08-18"))
        self.assertEqual("07 de Junio de 2026",
                         pdf_comun.fecha_larga(date(2026, 6, 7)))

    def test_lo_que_no_es_fecha_se_imprime_tal_cual(self):
        """Si el médico escribió cualquier cosa, sale eso: no se rompe nada."""
        self.assertEqual("a fin de mes", pdf_comun.fecha_larga("a fin de mes"))
        self.assertEqual("", pdf_comun.fecha_larga(None))


class FechasDeLosGraficos(unittest.TestCase):
    """Lo que necesita el eje X de un mini-gráfico (dec. 13 ampliada)."""

    def test_la_fecha_corta_lleva_el_ano_en_dos_cifras(self):
        self.assertEqual("18/08/26", pdf_comun.fecha_corta("2026-08-18"))
        self.assertEqual("07/06/26", pdf_comun.fecha_corta(date(2026, 6, 7)))

    def test_lo_que_no_es_fecha_se_imprime_tal_cual(self):
        self.assertEqual("en enero", pdf_comun.fecha_corta("en enero"))
        self.assertEqual("", pdf_comun.fecha_corta(None))

    def test_el_ordinal_deja_medir_cuantos_dias_pasaron(self):
        self.assertEqual(
            36, pdf_comun.dia_ordinal("2026-03-20")
            - pdf_comun.dia_ordinal("2026-02-12"))

    def test_una_fecha_ilegible_no_tiene_ordinal(self):
        self.assertIsNone(pdf_comun.dia_ordinal("cuando volvió"))
        self.assertIsNone(pdf_comun.dia_ordinal("2026-13-45"))
        self.assertIsNone(pdf_comun.dia_ordinal(None))


class AbscisasDeLosPuntos(unittest.TestCase):
    """Dónde cae cada medición en el eje X: el tiempo tiene que pesar."""

    def test_sin_posiciones_se_reparten_iguales(self):
        self.assertEqual([0.0, 50.0, 100.0],
                         pdf_comun._abscisas(0.0, 100.0, 3))

    def test_con_las_fechas_se_reparten_en_proporcion_al_tiempo(self):
        equis = pdf_comun._abscisas(0.0, 100.0, 3, [0, 25, 100])
        self.assertEqual([0.0, 25.0, 100.0], equis)

    def test_si_todas_cayeron_el_mismo_dia_vuelve_a_repartir_igual(self):
        self.assertEqual([0.0, 50.0, 100.0],
                         pdf_comun._abscisas(0.0, 100.0, 3, [7, 7, 7]))

    def test_una_fecha_ilegible_arrastra_a_toda_la_serie_al_reparto_parejo(self):
        """Mezclar días con huecos daría distancias inventadas."""
        self.assertEqual([0.0, 50.0, 100.0],
                         pdf_comun._abscisas(0.0, 100.0, 3, [0, None, 100]))

    def test_un_solo_punto_va_al_medio(self):
        self.assertEqual([50.0], pdf_comun._abscisas(0.0, 100.0, 1))

    def test_sin_puntos_no_hay_abscisas(self):
        self.assertEqual([], pdf_comun._abscisas(0.0, 100.0, 0))


class MiniGraficoDentroDeSuCaja(unittest.TestCase):
    """El gráfico no puede desbordar el rectángulo que le dieron.

    Se dibujan de a dos por fila y pegados al margen: dos milímetros de más a
    la derecha se meten en el gráfico vecino o se van de la hoja.
    """

    ANCHO = 83.95
    PUNTOS = [("12/02/26", 84.6), ("20/03/26", 83.1), ("07/06/26", 80.1),
              ("18/07/26", 79.3), ("18/08/26", 78.4)]

    def setUp(self):
        self.hoja = _hoja()
        self.hoja.nueva_pagina()
        self.trazado: list[tuple[float, float, float, float]] = []
        real_linea, real_circulo = self.hoja.line, self.hoja.circle

        def linea(x1, y1, x2, y2):
            self.trazado.append((x1, y1, x2, y2))
            return real_linea(x1, y1, x2, y2)

        def circulo(x, y, radio, style=None):
            self.trazado.append((x - radio, y - radio, x + radio, y + radio))
            return real_circulo(x, y, radio, style)

        self.hoja.line = linea          # type: ignore[method-assign]
        self.hoja.circle = circulo      # type: ignore[method-assign]

    def dibujar(self, puntos=None, **extra):
        desde = len(self.hoja.trazos)     # lo de antes es el membrete
        self.alto = self.hoja.mini_grafico(
            20.0, 60.0, self.ANCHO, "Peso (kg)",
            self.PUNTOS if puntos is None else puntos, **extra)
        self.rotulos = self.hoja.trazos[desde:]

    def test_devuelve_el_alto_que_declara_la_constante(self):
        self.dibujar()
        self.assertAlmostEqual(pdf_comun.alto_mini_grafico(), self.alto, places=3)

    def test_todo_el_trazo_queda_adentro_del_rectangulo(self):
        self.dibujar()
        self.assertTrue(self.trazado)
        for x1, y1, x2, y2 in self.trazado:
            for x in (x1, x2):
                self.assertGreaterEqual(round(x, 2), 20.0)
                self.assertLessEqual(round(x, 2), 20.0 + self.ANCHO)
            for y in (y1, y2):
                self.assertGreaterEqual(round(y, 2), 60.0)
                self.assertLessEqual(round(y, 2), 60.0 + self.alto)

    def test_ningun_rotulo_se_pasa_del_ancho_del_grafico(self):
        self.dibujar()
        self.assertTrue(self.rotulos)
        for _, x, _, texto, estilo, pt in self.rotulos:
            fin = x + self.hoja._ancho(texto, estilo, pt)
            self.assertLessEqual(round(fin, 2), 20.0 + self.ANCHO + 0.01, texto)
            self.assertGreaterEqual(round(x, 2), 20.0, texto)

    def test_un_valor_final_larguisimo_se_corre_para_adentro(self):
        """Antes que salirse de la caja, la etiqueta se pega al borde."""
        self.dibujar([("12/02/26", 1.0), ("18/08/26", 123456.789)],
                     formato=lambda v: f"{v:,.3f}")
        finales = [t for t in self.rotulos if "123" in t[3]]
        self.assertTrue(finales)
        for _, x, _, texto, estilo, pt in finales:
            self.assertLessEqual(round(x + self.hoja._ancho(texto, estilo, pt), 2),
                                 20.0 + self.ANCHO + 0.01)

    def test_una_serie_vacia_no_dibuja_nada(self):
        self.dibujar([])
        self.assertEqual([], self.trazado)
        self.assertEqual(0.0, self.alto)

    def test_no_mueve_el_cursor_de_la_hoja(self):
        """El que llama decide dónde sigue el texto: el ladrillo no opina."""
        antes = self.hoja.pluma_y
        self.dibujar()
        self.assertEqual(antes, self.hoja.pluma_y)


class EncajarImagenes(unittest.TestCase):
    """La imagen del anexo entra entera y sin deformarse (Parte C §5)."""

    def test_una_imagen_vertical_se_ajusta_por_alto(self):
        ancho, alto = pdf_comun.encajar(909, 1280, 175.9, 232.0)
        self.assertAlmostEqual(232.0, alto, places=2)
        self.assertLess(ancho, 175.9)
        self.assertAlmostEqual(909 / 1280, ancho / alto, places=4)

    def test_una_imagen_apaisada_se_ajusta_por_ancho(self):
        ancho, alto = pdf_comun.encajar(1600, 900, 175.9, 232.0)
        self.assertAlmostEqual(175.9, ancho, places=2)
        self.assertLess(alto, 232.0)

    def test_una_imagen_que_falta_avisa_donde_la_buscaba(self):
        with self.assertRaises(pdf_comun.RecursoFaltanteError) as caja:
            pdf_comun.medidas_imagen(str(RAIZ / "no-existe" / "foto.jpg"))
        self.assertIn("foto.jpg", str(caja.exception))


class SangriaFrancesa(unittest.TestCase):
    """«Rótulo: valor» de varias líneas no se va media hoja a la derecha."""

    def setUp(self):
        self.hoja = _hoja()
        self.hoja.nueva_pagina()

    def test_el_primer_renglon_es_mas_corto_que_los_demas(self):
        renglones = self.hoja._envolver_colgante(
            "palabra " * 40, 60.0, 160.0, "", 11.0)
        self.assertGreater(len(renglones), 2)
        ancho_primero = self.hoja._ancho(renglones[0], "", 11.0)
        ancho_segundo = self.hoja._ancho(renglones[1], "", 11.0)
        self.assertLessEqual(ancho_primero, 60.0)
        self.assertGreater(ancho_segundo, 60.0)
        self.assertLessEqual(ancho_segundo, 160.0)

    def test_no_se_pierde_ni_una_palabra(self):
        texto = " ".join(f"palabra{i}" for i in range(60))
        renglones = self.hoja._envolver_colgante(texto, 40.0, 150.0, "", 11.0)
        self.assertEqual(texto.split(), " ".join(renglones).split())

    def test_una_palabra_mas_ancha_que_la_columna_se_corta_igual(self):
        renglones = self.hoja._envolver_colgante("A" * 400, 40.0, 60.0, "", 11.0)
        self.assertGreater(len(renglones), 1)
        for renglon in renglones:
            self.assertLessEqual(round(self.hoja._ancho(renglon, "", 11.0), 2),
                                 60.0)

    def test_el_campo_alinea_las_continuaciones_cerca_del_margen(self):
        self.hoja.campo("Crónico-degenerativos:", "detalle " * 40)
        valor = [t for t in self.hoja.trazos if t[3].startswith("detalle")]
        self.assertGreater(len(valor), 2, "hacen falta varios renglones")
        x_continuaciones = {round(t[1], 2) for t in valor[1:]}
        self.assertEqual(
            {round(pdf_comun.MARGEN_IZQ_MM + pdf_comun.SANGRIA_COLGANTE_MM, 2)},
            x_continuaciones)


class MembreteEnCadaPagina(unittest.TestCase):
    """Lo que no se puede perder al pasar de hoja."""

    def setUp(self):
        self.hoja = _hoja("EC-0042")
        self.hoja.nueva_pagina()
        for i in range(120):
            self.hoja.parrafo(f"Renglón número {i} de una historia larga.")

    def test_se_abrieron_varias_paginas(self):
        self.assertGreater(self.hoja.page, 1)

    def test_el_codigo_del_paciente_esta_en_todas(self):
        paginas = {t[0] for t in self.hoja.trazos if t[3] == "EC-0042"}
        self.assertEqual(set(range(1, self.hoja.page + 1)), paginas)

    def test_el_lockup_de_la_marca_esta_en_todas(self):
        paginas = {t[0] for t in self.hoja.trazos
                   if t[3] == pdf_comun.SALUD_TEXTO}
        self.assertEqual(set(range(1, self.hoja.page + 1)), paginas)

    def test_ningun_renglon_pisa_el_pie_de_la_hoja(self):
        for _, _, y, texto, _, _ in self.hoja.trazos:
            self.assertLessEqual(y, pdf_comun.CUERPO_Y1_MM, texto)

    def test_ningun_renglon_se_pasa_de_la_guia_derecha(self):
        for _, x, _, texto, estilo, pt in self.hoja.trazos:
            fin = x + self.hoja._ancho(texto, estilo, pt)
            self.assertLessEqual(round(fin, 2), pdf_comun.GUIA_DER_MM + 0.01,
                                 f"«{texto}» se pasa de la guía derecha")

    def test_numerar_paginas_dice_cuantas_son(self):
        self.hoja.numerar_paginas()
        pies = [t[3] for t in self.hoja.trazos if t[3].startswith("Página ")]
        self.assertEqual(
            [f"Página {n} de {self.hoja.page}"
             for n in range(1, self.hoja.page + 1)],
            pies)


class PieConElCuerpoDeLetraQueCorresponde(unittest.TestCase):
    """El pie de la hoja 2 tiene que salir del mismo tamaño que el de la 1.

    Este es el único lugar del proyecto donde espiar `_texto()` **no alcanza**,
    porque el defecto no está en lo que se pide sino en lo que termina escrito
    en el PDF. fpdf2 lleva la cuenta de la fuente por documento y no por
    página: escribe el operador `Tf` solo cuando la fuente cambia y después
    confía en que sigue vigente. La numeración salta de página a mano —eso la
    biblioteca no lo ve—, así que sin `_ir_a_pagina` el pie de la hoja 2 en
    adelante se dibujaba con el cuerpo que hubiera quedado en ESA hoja (11 pt
    en una historia, 9,5 pt en una de anexos) y, como el ancho para alinearlo
    a la derecha se midió en 8,5 pt, terminaba hasta 5 mm afuera de la guía.

    Por eso se mira el contenido crudo de cada página: ahí está la verdad.
    """

    #: `/F1 8.50 Tf` — cualquier fuente, el cuerpo del pie de `numerar_paginas`.
    _TF_PIE = re.compile(rb"/F\d+ 8\.50 Tf")

    def setUp(self):
        self.hoja = _hoja("EC-0042")
        # Dos hojas que terminan con cuerpos de letra DISTINTOS entre sí y
        # distintos del pie: es la trampa que destapó el defecto.
        self.hoja.nueva_pagina()
        self.hoja.parrafo("Cuerpo de la primera hoja.", pt=11.0)
        self.hoja.nueva_pagina()
        self.hoja.parrafo("Cuerpo de la segunda hoja.", pt=9.5)
        self.hoja.numerar_paginas()

    def _contenido(self, numero: int) -> bytes:
        return bytes(self.hoja.pages[numero].contents)

    def test_todas_las_hojas_declaran_la_fuente_del_pie(self):
        for numero in range(1, self.hoja.page + 1):
            self.assertRegex(
                self._contenido(numero), self._TF_PIE,
                f"la hoja {numero} no declara el cuerpo 8,5 pt del pie: se va a "
                "dibujar con el que haya quedado de antes y se pasa de la guía")

    def test_el_pie_es_lo_ultimo_que_se_declara_en_cada_hoja(self):
        """Si quedara otro `Tf` después, el pie saldría con ese cuerpo."""
        for numero in range(1, self.hoja.page + 1):
            tamanios = re.findall(rb"/F\d+ ([\d.]+) Tf", self._contenido(numero))
            self.assertEqual(b"8.50", tamanios[-1],
                             f"en la hoja {numero} el pie no es el último texto")

    def test_el_arreglo_no_deja_el_documento_en_una_pagina_ajena(self):
        """Después de numerar hay que volver donde estábamos."""
        self.assertEqual(2, self.hoja.page)


class UnaSolaPaginaNoSeNumera(unittest.TestCase):
    """Numerar «Página 1 de 1» sería ruido en una carta de una carilla."""

    def test_sin_pie_de_pagina(self):
        hoja = _hoja()
        hoja.nueva_pagina()
        hoja.parrafo("Un informe corto.")
        hoja.numerar_paginas()
        self.assertEqual([], [t for t in hoja.trazos
                              if t[3].startswith("Página ")])


if __name__ == "__main__":
    unittest.main()
