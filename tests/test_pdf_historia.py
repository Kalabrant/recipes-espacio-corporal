"""Tests de `pdf_historia.py` — la historia clínica imprimible.

Lo que fija esta suite:

  - Se imprime **solo lo que tiene contenido**. Una historia recién empezada
    sale en una carilla; un formulario impreso con veinte huecos vacíos es
    exactamente el papel que el médico vino a dejar atrás.
  - Las **alergias** salen arriba, destacadas y una sola vez: es lo único de la
    historia que puede hacer daño si no se ve.
  - Las consultas van de la **más nueva a la más vieja**, con los signos
    vitales del papel y sin las casillas que quedaron vacías.
  - Se respeta lo que el médico tachó en `referencias/Historia clínica.pdf`:
    no aparecen "heredo", ni el interrogatorio por aparatos, ni la exploración
    física por regiones, ni los campos de hospital.

Se espía `_texto()`, igual que en `test_pdf_recipe.py`, anotando la página.
Solo `unittest` de la stdlib (§3).

Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import pdf_comun  # noqa: E402
import pdf_historia  # noqa: E402

PACIENTE = {
    "nombre": "María Fernanda Rodríguez Blanco",
    "cedula": "V-7856151",
    "fecha_nacimiento": "1966-03-12",
    "edad": 60,
    "sexo": "Femenino",
    "telefono": "0414-6612233",
}

HISTORIA = {
    "estado_civil": "Casada",
    "ocupacion": "Docente universitaria",
    "tipo_sangre": "O+",
    "fam_madre": "Hipertensión arterial desde los 55 años.",
    "fam_padre": "Diabetes mellitus tipo 2.",
    "fam_hermanos": "",
    "fam_hijos": "Dos hijos sanos.",
    "alim_comidas_dia": 3,
    "alim_frutas_verduras": 4,
    "alim_pescado": 1,
    "alim_litros_agua": 1,
    "actividad_fisica": "Caminata 30 minutos, 3 veces por semana.",
    "habitacion": "Casa propia, vive con esposo y dos hijos.",
    "cronico_degenerativos": "Dislipidemia desde 2021.",
    "alcoholismo": "Ocasional, social.",
    "tabaquismo": "Niega.",
    "quirurgicos": "Colecistectomía laparoscópica en 2019.",
    "alergias": "Penicilina (rash generalizado, 2008).",
    "notas_generales": "Paciente muy adherente al control.",
}

CONSULTAS = [
    {"fecha": "2026-08-14", "motivo": "Control de peso.",
     "examen_fisico": "Obesidad de predominio central.",
     "evolucion": "Refiere aumento de 4 kg desde la última consulta.",
     "diagnostico": "Obesidad grado II.",
     "plan": "Perfil lipídico y control en 30 días.",
     "ta_sistolica": 138, "ta_diastolica": 86, "fc": 78, "temperatura": 36.6,
     "peso": 97.9, "talla": 1.68, "imc": 34.6},
    {"fecha": "2026-05-09", "motivo": "Primera consulta.",
     "evolucion": "Aumento de peso de 18 meses de evolución.",
     "ta_sistolica": 142, "ta_diastolica": 90, "peso": 93.8},
]

DATOS = {
    "codigo": "EC-0007",
    "fecha": "2026-08-18",
    "paciente": PACIENTE,
    "historia": HISTORIA,
    "consultas": CONSULTAS,
}

#: Fechas separadas a propósito de forma **irregular** (36, 79, 41 y 31 días):
#: es lo que permite comprobar que el eje X se reparte en proporción al tiempo
#: y no en cinco casilleros iguales.
FECHAS = ("2026-02-12", "2026-03-20", "2026-06-07", "2026-07-18", "2026-08-18")


def _serie(fechas, valores):
    return [{"fecha": f, "valor": v} for f, v in zip(fechas, valores)]


#: Lo que devuelve `GET /api/pacientes/<id>/evolucion`: tres métricas con
#: mediciones de sobra, una vacía y una con una sola. Las dos últimas no
#: tienen que llegar al papel.
EVOLUCION = {"series": {
    "peso": _serie(FECHAS, (84.6, 83.1, 80.1, 79.3, 78.4)),
    "imc": _serie(FECHAS, (33.9, 33.3, 32.1, 31.8, 31.4)),
    "grasa_pct": _serie(FECHAS, (42.1, 41.4, 39.8, 39.1, 38.3)),
    "musculo_kg": [],
    "grasa_visceral": _serie(FECHAS[:1], (12,)),
}}

EVOLUCION_COMPLETA = {"series": dict(
    EVOLUCION["series"],
    musculo_kg=_serie(FECHAS, (44.2, 44.5, 45.0, 45.2, 45.6)),
    grasa_visceral=_serie(FECHAS, (12, 12, 11, 11, 10)),
)}


class _Espia(pdf_historia._Historia):
    """El compositor real, anotando cada renglón, cada trazo y su página.

    Los mini-gráficos de la sección EVOLUCIÓN no escriben solo texto: dibujan
    líneas y puntos, y eso también tiene que caer adentro de los márgenes y en
    la hoja que corresponde. Por eso se espían además `line` y `circle`, que
    son por donde pasa **todo** el dibujo del módulo.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trazos: list[tuple[int, float, float, str, str, float]] = []
        self.lineas: list[tuple[int, float, float, float, float, tuple]] = []
        self.circulos: list[tuple[int, float, float, float]] = []
        self.color_trazo: tuple[int, int, int] = (0, 0, 0)

    def _texto(self, x, base_y, texto, estilo, pt, color):
        self.trazos.append((self.page, x, base_y, texto, estilo, pt))
        return super()._texto(x, base_y, texto, estilo, pt, color)

    def set_draw_color(self, r, g=-1, b=-1):
        self.color_trazo = (r, g, b)
        return super().set_draw_color(r, g, b)

    def line(self, x1, y1, x2, y2):
        self.lineas.append((self.page, x1, y1, x2, y2, self.color_trazo))
        return super().line(x1, y1, x2, y2)

    def circle(self, x, y, radius, style=None):
        self.circulos.append((self.page, x, y, radius))
        return super().circle(x, y, radius, style)


