"""Tests de `pdf_informe.py` — los dos tipos de informe (dec. 10).

Lo que fija esta suite es lo que se puede romper sin que nadie se dé cuenta
hasta que el informe ya está entregado:

  - El **clínico** (plantilla B) dice lo que dice el ejemplo real: paciente con
    su C.I., prosa, "Diagnóstico:", "Tratamiento indicado:", ciudad con fecha
    larga y la firma. Nada de vocabulario de seguros.
  - El **de la aseguradora** (plantilla A) lleva sus rótulos LITERALES, con los
    paréntesis y todo, porque pueden ser exigencia de quien lo recibe.
  - Los tres defectos medidos del `.docx` original quedan arreglados: la firma
    no se cae sola a una segunda hoja, los recuadros crecen con el texto y el
    título está centrado de verdad (medido, no empujado con espacios).
  - Un anexo que falta **frena la emisión**: un informe sin el anexo que el
    médico creía estar mandando es peor que uno que no salió.

No se lee el PDF con un visor: se espía `_texto()`, que es por donde pasa toda
la tinta de texto del módulo, anotando además en qué página cayó cada renglón.
Solo `unittest` de la stdlib (§3).

Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
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
import pdf_informe  # noqa: E402

MEDICION = RAIZ / "referencias" / "medicion-whatsapp-ejemplo.jpeg"

MEDICO = {
    "medico_nombre": "Dr. Eleazar Shiera Bastidas",
    "medico_especialidad": "Medicina Interna",
    "medico_comezu": "7414",
    "medico_mpps": "34846",
    "ciudad": "Maracaibo",
}

CLINICO = dict(MEDICO, **{
    "tipo": "clinico",
    "codigo": "EC-0001",
    "fecha": "2026-08-18",
    "paciente_nombre": "María Pérez",
    "paciente_cedula": "11222333",
    "cuerpo": ("Se trata de paciente femenino de 60 años de edad, quien "
               "consulta por presentar aumento de peso progresivo con "
               "antecedentes de dislipidemia y trastornos del sueño."),
    "diagnostico": "Dislipidemia",
    "tratamiento": "Se indican exámenes pertinentes diagnósticos",
})

ASEGURADORA = dict(MEDICO, **{
    "tipo": "aseguradora",
    "codigo": "EC-0007",
    "fecha": "2026-08-18",
    "paciente_nombre": "María Fernanda Rodríguez Blanco",
    "numero_poliza": "AXA-4471902-03",
    "prestacion_sanitaria": "Consulta especializada",
    "antecedentes": "Dislipidemia desde marzo de 2021.",
    "motivo_consulta": "Aumento de peso progresivo desde febrero de 2025.",
    "diagnostico": "Obesidad grado II. Dislipidemia mixta.",
    "evolucion": "Se indican exámenes de laboratorio y plan nutricional.",
})


class _Espia(pdf_informe._Informe):
    """El compositor real, anotando cada renglón y su página."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trazos: list[tuple[int, float, float, str, str, float]] = []
        self.imagenes: list[tuple[int, str, float, float]] = []

    def _texto(self, x, base_y, texto, estilo, pt, color):
        self.trazos.append((self.page, x, base_y, texto, estilo, pt))
        return super()._texto(x, base_y, texto, estilo, pt, color)

    def image(self, ruta, *args, **kwargs):  # type: ignore[override]
        self.imagenes.append((self.page, str(ruta), kwargs.get("w", 0.0),
                              kwargs.get("h", 0.0)))
        return super().image(ruta, *args, **kwargs)


class BaseInforme(unittest.TestCase):
    """Genera un informe de verdad en una carpeta temporal y guarda los trazos."""

    def setUp(self) -> None:
        # fpdf subsetea las Lato con fontTools y deja archivos al recolector:
        # son ResourceWarning de una dependencia, no de la app.
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)

        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_informe_"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)

        # `generar_informe` resuelve `_Informe` al llamarlo, así que alcanza con
        # cambiar el atributo del módulo para quedarse con el compositor y
        # poder mirar lo que dibujó.
        real = pdf_informe._Informe
        self.addCleanup(setattr, pdf_informe, "_Informe", real)
        self.doc: _Espia | None = None

        def recordar(*args, **kwargs):
            self.doc = _Espia(*args, **kwargs)
            return self.doc

        pdf_informe._Informe = recordar          # type: ignore[misc]

    def generar(self, datos) -> Path:
        destino = self.carpeta / "informe.pdf"
        pdf_informe.generar_informe(datos, str(destino))
        return destino

    # -- consultas sobre lo dibujado --------------------------------------
    @property
    def texto(self) -> str:
        return " ".join(t[3] for t in self.doc.trazos)

    def renglones(self, contiene: str):
        return [t for t in self.doc.trazos if contiene in t[3]]

    def pagina_de(self, contiene: str) -> int:
        encontrados = self.renglones(contiene)
        self.assertTrue(encontrados, f"no se imprimió «{contiene}»")
        return encontrados[0][0]


