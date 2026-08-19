"""Tests del modelo de datos de la historia clínica (dec. 3 a 13).

Cubre las seis tablas nuevas de `basedatos.py` —historias, consultas,
signos_vitales, anexos, mediciones e informes— con el criterio del resto de la
suite: lo que el médico va a hacer de verdad, y lo que la base tiene que
impedirle. Sin dependencias fuera de la stdlib (§3).

Se corre con:  py -3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import basedatos  # noqa: E402
import codigos  # noqa: E402


ITEMS = [{"medicamento": "Losartán", "presentacion": "50 mg",
          "cantidad": "30 tabletas", "dosis": "1 diaria"}]


class BaseHistoria(unittest.TestCase):

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_historia_"))
        self.con = basedatos.inicializar(self.carpeta / "recipes.db")
        self.paciente_id = basedatos.crear_paciente(
            self.con, "María González", cedula="V-7856151", edad=47, sexo="F"
        )

    def tearDown(self) -> None:
        self.con.close()
        shutil.rmtree(self.carpeta, ignore_errors=True)


# --------------------------------------------------------------------------
# Ficha y antecedentes: se llenan una vez por paciente (dec. 3)
# --------------------------------------------------------------------------

class TestHistoria(BaseHistoria):

    def test_arranca_sin_historia_y_se_crea_al_guardar(self):
        self.assertIsNone(basedatos.obtener_historia(self.con, self.paciente_id))
        basedatos.guardar_historia(self.con, self.paciente_id, ocupacion="Docente")
        fila = basedatos.obtener_historia(self.con, self.paciente_id)
        self.assertEqual(fila["ocupacion"], "Docente")
        self.assertEqual(fila["paciente_id"], self.paciente_id)

    def test_es_una_sola_por_paciente(self):
        primera = basedatos.guardar_historia(self.con, self.paciente_id, ocupacion="Docente")
        segunda = basedatos.guardar_historia(self.con, self.paciente_id, estado_civil="Casada")
        self.assertEqual(primera, segunda)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM historias").fetchone()[0], 1
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                """
                INSERT INTO historias (paciente_id, creado_en, actualizado_en)
                VALUES (?, 'x', 'x')
                """,
                (self.paciente_id,),
            )

    def test_guardar_de_a_secciones_no_pisa_lo_demas(self):
        """La pantalla edita una sección por vez; lo que no llega no se toca."""
        basedatos.guardar_historia(
            self.con, self.paciente_id, fam_madre="HTA", fam_padre="DM2"
        )
        basedatos.guardar_historia(self.con, self.paciente_id, alergias="Penicilina")
        fila = basedatos.obtener_historia(self.con, self.paciente_id)
        self.assertEqual(fila["fam_madre"], "HTA")
        self.assertEqual(fila["fam_padre"], "DM2")
        self.assertEqual(fila["alergias"], "Penicilina")

    def test_los_campos_de_la_ficha_son_los_tres_que_quedaron(self):
        """Dec. 4 y 6: estado civil, ocupación y tipo de sangre. Nada más."""
        columnas = {f["name"] for f in self.con.execute("PRAGMA table_info(historias)")}
        self.assertLessEqual({"estado_civil", "ocupacion", "tipo_sangre"}, columnas)
        for tachado in ("afiliacion", "cama", "residente", "clinica_adscripcion",
                        "elaboro", "tipo_interrogatorio", "religion", "escolaridad",
                        "origen"):
            self.assertNotIn(tachado, columnas)

    def test_los_siete_numeradores_de_alimentacion(self):
        """Los denominadores son fijos y los pone la pantalla (Parte A §2.4)."""
        self.assertEqual(len(basedatos.DENOMINADORES_ALIMENTACION), 7)
        self.assertEqual(basedatos.DENOMINADORES_ALIMENTACION["alim_comidas_dia"], 3)
        self.assertEqual(basedatos.DENOMINADORES_ALIMENTACION["alim_litros_agua"], 2)

        basedatos.guardar_historia(
            self.con, self.paciente_id,
            **{campo: 2 for campo in basedatos.DENOMINADORES_ALIMENTACION}
        )
        fila = basedatos.obtener_historia(self.con, self.paciente_id)
        for campo in basedatos.DENOMINADORES_ALIMENTACION:
            self.assertEqual(fila[campo], 2, campo)

    def test_un_numerador_vacio_queda_en_null_y_no_en_cero(self):
        basedatos.guardar_historia(self.con, self.paciente_id, alim_pollo="")
        self.assertIsNone(basedatos.obtener_historia(self.con, self.paciente_id)["alim_pollo"])

    def test_la_vivienda_es_una_nota_libre(self):
        """Dec. 5: no son doce casillas, es texto (y respeta los renglones)."""
        basedatos.guardar_historia(
            self.con, self.paciente_id,
            habitacion="Casa propia, 3 habitaciones.\nServicios completos.",
        )
        self.assertEqual(
            basedatos.obtener_historia(self.con, self.paciente_id)["habitacion"],
            "Casa propia, 3 habitaciones.\nServicios completos.",
        )

    def test_las_alergias_se_leen_de_una(self):
        """Van fijas en el encabezado: es lo único que puede hacer daño."""
        self.assertEqual(basedatos.tiene_alergias(self.con, self.paciente_id), "")
        basedatos.guardar_historia(self.con, self.paciente_id, alergias="Penicilina")
        self.assertEqual(basedatos.tiene_alergias(self.con, self.paciente_id), "Penicilina")

    def test_un_campo_inventado_falla_en_vez_de_perderse(self):
        with self.assertRaises(ValueError):
            basedatos.guardar_historia(self.con, self.paciente_id, religion="—")

    def test_al_borrar_el_paciente_se_va_su_historia(self):
        basedatos.guardar_historia(self.con, self.paciente_id, alergias="Penicilina")
        self.con.execute("DELETE FROM pacientes WHERE id = ?", (self.paciente_id,))
        self.assertIsNone(basedatos.obtener_historia(self.con, self.paciente_id))


# --------------------------------------------------------------------------
# Consultas y signos vitales: lo que se repite en cada visita (dec. 3)
# --------------------------------------------------------------------------

class TestConsultas(BaseHistoria):

    def test_crear_y_releer_una_consulta(self):
        consulta_id = basedatos.crear_consulta(
            self.con, self.paciente_id, fecha="2026-08-14",
            motivo="Control de peso", evolucion="Refiere mejoría.",
        )
        fila = basedatos.obtener_consulta(self.con, consulta_id)
        self.assertEqual(fila["fecha"], "2026-08-14")
        self.assertEqual(fila["motivo"], "Control de peso")
        self.assertEqual(fila["evolucion"], "Refiere mejoría.")
        self.assertEqual(fila["examen_fisico"], "")

    def test_sin_fecha_es_hoy(self):
        from datetime import date
        consulta_id = basedatos.crear_consulta(self.con, self.paciente_id)
        self.assertTrue(
            basedatos.obtener_consulta(self.con, consulta_id)["fecha"].startswith(
                date.today().isoformat()
            )
        )

    def test_fecha_invalida_falla_temprano(self):
        for mala in ("14/08/2026", "2026-13-40", "ayer"):
            with self.subTest(fecha=mala):
                with self.assertRaises(ValueError):
                    basedatos.crear_consulta(self.con, self.paciente_id, fecha=mala)

    def test_la_linea_de_tiempo_va_de_la_mas_nueva_a_la_mas_vieja(self):
        for fecha in ("2026-01-05", "2026-08-14", "2026-05-01"):
            basedatos.crear_consulta(self.con, self.paciente_id, fecha=fecha)
        self.assertEqual(
            [f["fecha"] for f in basedatos.listar_consultas(self.con, self.paciente_id)],
            ["2026-08-14", "2026-05-01", "2026-01-05"],
        )
        self.assertEqual(
            basedatos.ultima_consulta(self.con, self.paciente_id)["fecha"], "2026-08-14"
        )

    def test_la_linea_de_tiempo_trae_los_signos_y_los_conteos(self):
        """Cada renglón colapsado muestra TA, peso, IMC y qué colgó de la visita."""
        consulta_id = basedatos.crear_consulta(
            self.con, self.paciente_id, fecha="2026-08-14", motivo="Control"
        )
        basedatos.guardar_signos_vitales(
            self.con, consulta_id, ta_sistolica=120, ta_diastolica=80,
            peso=78.4, talla=1.70,
        )
        basedatos.crear_anexo(
            self.con, self.paciente_id, "pacientes/EC-0001/anexos/a.jpg", "aa11",
            "2026-08-14", consulta_id=consulta_id,
        )
        codigos.crear_recipe(
            self.con, self.paciente_id, ITEMS, fecha_emision="2026-08-14",
            consulta_id=consulta_id,
        )
        basedatos.crear_informe(
            self.con, self.paciente_id, fecha="2026-08-14", consulta_id=consulta_id
        )

        fila = basedatos.listar_consultas(self.con, self.paciente_id)[0]
        self.assertEqual((fila["ta_sistolica"], fila["ta_diastolica"]), (120, 80))
        self.assertEqual(fila["peso"], 78.4)
        self.assertEqual(fila["imc"], 27.1)
        self.assertEqual(fila["cantidad_anexos"], 1)
        self.assertEqual(fila["cantidad_recipes"], 1)
        self.assertEqual(fila["cantidad_informes"], 1)

    def test_corregir_una_consulta(self):
        consulta_id = basedatos.crear_consulta(
            self.con, self.paciente_id, fecha="2026-08-14", motivo="Control"
        )
        basedatos.actualizar_consulta(
            self.con, consulta_id, motivo="Control de peso", plan="Dieta y caminata"
        )
        fila = basedatos.obtener_consulta(self.con, consulta_id)
        self.assertEqual(fila["motivo"], "Control de peso")
        self.assertEqual(fila["plan"], "Dieta y caminata")
        self.assertGreaterEqual(fila["actualizado_en"], fila["creado_en"])

    def test_las_consultas_son_de_cada_paciente(self):
        otra = basedatos.crear_paciente(self.con, "Juan Pérez")
        basedatos.crear_consulta(self.con, self.paciente_id, fecha="2026-08-14")
        basedatos.crear_consulta(self.con, otra, fecha="2026-08-14")
        self.assertEqual(len(basedatos.listar_consultas(self.con, self.paciente_id)), 1)
        self.assertEqual(len(basedatos.listar_consultas(self.con, otra)), 1)


class TestSignosVitales(BaseHistoria):

    def setUp(self) -> None:
        super().setUp()
        self.consulta_id = basedatos.crear_consulta(
            self.con, self.paciente_id, fecha="2026-08-14", motivo="Control"
        )

    def test_son_uno_por_consulta(self):
        primero = basedatos.guardar_signos_vitales(self.con, self.consulta_id, fc=72)
        segundo = basedatos.guardar_signos_vitales(self.con, self.consulta_id, fr=16)
        self.assertEqual(primero, segundo)
        fila = basedatos.obtener_signos_vitales(self.con, self.consulta_id)
        self.assertEqual((fila["fc"], fila["fr"]), (72, 16))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                """
                INSERT INTO signos_vitales (consulta_id, creado_en, actualizado_en)
                VALUES (?, 'x', 'x')
                """,
                (self.consulta_id,),
            )

    def test_estan_todos_los_campos_de_la_tabla_del_papel(self):
        basedatos.guardar_signos_vitales(
            self.con, self.consulta_id,
            ta_sistolica=120, ta_diastolica=80, fc=72, fr=16, temperatura=36.8,
            dxtx=95, tfg=90.0, spo2=98, peso=78.4, talla=1.70,
        )
        fila = basedatos.obtener_signos_vitales(self.con, self.consulta_id)
        self.assertEqual(fila["temperatura"], 36.8)
        self.assertEqual(fila["dxtx"], 95)
        self.assertEqual(fila["tfg"], 90.0)
        self.assertEqual(fila["spo2"], 98)

    def test_imc_y_tam_se_calculan_y_se_guardan(self):
        basedatos.guardar_signos_vitales(
            self.con, self.consulta_id, ta_sistolica=120, ta_diastolica=80,
            peso=78.4, talla=1.70,
        )
        fila = basedatos.obtener_signos_vitales(self.con, self.consulta_id)
        self.assertEqual(fila["imc"], 27.1)
        self.assertEqual(fila["tam"], 93.3)

    def test_lo_que_el_medico_escribe_a_mano_le_gana_al_calculo(self):
        basedatos.guardar_signos_vitales(
            self.con, self.consulta_id, peso=78.4, talla=1.70, imc=28.0
        )
        self.assertEqual(
            basedatos.obtener_signos_vitales(self.con, self.consulta_id)["imc"], 28.0
        )

    def test_la_talla_en_centimetros_tambien_sirve(self):
        self.assertEqual(basedatos.calcular_imc(78.4, 170), 27.1)
        self.assertEqual(basedatos.calcular_imc(78.4, 1.70), 27.1)

    def test_los_calculos_no_se_rompen_con_lo_que_falta(self):
        for peso, talla in ((None, 1.7), (78.4, None), (0, 1.7), (78.4, 0), ("", "")):
            with self.subTest(peso=peso, talla=talla):
                self.assertIsNone(basedatos.calcular_imc(peso, talla))
        self.assertIsNone(basedatos.calcular_tam(None, 80))
        self.assertIsNone(basedatos.calcular_tam(120, None))
        self.assertEqual(basedatos.calcular_tam(120, 80), 93.3)

    def test_el_historico_va_de_la_mas_vieja_a_la_mas_nueva(self):
        """Es el orden en que se grafica la evolución de peso e IMC."""
        for fecha, peso in (("2026-08-14", 97.9), ("2026-01-05", 101.2), ("2026-05-01", 99.4)):
            consulta = basedatos.crear_consulta(self.con, self.paciente_id, fecha=fecha)
            basedatos.guardar_signos_vitales(self.con, consulta, peso=peso, talla=1.68)
        historico = basedatos.historico_signos_vitales(self.con, self.paciente_id)
        self.assertEqual([f["fecha"] for f in historico],
                         ["2026-01-05", "2026-05-01", "2026-08-14"])
        self.assertEqual([f["peso"] for f in historico], [101.2, 99.4, 97.9])

    def test_al_borrar_la_consulta_se_van_sus_signos(self):
        basedatos.guardar_signos_vitales(self.con, self.consulta_id, fc=72)
        self.con.execute("DELETE FROM consultas WHERE id = ?", (self.consulta_id,))
        self.assertIsNone(basedatos.obtener_signos_vitales(self.con, self.consulta_id))


# --------------------------------------------------------------------------
# Anexos: las imágenes que llegan por WhatsApp (dec. 11)
# --------------------------------------------------------------------------

class TestAnexos(BaseHistoria):

    def anexar(self, sha256="ab12", fecha="2026-08-14", **extra) -> int:
        return basedatos.crear_anexo(
            self.con, self.paciente_id,
            f"pacientes/EC-0001_Maria-Gonzalez/anexos/{sha256}.jpg",
            sha256, fecha, **extra,
        )

    def test_guarda_ruta_relativa_hash_y_procedencia(self):
        anexo_id = self.anexar(
            origen=r"C:\Users\luxmu\Downloads\WhatsApp Image 2026-08-18 at 3.14.48 PM.jpeg",
            ancho_px=909, alto_px=1280, bytes=131949, nota="Báscula CF610_G",
        )
        fila = basedatos.obtener_anexo(self.con, anexo_id)
        self.assertTrue(fila["ruta_relativa"].startswith("pacientes/"))
        self.assertEqual((fila["ancho_px"], fila["alto_px"], fila["bytes"]),
                         (909, 1280, 131949))
        self.assertIn("Downloads", fila["origen"])
        self.assertEqual(fila["tipo"], "medicion")

    def test_la_fecha_es_la_de_la_medicion_y_no_la_del_archivo(self):
        """Probado en el ejemplo real: cuatro días de diferencia."""
        anexo_id = self.anexar(fecha="2026-08-14")
        self.assertEqual(
            basedatos.obtener_anexo(self.con, anexo_id)["fecha_medicion"], "2026-08-14"
        )
        basedatos.actualizar_anexo(self.con, anexo_id, fecha_medicion="2026-08-10")
        self.assertEqual(
            basedatos.obtener_anexo(self.con, anexo_id)["fecha_medicion"], "2026-08-10"
        )

    def test_el_mismo_archivo_no_se_anexa_dos_veces(self):
        self.anexar(sha256="ABCD")
        with self.assertRaises(sqlite3.IntegrityError):
            self.anexar(sha256="abcd")  # el hash se guarda en minúsculas

    def test_el_hash_dice_con_quien_quedo_anexado(self):
        self.anexar(sha256="ABCD")
        fila = basedatos.obtener_anexo_por_sha256(self.con, "abcd")
        self.assertEqual(fila["paciente_id"], self.paciente_id)
        self.assertIsNone(basedatos.obtener_anexo_por_sha256(self.con, "otro"))
        self.assertEqual(basedatos.sha256_anexados(self.con), {"abcd"})

    def test_el_anexo_necesita_ruta_y_hash(self):
        for ruta, sha in (("", "abcd"), ("x.jpg", "")):
            with self.subTest(ruta=ruta, sha=sha):
                with self.assertRaises(ValueError):
                    basedatos.crear_anexo(self.con, self.paciente_id, ruta, sha, "2026-08-14")

    def test_puede_no_tener_consulta(self):
        """Dec. 11 y §4 del análisis: llegan imágenes entre visita y visita."""
        anexo_id = self.anexar()
        self.assertIsNone(basedatos.obtener_anexo(self.con, anexo_id)["consulta_id"])
        consulta = basedatos.crear_consulta(self.con, self.paciente_id, fecha="2026-08-14")
        basedatos.actualizar_anexo(self.con, anexo_id, consulta_id=consulta)
        self.assertEqual(basedatos.listar_anexos_de_consulta(self.con, consulta)[0]["id"],
                         anexo_id)

    def test_se_listan_del_mas_nuevo_al_mas_viejo(self):
        self.anexar(sha256="a1", fecha="2026-01-05")
        self.anexar(sha256="a2", fecha="2026-08-14")
        self.anexar(sha256="a3", fecha="2026-05-01")
        self.assertEqual(
            [f["fecha_medicion"] for f in basedatos.listar_anexos(self.con, self.paciente_id)],
            ["2026-08-14", "2026-05-01", "2026-01-05"],
        )

    def test_borrar_la_consulta_no_borra_el_anexo(self):
        consulta = basedatos.crear_consulta(self.con, self.paciente_id, fecha="2026-08-14")
        anexo_id = self.anexar(consulta_id=consulta)
        self.con.execute("DELETE FROM consultas WHERE id = ?", (consulta,))
        fila = basedatos.obtener_anexo(self.con, anexo_id)
        self.assertIsNotNone(fila)
        self.assertIsNone(fila["consulta_id"])


# --------------------------------------------------------------------------
# Mediciones: los valores clave tipeados a mano (dec. 13)
# --------------------------------------------------------------------------

class TestMediciones(BaseHistoria):

    def test_guarda_los_cinco_valores_del_grafico(self):
        medicion_id = basedatos.crear_medicion(
            self.con, self.paciente_id, fecha="2026-08-14",
            peso=97.9, imc=34.6, grasa_pct=44.3, musculo_kg=30.2, grasa_visceral=19,
        )
        fila = basedatos.obtener_medicion(self.con, medicion_id)
        self.assertEqual((fila["peso"], fila["imc"], fila["grasa_pct"]), (97.9, 34.6, 44.3))
        self.assertEqual((fila["musculo_kg"], fila["grasa_visceral"]), (30.2, 19.0))

    def test_todo_es_opcional(self):
        """Nunca obligatorio (dec. 13): una medición puede ser solo el peso."""
        medicion_id = basedatos.crear_medicion(
            self.con, self.paciente_id, fecha="2026-08-14", peso=97.9
        )
        fila = basedatos.obtener_medicion(self.con, medicion_id)
        self.assertEqual(fila["peso"], 97.9)
        self.assertIsNone(fila["imc"])
        self.assertIsNone(fila["anexo_id"])

    def test_se_listan_de_la_mas_vieja_a_la_mas_nueva(self):
        for fecha, peso in (("2026-08-14", 97.9), ("2026-01-05", 101.2)):
            basedatos.crear_medicion(self.con, self.paciente_id, fecha=fecha, peso=peso)
        self.assertEqual(
            [f["peso"] for f in basedatos.listar_mediciones(self.con, self.paciente_id)],
            [101.2, 97.9],
        )

    def test_los_numeros_sobreviven_a_su_imagen(self):
        """Los tipeó el médico: no se pierden si el anexo se va."""
        anexo_id = basedatos.crear_anexo(
            self.con, self.paciente_id, "pacientes/EC-0001/anexos/a.jpg", "aa11", "2026-08-14"
        )
        medicion_id = basedatos.crear_medicion(
            self.con, self.paciente_id, fecha="2026-08-14", peso=97.9, anexo_id=anexo_id
        )
        self.con.execute("DELETE FROM anexos WHERE id = ?", (anexo_id,))
        fila = basedatos.obtener_medicion(self.con, medicion_id)
        self.assertEqual(fila["peso"], 97.9)
        self.assertIsNone(fila["anexo_id"])


# --------------------------------------------------------------------------
# Informes (dec. 9 a 12)
# --------------------------------------------------------------------------

class TestInformes(BaseHistoria):

    def test_los_dos_tipos(self):
        clinico = basedatos.crear_informe(
            self.con, self.paciente_id, tipo="clinico", fecha="2026-08-18",
            cuerpo="Se trata de paciente femenino de 47 años de edad…",
            diagnostico="Dislipidemia",
            tratamiento="Se indican exámenes pertinentes diagnósticos",
            ciudad="Maracaibo",
        )
        aseguradora = basedatos.crear_informe(
            self.con, self.paciente_id, tipo="aseguradora", fecha="2026-08-18",
            numero_poliza="A-123", prestacion_sanitaria="Consulta especializada",
            antecedentes="Dislipidemia desde 2024", motivo_consulta="Aumento de peso",
            evolucion="Estable", diagnostico="Dislipidemia",
        )
        self.assertEqual(basedatos.obtener_informe(self.con, clinico)["tipo"], "clinico")
        fila = basedatos.obtener_informe(self.con, aseguradora)
        self.assertEqual(fila["tipo"], "aseguradora")
        self.assertEqual(fila["numero_poliza"], "A-123")
        self.assertEqual(fila["prestacion_sanitaria"], "Consulta especializada")

    def test_un_tipo_inventado_no_entra(self):
        with self.assertRaises(ValueError):
            basedatos.crear_informe(self.con, self.paciente_id, tipo="constancia")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                """
                INSERT INTO informes (paciente_id, tipo, fecha, creado_en, actualizado_en)
                VALUES (?, 'constancia', '2026-08-18', 'x', 'x')
                """,
                (self.paciente_id,),
            )

    def test_el_codigo_del_paciente_se_copia_literal_al_emitir(self):
        informe_id = basedatos.crear_informe(self.con, self.paciente_id, fecha="2026-08-18")
        self.assertEqual(
            basedatos.obtener_informe(self.con, informe_id)["codigo_paciente"], "EC-0001"
        )
        # Un documento emitido no se mueve si mañana cambia la ficha.
        self.con.execute("UPDATE pacientes SET codigo = 'ZZ-9999' WHERE id = ?",
                         (self.paciente_id,))
        self.assertEqual(
            basedatos.obtener_informe(self.con, informe_id)["codigo_paciente"], "EC-0001"
        )

    def test_se_guarda_la_ruta_del_pdf(self):
        informe_id = basedatos.crear_informe(self.con, self.paciente_id, fecha="2026-08-18")
        basedatos.guardar_ruta_pdf_informe(self.con, informe_id, r"pdf\2026\informe.pdf")
        self.assertEqual(
            basedatos.obtener_informe(self.con, informe_id)["ruta_pdf"],
            r"pdf\2026\informe.pdf",
        )

    def test_se_anula_con_motivo_y_nunca_se_borra(self):
        informe_id = basedatos.crear_informe(self.con, self.paciente_id, fecha="2026-08-18")
        basedatos.anular_informe(self.con, informe_id, "Datos equivocados")
        fila = basedatos.obtener_informe(self.con, informe_id)
        self.assertEqual(fila["anulado"], 1)
        self.assertEqual(fila["motivo_anulacion"], "Datos equivocados")
        self.assertIsNotNone(fila["fecha_anulacion"])
        self.assertEqual(len(basedatos.listar_informes(self.con, self.paciente_id)), 1)

    def test_anular_exige_motivo_y_no_se_repite(self):
        informe_id = basedatos.crear_informe(self.con, self.paciente_id, fecha="2026-08-18")
        with self.assertRaises(ValueError):
            basedatos.anular_informe(self.con, informe_id, "   ")
        basedatos.anular_informe(self.con, informe_id, "Datos equivocados")
        with self.assertRaises(ValueError):
            basedatos.anular_informe(self.con, informe_id, "De nuevo")

    def test_se_listan_del_mas_nuevo_al_mas_viejo(self):
        basedatos.crear_informe(self.con, self.paciente_id, fecha="2026-01-05")
        basedatos.crear_informe(self.con, self.paciente_id, fecha="2026-08-18")
        self.assertEqual(
            [f["fecha"] for f in basedatos.listar_informes(self.con, self.paciente_id)],
            ["2026-08-18", "2026-01-05"],
        )

    def test_los_anexos_del_informe_son_opt_in_y_ordenados(self):
        """Dec. 12: el médico marca cuáles salen, y en qué orden."""
        primero = basedatos.crear_anexo(
            self.con, self.paciente_id, "a/1.jpg", "h1", "2026-08-14"
        )
        segundo = basedatos.crear_anexo(
            self.con, self.paciente_id, "a/2.jpg", "h2", "2026-08-15"
        )
        informe_id = basedatos.crear_informe(
            self.con, self.paciente_id, fecha="2026-08-18", anexos=[segundo, primero]
        )
        self.assertEqual(
            [f["id"] for f in basedatos.listar_anexos_de_informe(self.con, informe_id)],
            [segundo, primero],
        )

        # Volver a elegir reemplaza la selección, no la acumula.
        basedatos.vincular_anexos_informe(self.con, informe_id, [primero])
        self.assertEqual(
            [f["id"] for f in basedatos.listar_anexos_de_informe(self.con, informe_id)],
            [primero],
        )

    def test_sin_anexos_marcados_el_informe_sale_solo(self):
        informe_id = basedatos.crear_informe(self.con, self.paciente_id, fecha="2026-08-18")
        self.assertEqual(basedatos.listar_anexos_de_informe(self.con, informe_id), [])

    def test_corregir_el_informe_guardado(self):
        informe_id = basedatos.crear_informe(
            self.con, self.paciente_id, fecha="2026-08-18", diagnostico="Dislipidemia"
        )
        basedatos.actualizar_informe(
            self.con, informe_id, diagnostico="Dislipidemia mixta", tipo="aseguradora"
        )
        fila = basedatos.obtener_informe(self.con, informe_id)
        self.assertEqual(fila["diagnostico"], "Dislipidemia mixta")
        self.assertEqual(fila["tipo"], "aseguradora")
        with self.assertRaises(ValueError):
            basedatos.actualizar_informe(self.con, informe_id, tipo="constancia")


if __name__ == "__main__":
    unittest.main(verbosity=2)