class BaseHistoriaPDF(unittest.TestCase):

    def setUp(self) -> None:
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)

        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_historia_pdf_"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)

        real = pdf_historia._Historia
        self.addCleanup(setattr, pdf_historia, "_Historia", real)
        self.doc: _Espia | None = None

        def recordar(*args, **kwargs):
            self.doc = _Espia(*args, **kwargs)
            return self.doc

        pdf_historia._Historia = recordar        # type: ignore[misc]

    def generar(self, datos=None) -> Path:
        destino = self.carpeta / "historia.pdf"
        pdf_historia.generar_historia(datos if datos is not None else DATOS,
                                      str(destino))
        return destino

    @property
    def texto(self) -> str:
        return " ".join(t[3] for t in self.doc.trazos)

    def renglones(self, contiene: str):
        return [t for t in self.doc.trazos if contiene in t[3]]

    def y_de(self, contiene: str) -> tuple[int, float]:
        encontrados = self.renglones(contiene)
        self.assertTrue(encontrados, f"no se imprimió «{contiene}»")
        return encontrados[0][0], encontrados[0][2]

    # -- mini-gráficos -----------------------------------------------------
    @property
    def titulos_grafico(self):
        """Los `(página, x, base_y, texto, …)` de los títulos de los gráficos.

        Se los reconoce por negrita a 8,5 pt, que en esta hoja no usa nada
        más: los rótulos de las celdas van a 8,5 pt pero en redonda, y los
        títulos de sección a 11,5 pt.
        """
        return [t for t in self.doc.trazos
                if t[4] == "B"
                and abs(t[5] - pdf_comun.GRAFICO_PT_TITULO) < 0.01]

    def puntos_del_grafico(self, titulo: str):
        """Los puntos dibujados **dentro de la caja** del gráfico `titulo`.

        Si un gráfico se hubiera partido entre dos hojas, o si su segunda
        columna se hubiera ido de la caja, acá faltarían puntos: el filtro es
        por página y por rectángulo.
        """
        cabecera = [t for t in self.titulos_grafico if t[3] == titulo]
        self.assertEqual(1, len(cabecera), f"título de gráfico «{titulo}»")
        pagina, x, base_y = cabecera[0][0], cabecera[0][1], cabecera[0][2]
        ancho = ((pdf_comun.ANCHO_UTIL_MM - pdf_historia.SEPARACION_GRAFICOS_MM
                  * (pdf_historia.GRAFICOS_POR_FILA - 1))
                 / pdf_historia.GRAFICOS_POR_FILA)
        alto = pdf_comun.alto_mini_grafico()
        return [c for c in self.doc.circulos
                if c[0] == pagina
                and x - 0.01 <= c[1] <= x + ancho + 0.01
                and base_y < c[2] < base_y + alto]