class InformeClinico(BaseInforme):
    """La carta que el médico usa todos los días (plantilla B)."""

    def setUp(self) -> None:
        super().setUp()
        self.generar(CLINICO)

    def test_entra_en_una_sola_pagina(self):
        self.assertEqual(1, self.doc.page)

    def test_titulo_acentuado_y_centrado_de_verdad(self):
        """En el `.docx` estaba empujado con setenta espacios y sin tilde."""
        titulo = self.renglones("INFORME MÉDICO")
        self.assertEqual(1, len(titulo))
        _, x, _, texto, estilo, pt = titulo[0]
        self.assertEqual("B", estilo)
        ancho = self.doc._ancho(texto, estilo, pt)
        centro = x + ancho / 2.0
        self.assertAlmostEqual(
            (pdf_comun.MARGEN_IZQ_MM + pdf_comun.GUIA_DER_MM) / 2.0, centro,
            places=2)

    def test_cabecera_con_medico_especialidad_comezu_y_mpps(self):
        for esperado in ("Dr. Eleazar Shiera Bastidas", "Medicina Interna",
                         "COMEZU", "7414", "MPPS", "34846"):
            self.assertIn(esperado, self.texto)

    def test_paciente_con_su_cedula(self):
        self.assertIn("María Pérez, C.I. 11222333", self.texto)

    def test_cuerpo_diagnostico_y_tratamiento(self):
        self.assertIn("Se trata de paciente femenino de 60 años", self.texto)
        self.assertIn("Diagnóstico:", self.texto)
        self.assertIn("Dislipidemia", self.texto)
        self.assertIn("Tratamiento indicado:", self.texto)
        self.assertIn("Se indican exámenes pertinentes", self.texto)

    def test_ciudad_y_fecha_larga_al_pie(self):
        self.assertIn("Maracaibo; 18 de Agosto de 2026", self.texto)

    def test_la_firma_va_al_pie_de_la_misma_pagina(self):
        firmas = [i for i in self.doc.imagenes if "firma" in i[1].lower()]
        self.assertEqual(1, len(firmas))
        pagina, _, ancho, _ = firmas[0]
        self.assertEqual(1, pagina, "la firma no puede caerse a otra hoja")
        self.assertAlmostEqual(pdf_informe.FIRMA_ANCHO_MM, ancho, places=1)

    def test_no_repite_la_colegiatura_debajo_de_la_firma(self):
        """Ya está adentro del PNG de la firma y arriba en la cabecera."""
        firma = [i for i in self.doc.imagenes if "firma" in i[1].lower()][0]
        y_firma = self.doc.pluma_y - pdf_informe.FIRMA_ALTO_MM
        debajo = [t for t in self.doc.trazos if t[2] >= y_firma]
        self.assertEqual([], debajo,
                         "debajo de la firma no va nada: los datos de "
                         "colegiatura ya están adentro de la imagen")
        self.assertEqual(1, firma[0])

    def test_no_usa_vocabulario_de_seguros(self):
        for prohibido in ("Nº de póliza", "Prestación sanitaria", "Evolución",
                          "Firma del facultativo"):
            self.assertNotIn(prohibido, self.texto)


class InformeSinDiagnostico(BaseInforme):
    """Un informe puede no traer diagnóstico: no se imprime el rótulo vacío."""

    def test_sin_diagnostico_no_hay_rotulo(self):
        datos = dict(CLINICO, diagnostico="", tratamiento="")
        self.generar(datos)
        self.assertNotIn("Diagnóstico:", self.texto)
        self.assertNotIn("Tratamiento indicado:", self.texto)
        self.assertIn("Se trata de paciente femenino", self.texto)
        self.assertIn("Maracaibo; 18 de Agosto de 2026", self.texto)

    def test_sin_especialidad_no_hay_celda_vacia(self):
        self.generar(dict(CLINICO, medico_especialidad=""))
        self.assertNotIn("Especialidad", self.texto)