class HistoriaCompleta(BaseHistoriaPDF):

    def setUp(self) -> None:
        super().setUp()
        self.generar()

    def test_titulo_y_codigo_del_paciente(self):
        self.assertIn("HISTORIA CLÍNICA", self.texto)
        self.assertIn("EC-0007", self.texto)

    def test_la_ficha_trae_lo_que_quedo_del_papel(self):
        for esperado in ("María Fernanda Rodríguez Blanco", "V-7856151",
                         "12/03/1966", "60 años", "Femenino", "O+",
                         "Casada", "Docente universitaria"):
            self.assertIn(esperado, self.texto)

    def test_no_imprime_los_campos_de_hospital_que_el_medico_tacho(self):
        for tachado in ("Afiliación", "Cama", "Residente", "Escolaridad",
                        "Religión", "Origen", "Clínica de Adscripción",
                        "Tipo de Interrogatorio", "Elaboró"):
            self.assertNotIn(tachado, self.texto)

    def test_antecedentes_familiares_sin_la_palabra_heredo(self):
        """El médico tachó «HEREDO» del rótulo del papel."""
        self.assertIn("ANTECEDENTES FAMILIARES", self.texto)
        self.assertNotIn("HEREDO", self.texto.upper())

    def test_no_imprime_el_interrogatorio_ni_la_exploracion_por_regiones(self):
        for tachado in ("INTERROGATORIO", "EXPLORACIÓN FÍSICA", "HABITUS",
                        "Astenia", "Disuria"):
            self.assertNotIn(tachado, self.texto)

    def test_los_campos_familiares_vacios_no_se_imprimen(self):
        self.assertIn("Madre:", self.texto)
        self.assertIn("Hijos:", self.texto)
        self.assertNotIn("Hermanos:", self.texto)

    def test_los_patologicos_vacios_no_se_imprimen(self):
        self.assertIn("Crónico-degenerativos:", self.texto)
        self.assertIn("Quirúrgicos:", self.texto)
        for vacio in ("Toxicomanías:", "Traumáticos:", "Ginecológicos:",
                      "Hospitalizaciones previas:", "Transfusiones:"):
            self.assertNotIn(vacio, self.texto)

    def test_alimentacion_con_los_denominadores_del_papel(self):
        alimentacion = self.renglones("Comidas al día")
        self.assertTrue(alimentacion)
        texto = " ".join(t[3] for t in alimentacion)
        self.assertIn("Comidas al día 3/3", texto)
        self.assertIn("Frutas y verduras 4/7", texto)
        self.assertIn("Pescado 1/7", texto)
        self.assertIn("Litros de agua al día 1/2", texto)
        # los numeradores que el médico no cargó no salen
        self.assertNotIn("Pollo", texto)

    def test_las_alergias_van_arriba_de_los_antecedentes(self):
        _, y_alergias = self.y_de("ALERGIAS:")
        _, y_familiares = self.y_de("ANTECEDENTES FAMILIARES")
        self.assertLess(y_alergias, y_familiares)

    def test_las_alergias_no_se_imprimen_dos_veces(self):
        self.assertEqual(1, len(self.renglones("Penicilina")))
        self.assertNotIn("Alergias:", self.texto)

    def test_las_consultas_van_de_la_mas_nueva_a_la_mas_vieja(self):
        (pag_nueva, y_nueva) = self.y_de("14/08/2026")
        (pag_vieja, y_vieja) = self.y_de("09/05/2026")
        self.assertLessEqual(pag_nueva, pag_vieja)
        if pag_nueva == pag_vieja:
            self.assertLess(y_nueva, y_vieja)

    def test_cada_consulta_trae_su_motivo_examen_evolucion_y_plan(self):
        for esperado in ("Motivo de consulta:", "Control de peso.",
                         "Examen físico:", "Obesidad de predominio central.",
                         "Evolución:", "Refiere aumento de 4 kg",
                         "Diagnóstico:", "Plan:"):
            self.assertIn(esperado, self.texto)

    def test_los_signos_vitales_llevan_los_rotulos_del_papel(self):
        for rotulo in ("TA (mmHg)", "F.C. (lpm)", "Temp. (°C)", "Peso (kg)",
                       "Talla (m)", "IMC (kg/m²)"):
            self.assertIn(rotulo, self.texto)
        self.assertIn("138/86", self.texto)
        self.assertIn("97,9", self.texto, "los decimales van con coma")

    def test_las_casillas_de_signos_sin_valor_no_salen(self):
        """Once casillas de las cuales cinco vacías no se leen; seis, sí."""
        for ausente in ("F.R. (rpm)", "Dxtx (mg/dL)", "TFG (mL/min)"):
            self.assertNotIn(ausente, self.texto)

    def test_el_pie_dice_cuando_se_imprimio(self):
        self.assertIn("Historia impresa el 18/08/2026", self.texto)

    def test_nada_se_pasa_de_la_guia_derecha(self):
        for _, x, _, texto, estilo, pt in self.doc.trazos:
            fin = x + self.doc._ancho(texto, estilo, pt)
            self.assertLessEqual(round(fin, 2), pdf_comun.GUIA_DER_MM + 0.01,
                                 f"«{texto}» se pasa de la guía derecha")


class HistoriaVacia(BaseHistoriaPDF):
    """Un paciente recién cargado: no puede salir un formulario en blanco."""

    def setUp(self) -> None:
        super().setUp()
        self.generar({"codigo": "EC-0001", "fecha": "2026-08-18",
                      "paciente": {"nombre": "Juan Pérez"}})

    def test_entra_en_una_carilla(self):
        self.assertEqual(1, self.doc.page)

    def test_dice_que_todavia_no_hay_consultas(self):
        self.assertIn("CONSULTAS", self.texto)
        self.assertIn("Todavía no hay consultas registradas", self.texto)

    def test_no_imprime_secciones_de_antecedentes_vacias(self):
        for seccion in ("ANTECEDENTES FAMILIARES",
                        "ANTECEDENTES PERSONALES NO PATOLÓGICOS",
                        "ANTECEDENTES PERSONALES PATOLÓGICOS", "NOTAS"):
            self.assertNotIn(seccion, self.texto)

    def test_sin_alergias_no_hay_aviso(self):
        self.assertNotIn("ALERGIAS", self.texto)

    def test_la_ficha_sale_igual_con_lo_poco_que_hay(self):
        self.assertIn("Juan Pérez", self.texto)
        self.assertIn("Nombre", self.texto)


class HistoriaLarga(BaseHistoriaPDF):
    """Un paciente de años: multipágina con el membrete repetido."""

    def setUp(self) -> None:
        super().setUp()
        consultas = [
            {"fecha": f"2026-{mes:02d}-1{dia}",
             "motivo": f"Control mensual número {mes}.",
             "evolucion": "Evolución favorable, continúa el plan indicado. "
                          "Se refuerzan las pautas de alimentación.",
             "diagnostico": "Obesidad grado II en tratamiento.",
             "ta_sistolica": 130, "ta_diastolica": 84, "peso": 95.0 - mes,
             "talla": 1.68, "imc": 33.0}
            for mes in range(12, 0, -1) for dia in (4,)
        ]
        self.generar(dict(DATOS, consultas=consultas))

    def test_se_pasa_a_varias_paginas(self):
        self.assertGreater(self.doc.page, 1)

    def test_el_membrete_y_el_codigo_estan_en_todas(self):
        for marca in ("EC-0007", pdf_comun.SALUD_TEXTO):
            paginas = {t[0] for t in self.doc.trazos if t[3] == marca}
            self.assertEqual(set(range(1, self.doc.page + 1)), paginas, marca)

    def test_el_titulo_no_se_repite(self):
        self.assertEqual(1, len(self.renglones("HISTORIA CLÍNICA")))

    def test_el_pie_esta_en_todas_las_paginas(self):
        paginas = {t[0] for t in self.doc.trazos
                   if t[3].startswith("Historia impresa el")}
        self.assertEqual(set(range(1, self.doc.page + 1)), paginas)

    def test_lleva_numero_de_pagina(self):
        self.assertIn(f"Página 1 de {self.doc.page}", self.texto)

    def test_ningun_renglon_del_cuerpo_pisa_el_pie(self):
        for _, _, y, texto, _, _ in self.doc.trazos:
            if texto.startswith(("Página ", "Historia impresa")):
                continue
            self.assertLessEqual(y, pdf_comun.CUERPO_Y1_MM, texto)