class ProsaLarguisima(BaseInforme):
    """Un informe largo es legítimo: fluye, con el membrete repetido."""

    def setUp(self) -> None:
        super().setUp()
        parrafo = ("El paciente refiere aumento de peso progresivo con "
                   "astenia, somnolencia diurna y trastornos del sueño de "
                   "larga data, sin cambios en la dieta ni en la actividad "
                   "física habitual. ")
        self.generar(dict(CLINICO, cuerpo=parrafo * 60))

    def test_se_pasa_a_varias_paginas_sin_avisar_error(self):
        self.assertGreater(self.doc.page, 1)

    def test_el_membrete_se_repite_en_todas(self):
        paginas = {t[0] for t in self.doc.trazos if t[3] == "EC-0001"}
        self.assertEqual(set(range(1, self.doc.page + 1)), paginas)

    def test_el_titulo_no_se_repite(self):
        self.assertEqual(1, len(self.renglones("INFORME MÉDICO")))

    def test_la_firma_nunca_queda_sola_en_una_hoja(self):
        """El defecto del `.docx` era una hoja con NADA más que la rúbrica.

        Con el texto fluyendo, el cierre («Maracaibo; 18 de Agosto de 2026»)
        viaja pegado a la firma y aterriza con ella: la última hoja siempre
        tiene contenido del informe, no solo la imagen.
        """
        firma = [i for i in self.doc.imagenes if "firma" in i[1].lower()][0]
        cromo = {pdf_comun.SALUD_TEXTO, pdf_comun.CODIGO_ROTULO, "EC-0001"}
        cuerpo = [t for t in self.doc.trazos
                  if t[0] == firma[0] and t[3] not in cromo
                  and not t[3].startswith("Página ")]
        self.assertTrue(cuerpo, "la firma tiene que compartir hoja con el texto")
        self.assertIn("Maracaibo; 18 de Agosto de 2026",
                      " ".join(t[3] for t in cuerpo))

    def test_lleva_numero_de_pagina(self):
        self.assertIn(f"Página 1 de {self.doc.page}", self.texto)

    def test_nada_se_pasa_de_la_guia_derecha(self):
        for _, x, _, texto, estilo, pt in self.doc.trazos:
            fin = x + self.doc._ancho(texto, estilo, pt)
            self.assertLessEqual(round(fin, 2), pdf_comun.GUIA_DER_MM + 0.01,
                                 f"«{texto}» se pasa de la guía derecha")


class InformeAseguradora(BaseInforme):
    """El formulario de la plantilla A, con sus rótulos literales."""

    def setUp(self) -> None:
        super().setUp()
        self.generar(ASEGURADORA)

    def test_los_rotulos_literales_estan_completos(self):
        for literal in (
                "Nombre del Médico", "COMEZU", "MPPS", "Especialidad",
                "Fecha del Informe", "Datos de la prestación",
                "Nombre del Paciente", "Nº de póliza", "Prestación sanitaria",
                "Antecedentes patológicos del paciente",
                "(indicar fecha de inicio de la patología)",
                "Motivo de la consulta y/o ingreso",
                "Diagnóstico", "Evolución", "Firma del facultativo"):
            self.assertIn(literal, self.texto, f"falta el rótulo «{literal}»")

    def test_el_rotulo_del_motivo_va_entero_con_su_parentesis(self):
        """Es el más largo y el que se parte en dos renglones: se junta igual."""
        self.assertIn(
            "(indicar la fecha de inicio de la enfermedad de los síntomas y "
            "del diagnóstico.)", self.texto.replace("  ", " "))

    def test_trae_los_datos_cargados(self):
        for esperado in ("AXA-4471902-03", "Consulta especializada",
                         "Dislipidemia desde marzo de 2021.",
                         "Obesidad grado II. Dislipidemia mixta."):
            self.assertIn(esperado, self.texto)

    def test_la_firma_no_se_cae_a_una_segunda_hoja(self):
        """El defecto del `.docx`: la plantilla A imprimía 2 hojas siempre."""
        self.assertEqual(1, self.doc.page)
        firma = [i for i in self.doc.imagenes if "firma" in i[1].lower()][0]
        self.assertEqual(1, firma[0])

    def test_no_usa_el_vocabulario_del_informe_clinico(self):
        self.assertNotIn("Tratamiento indicado:", self.texto)


class CajonesQueCrecen(BaseInforme):
    """En el `.docx` las cajas eran de alto fijo y el texto se desbordaba."""

    def test_un_texto_largo_no_se_pierde_ni_se_sale(self):
        largo = ("Antecedente detallado con fechas y evolución completa. " * 30)
        self.generar(dict(ASEGURADORA, antecedentes=largo))
        pedazos = [t for t in self.doc.trazos
                   if t[3].startswith("Antecedente detallado")]
        self.assertGreater(len(pedazos), 5, "el cajón tiene que crecer")
        for _, _, y, texto, _, _ in self.doc.trazos:
            if texto.startswith("Página "):
                continue                      # el pie vive debajo del cuerpo
            self.assertLessEqual(y, pdf_comun.CUERPO_Y1_MM, texto)