class EvolucionEnLaHistoria(BaseHistoriaPDF):
    """Los mini-gráficos de la dec. 13 ampliada, dentro del PDF impreso."""

    def setUp(self) -> None:
        super().setUp()
        self.generar(dict(DATOS, evolucion=EVOLUCION))

    def test_la_seccion_sale_con_su_titulo(self):
        self.assertIn("EVOLUCIÓN", self.texto)

    def test_hay_un_grafico_por_metrica_con_dos_o_mas_mediciones(self):
        self.assertEqual(["Peso (kg)", "IMC", "Grasa (%)"],
                         [t[3] for t in self.titulos_grafico])

    def test_la_metrica_sin_mediciones_no_tiene_grafico(self):
        """`musculo_kg` vino vacía: no hay gráfico ni título que lo anuncie."""
        self.assertNotIn("Músculo (kg)", [t[3] for t in self.titulos_grafico])

    def test_una_serie_de_un_solo_punto_se_ignora(self):
        """Con una sola medición no hay tendencia: hay un número."""
        self.assertNotIn("Grasa visceral", [t[3] for t in self.titulos_grafico])

    def test_el_titulo_lleva_la_unidad_y_el_imc_no_porque_no_tiene(self):
        titulos = [t[3] for t in self.titulos_grafico]
        self.assertIn("Peso (kg)", titulos)
        self.assertIn("Grasa (%)", titulos)
        self.assertIn("IMC", titulos)

    def test_la_evolucion_va_antes_de_las_consultas(self):
        pag_evo, y_evo = self.y_de("EVOLUCIÓN")
        pag_con, y_con = self.y_de("CONSULTAS")
        self.assertLessEqual(pag_evo, pag_con)
        if pag_evo == pag_con:
            self.assertLess(y_evo, y_con)

    def test_hay_un_punto_dibujado_por_medicion(self):
        for titulo in ("Peso (kg)", "IMC", "Grasa (%)"):
            self.assertEqual(len(FECHAS), len(self.puntos_del_grafico(titulo)),
                             titulo)

    def test_rotula_la_primera_y_la_ultima_fecha_con_el_ano_en_dos_cifras(self):
        ejes = [t[3] for t in self.doc.trazos
                if abs(t[5] - pdf_comun.GRAFICO_PT_EJE) < 0.01]
        self.assertIn("12/02/26", ejes)
        self.assertIn("18/08/26", ejes)

    def test_los_extremos_del_eje_y_van_rotulados(self):
        ejes = [t[3] for t in self.doc.trazos
                if abs(t[5] - pdf_comun.GRAFICO_PT_EJE) < 0.01]
        self.assertIn("84,6", ejes, "falta el máximo del eje Y")
        self.assertIn("78,4", ejes, "falta el mínimo del eje Y")
        self.assertIn("42,1", ejes)

    def test_el_valor_de_la_ultima_medicion_va_en_negrita(self):
        finales = [t[3] for t in self.doc.trazos
                   if t[4] == "B"
                   and abs(t[5] - pdf_comun.GRAFICO_PT_VALOR) < 0.01]
        self.assertEqual(["78,4", "31,4", "38,3"], finales)

    def test_dos_graficos_por_fila(self):
        ancho = ((pdf_comun.ANCHO_UTIL_MM - pdf_historia.SEPARACION_GRAFICOS_MM)
                 / 2)
        izquierda = pdf_comun.MARGEN_IZQ_MM
        derecha = izquierda + ancho + pdf_historia.SEPARACION_GRAFICOS_MM
        self.assertEqual([izquierda, derecha, izquierda],
                         [round(t[1], 2) for t in self.titulos_grafico])

    def test_la_linea_de_datos_es_el_teal_de_la_marca(self):
        colores = {c for _, _, _, _, _, c in self.doc.lineas}
        self.assertIn(pdf_comun.TEAL_MEDIO, colores,
                      "la línea de evolución no salió en #157F6F")

    def test_la_grilla_es_el_gris_suave(self):
        colores = {c for _, _, _, _, _, c in self.doc.lineas}
        self.assertIn(pdf_comun.GRIS_CORTE, colores,
                      "falta la grilla horizontal #C9C9C9")

    def test_los_puntos_se_separan_en_proporcion_al_tiempo(self):
        """36 días no pueden medir lo mismo que 79 sobre el papel.

        Equiespaciar los puntos hace que una curva de peso mienta sobre la
        velocidad del cambio, que es justo lo que el médico está leyendo.
        """
        equis = [c[1] for c in self.puntos_del_grafico("Peso (kg)")]
        saltos = [b - a for a, b in zip(equis, equis[1:])]
        self.assertLess(saltos[0], saltos[1], "36 días > 79 días en el papel")
        self.assertGreater(saltos[1], saltos[2])

    def test_nada_dibujado_se_sale_de_los_margenes(self):
        for pagina, x1, y1, x2, y2, _ in self.doc.lineas:
            for x in (x1, x2):
                self.assertGreaterEqual(round(x, 2), pdf_comun.MARGEN_IZQ_MM,
                                        f"línea fuera del margen (p. {pagina})")
                self.assertLessEqual(round(x, 2), pdf_comun.GUIA_DER_MM + 0.01,
                                     f"línea fuera de la guía (p. {pagina})")
            for y in (y1, y2):
                self.assertLessEqual(round(y, 2), pdf_comun.CUERPO_Y1_MM)
        for pagina, x, y, radio in self.doc.circulos:
            self.assertGreaterEqual(round(x - radio, 2),
                                    pdf_comun.MARGEN_IZQ_MM)
            self.assertLessEqual(round(x + radio, 2),
                                 pdf_comun.GUIA_DER_MM + 0.01)
            self.assertLessEqual(round(y + radio, 2), pdf_comun.CUERPO_Y1_MM)

    def test_ningun_rotulo_del_grafico_se_pasa_de_la_guia_derecha(self):
        for _, x, _, texto, estilo, pt in self.doc.trazos:
            fin = x + self.doc._ancho(texto, estilo, pt)
            self.assertLessEqual(round(fin, 2), pdf_comun.GUIA_DER_MM + 0.01,
                                 f"«{texto}» se pasa de la guía derecha")


class SinEvolucionNoHaySeccion(BaseHistoriaPDF):
    """Sin datos suficientes no puede quedar un título huérfano."""

    def test_sin_la_clave_evolucion_la_historia_sale_igual_que_antes(self):
        self.generar()
        self.assertNotIn("EVOLUCIÓN", self.texto)
        self.assertEqual([], self.doc.circulos)

    def test_con_series_vacias_no_se_imprime_nada(self):
        self.generar(dict(DATOS, evolucion={"series": {
            "peso": [], "imc": None, "grasa_pct": []}}))
        self.assertNotIn("EVOLUCIÓN", self.texto)
        self.assertEqual([], self.doc.circulos)

    def test_con_una_sola_medicion_de_cada_cosa_tampoco(self):
        self.generar(dict(DATOS, evolucion={"series": {
            "peso": _serie(FECHAS[:1], (84.6,)),
            "imc": _serie(FECHAS[:1], (33.9,))}}))
        self.assertNotIn("EVOLUCIÓN", self.texto)
        self.assertEqual([], self.doc.circulos)

    def test_las_mediciones_a_medio_cargar_no_cuentan_como_punto(self):
        """Un `valor` nulo es un dato que no está, no un cero."""
        self.generar(dict(DATOS, evolucion={"series": {"peso": [
            {"fecha": "2026-02-12", "valor": 84.6},
            {"fecha": "2026-03-20", "valor": None},
            {"fecha": "2026-06-07", "valor": ""},
        ]}}))
        self.assertNotIn("EVOLUCIÓN", self.texto)

    def test_acepta_el_diccionario_de_series_pelado(self):
        """Sin envolver en «series», que es como queda si el que llama desenvuelve."""
        self.generar(dict(DATOS, evolucion={
            "peso": _serie(FECHAS, (84.6, 83.1, 80.1, 79.3, 78.4))}))
        self.assertIn("EVOLUCIÓN", self.texto)
        self.assertEqual(len(FECHAS), len(self.puntos_del_grafico("Peso (kg)")))