class Anexos(BaseInforme):
    """La página de anexo es opt-in y a página completa (dec. 12, Parte C §5)."""

    def test_una_pagina_por_imagen_con_su_pie(self):
        self.generar(dict(ASEGURADORA, anexos=[{
            "ruta": str(MEDICION),
            "tipo": "Medición de composición corporal",
            "fecha": "2026-08-14",
        }]))
        self.assertEqual(2, self.doc.page)
        self.assertIn("Anexo 1 — Medición de composición corporal, 14/08/2026",
                      self.texto)
        self.assertEqual(2, self.pagina_de("ANEXOS"))

    def test_la_imagen_ocupa_casi_toda_la_hoja(self):
        """Lo medido: en media carta las tablas del informe no se leen."""
        self.generar(dict(CLINICO, anexos=[str(MEDICION)]))
        medicion = [i for i in self.doc.imagenes
                    if "medicion" in i[1].lower()][0]
        _, _, ancho, alto = medicion
        self.assertGreater(alto, 200.0, "la imagen tiene que ir a página entera")
        self.assertLessEqual(ancho, pdf_comun.ANCHO_UTIL_MM + 0.01)
        self.assertAlmostEqual(909 / 1280, ancho / alto, places=3)

    def test_sin_anexos_no_hay_pagina_de_anexos(self):
        self.generar(CLINICO)
        self.assertNotIn("ANEXOS", self.texto)

    def test_el_codigo_del_paciente_esta_en_la_hoja_del_anexo(self):
        """Una hoja de anexo suelta tiene que decir de quién es."""
        self.generar(dict(CLINICO, anexos=[str(MEDICION)]))
        paginas = {t[0] for t in self.doc.trazos if t[3] == "EC-0001"}
        self.assertIn(2, paginas)


class AnexosHostiles(unittest.TestCase):
    """Lo que tiene que frenar ANTES de escribir el PDF."""

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_informe_mal_"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        self.destino = str(self.carpeta / "informe.pdf")

    def test_anexo_inexistente_avisa_donde_lo_buscaba(self):
        ruta = str(self.carpeta / "no-esta.jpg")
        with self.assertRaises(pdf_informe.AnexoNoEncontradoError) as caja:
            pdf_informe.generar_informe(dict(CLINICO, anexos=[ruta]),
                                        self.destino)
        mensaje = str(caja.exception)
        self.assertIn("no-esta.jpg", mensaje)
        self.assertIn("volvé a adjuntarla", mensaje)
        self.assertFalse(Path(self.destino).exists(),
                         "no se escribe un informe al que le falta un anexo")

    def test_un_pdf_no_se_pega_adentro_del_informe(self):
        falso = self.carpeta / "laboratorio.pdf"
        falso.write_bytes(b"%PDF-1.4\n")
        with self.assertRaises(pdf_informe.AnexoNoEsImagenError) as caja:
            pdf_informe.generar_informe(dict(CLINICO, anexos=[str(falso)]),
                                        self.destino)
        self.assertIn("imprimilo aparte", str(caja.exception))

    def test_tipo_desconocido(self):
        with self.assertRaises(pdf_informe.TipoDesconocidoError) as caja:
            pdf_informe.generar_informe(dict(CLINICO, tipo="constancia"),
                                        self.destino)
        self.assertIn("constancia", str(caja.exception))

    def test_falta_el_logo(self):
        with self.assertRaises(pdf_informe.RecursoFaltanteError):
            pdf_informe.generar_informe(
                CLINICO, self.destino,
                ruta_logo=str(self.carpeta / "no-hay-logo.png"))

    def test_sin_fecha_sale_la_de_hoy(self):
        """Un informe sin fecha no es un informe: se pone la del día."""
        from datetime import date
        pdf_informe.generar_informe(dict(CLINICO, fecha=""), self.destino)
        self.assertTrue(Path(self.destino).is_file())
        # la fecha larga de hoy tiene que poder armarse sin explotar
        self.assertIn(str(date.today().year),
                      pdf_comun.fecha_larga(date.today().isoformat()))


class FraseInicial(unittest.TestCase):
    """La fórmula del ejemplo real, para que la pantalla la ofrezca (dec. 10)."""

    def test_femenino_con_motivo_y_antecedentes(self):
        self.assertEqual(
            "Se trata de paciente femenino de 60 años de edad, quien consulta "
            "por presentar aumento de peso progresivo con antecedentes de "
            "dislipidemia y trastornos del sueño.",
            pdf_informe.frase_inicial("F", 60, "aumento de peso progresivo",
                                      "dislipidemia y trastornos del sueño"))

    def test_masculino_sin_antecedentes(self):
        self.assertEqual(
            "Se trata de paciente masculino de 34 años de edad, quien consulta "
            "por presentar dolor lumbar.",
            pdf_informe.frase_inicial("M", 34, "dolor lumbar"))

    def test_sin_sexo_ni_edad_no_inventa_nada(self):
        self.assertEqual("Se trata de paciente, quien consulta por presentar "
                         "cefalea.",
                         pdf_informe.frase_inicial("", None, "cefalea"))


if __name__ == "__main__":
    unittest.main()