class EvolucionEnLosExtremos(BaseHistoriaPDF):
    """Series planas, series larguísimas y fechas que no se pueden leer."""

    def test_una_serie_plana_no_rompe_ni_deja_el_grafico_vacio(self):
        self.generar(dict(DATOS, evolucion={"series": {
            "peso": _serie(FECHAS, (78.4,) * 5)}}))
        puntos = self.puntos_del_grafico("Peso (kg)")
        self.assertEqual(5, len(puntos))
        alturas = {round(p[2], 3) for p in puntos}
        self.assertEqual(1, len(alturas), "la serie plana tiene que ser plana")
        # Con mínimo y máximo iguales el eje Y se rotula una sola vez.
        ejes = [t[3] for t in self.doc.trazos
                if abs(t[5] - pdf_comun.GRAFICO_PT_EJE) < 0.01]
        self.assertEqual(1, ejes.count("78,4"))

    def test_cuarenta_mediciones_entran_en_el_mismo_cuadro(self):
        fechas = [f"2026-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d}"
                  for i in range(40)]
        self.generar(dict(DATOS, evolucion={"series": {
            "peso": _serie(fechas, [100.0 - i * 0.4 for i in range(40)])}}))
        puntos = self.puntos_del_grafico("Peso (kg)")
        self.assertEqual(40, len(puntos))
        self.assertLess(puntos[0][3], pdf_comun.GRAFICO_PUNTO_R_MM,
                        "con cuarenta puntos hay que achicarlos o se tocan")
        for _, x, y, radio in puntos:
            self.assertGreaterEqual(round(x - radio, 2),
                                    pdf_comun.MARGEN_IZQ_MM)
            self.assertLessEqual(round(x + radio, 2),
                                 pdf_comun.GUIA_DER_MM + 0.01)

    def test_una_serie_desordenada_se_ordena_por_fecha(self):
        self.generar(dict(DATOS, evolucion={"series": {
            "peso": _serie(("2026-08-18", "2026-02-12", "2026-06-07"),
                           (78.4, 84.6, 80.1))}}))
        ejes = [t[3] for t in self.doc.trazos
                if abs(t[5] - pdf_comun.GRAFICO_PT_EJE) < 0.01]
        self.assertLess(ejes.index("12/02/26"), ejes.index("18/08/26"))

    def test_fechas_que_no_se_pueden_leer_no_rompen_el_grafico(self):
        self.generar(dict(DATOS, evolucion={"series": {"peso": [
            {"fecha": "en enero", "valor": 84.6},
            {"fecha": "hace un mes", "valor": 80.1},
            {"fecha": "hoy", "valor": 78.4},
        ]}}))
        self.assertEqual(3, len(self.puntos_del_grafico("Peso (kg)")))
        self.assertIn("en enero", self.texto)


class GraficosEnUnaHistoriaLarga(BaseHistoriaPDF):
    """Las cinco métricas, empujadas contra el corte de página."""

    def setUp(self) -> None:
        super().setUp()
        historia = dict(HISTORIA,
                        notas_generales="Nota de seguimiento. " * 120)
        self.generar(dict(DATOS, historia=historia, evolucion=EVOLUCION_COMPLETA))

    def test_se_dibujan_los_cinco_graficos(self):
        self.assertEqual(
            ["Peso (kg)", "IMC", "Grasa (%)", "Músculo (kg)", "Grasa visceral"],
            [t[3] for t in self.titulos_grafico])

    def test_ningun_grafico_se_parte_entre_dos_paginas(self):
        """Cada gráfico conserva sus cinco puntos en la hoja de su título."""
        for titulo in ("Peso (kg)", "IMC", "Grasa (%)", "Músculo (kg)",
                       "Grasa visceral"):
            self.assertEqual(len(FECHAS), len(self.puntos_del_grafico(titulo)),
                             f"«{titulo}» perdió puntos: se partió de página")

    def test_el_titulo_de_la_seccion_no_queda_solo_al_pie(self):
        pagina_titulo, _ = self.y_de("EVOLUCIÓN")
        primeros = [t for t in self.titulos_grafico if t[3] == "Peso (kg)"]
        self.assertEqual(pagina_titulo, primeros[0][0],
                         "«EVOLUCIÓN» quedó en una hoja y su primer gráfico en otra")

    def test_ningun_punto_pisa_el_pie_de_la_hoja(self):
        for _, _, y, radio in self.doc.circulos:
            self.assertLessEqual(round(y + radio, 2), pdf_comun.CUERPO_Y1_MM)

    def test_el_membrete_sigue_en_todas_las_paginas(self):
        paginas = {t[0] for t in self.doc.trazos if t[3] == "EC-0007"}
        self.assertEqual(set(range(1, self.doc.page + 1)), paginas)


class LaFechaDeLaConsultaNoQuedaSola(unittest.TestCase):
    """Una visita no empieza con la fecha en una hoja y sus datos en la otra.

    El corte se barre **milímetro a milímetro**: se arranca la sección de
    consultas con el cursor a 12, 13, 14… mm del pie, que son todas las
    alturas a las que puede quedar. Barrerlo alargando el texto de arriba no
    sirve —un renglón mueve cinco milímetros de golpe y la ventana del defecto
    medía dos—, y es justo la ventana en la que la fecha entraba y su tabla de
    signos vitales no.
    """

    def setUp(self) -> None:
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)
        self.doc = _Espia(pdf_comun.RUTA_LOGO_DEFECTO,
                          pdf_comun.DIR_FUENTES_DEFECTO, "EC-0007")

    def test_siempre_hay_algo_debajo_de_la_fecha_en_su_misma_hoja(self):
        for hueco in range(8, 45):
            self.doc.nueva_pagina()
            self.doc.pluma_y = pdf_comun.CUERPO_Y1_MM - hueco
            pdf_historia._consultas(self.doc, CONSULTAS)

        fechas = [t for t in self.doc.trazos
                  if t[4] == "B"
                  and abs(t[5] - pdf_historia.PT_CONSULTA) < 0.01
                  and t[3][2:3] == "/" == t[3][5:6]]
        self.assertTrue(fechas, "no se imprimió ninguna fecha de consulta")
        for pagina, _, y, texto, _, _ in fechas:
            debajo = [t for t in self.doc.trazos if t[0] == pagina and t[2] > y]
            self.assertTrue(
                debajo, f"«{texto}» quedó sola al pie de la página {pagina}")


class FilasDeLaBase(BaseHistoriaPDF):
    """La historia llega de SQLite: `sqlite3.Row` tiene que servir tal cual."""

    def test_acepta_sqlite3_row_sin_convertir_nada(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE p (nombre TEXT, cedula TEXT, edad INTEGER)")
        con.execute("INSERT INTO p VALUES ('Ana Pérez', 'V-123', 47)")
        fila = con.execute("SELECT * FROM p").fetchone()
        self.generar({"codigo": "EC-0003", "paciente": fila,
                      "fecha": "2026-08-18"})
        self.assertIn("Ana Pérez", self.texto)
        self.assertIn("V-123", self.texto)
        self.assertIn("47 años", self.texto)


class FaltaElLogo(unittest.TestCase):

    def test_avisa_donde_lo_buscaba(self):
        carpeta = Path(tempfile.mkdtemp(prefix="recipes_historia_mal_"))
        self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        with self.assertRaises(pdf_historia.RecursoFaltanteError) as caja:
            pdf_historia.generar_historia(
                DATOS, str(carpeta / "h.pdf"),
                ruta_logo=str(carpeta / "no-hay-logo.png"))
        self.assertIn("no-hay-logo.png", str(caja.exception))


if __name__ == "__main__":
    unittest.main()
