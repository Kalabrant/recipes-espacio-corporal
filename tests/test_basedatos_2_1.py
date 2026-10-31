"""Tests de la capa de datos de la evolución 2.1 (build/contrato-2.1.md §1 y §2).

Cubren lo que se agregó a `basedatos.py`: la migración nueva, el catálogo de
análisis sembrado, las órdenes de exámenes y el mapa de infiltraciones. El
criterio es el del resto de la suite: lo que el médico va a hacer de verdad y
lo que la base tiene que impedirle. Sin red y sin dependencias fuera de la
stdlib (§3).

Se corre con:  py -3 -m pytest tests/test_basedatos_2_1.py -q
"""

from __future__ import annotations

import json
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


ITEMS_EXAMEN = [
    {"examen": "Hematología completa", "muestra": "Sangre",
     "indicaciones": "No requiere ayuno."},
    {"examen": "Glicemia en ayunas", "muestra": "Sangre",
     "indicaciones": "Ayuno de 8 a 12 horas."},
    {"examen": "Examen de orina (uroanálisis)", "muestra": "Orina",
     "indicaciones": "Primera orina de la mañana, chorro medio, previo aseo genital."},
]

PUNTOS = [
    {"orden": 1, "x": 0.412, "y": 0.233, "lado": "I",
     "zona": "Frontal — línea media medial", "productoId": "p1", "dosis": 2,
     "notas": "intradérmico"},
    {"orden": 2, "x": 0.588, "y": 0.233, "lado": "D",
     "zona": "Frontal — línea media medial", "productoId": "p1", "dosis": 2,
     "notas": ""},
]

PRODUCTOS = [
    {"id": "p1", "nombre": "Toxina A — marca 1", "tipo": "toxina", "unidad": "U",
     "color": "#D92B2B", "lote": "L-4471", "caducidad": "2027-01"},
]

CALIBRACION = {"pupilaIzq": [0.33, 0.41], "pupilaDer": [0.66, 0.41],
               "menton": [0.5, 0.83]}


class BaseDatos21(unittest.TestCase):
    """Base limpia y ya migrada, con un paciente cargado."""

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_2_1_"))
        self.con = basedatos.inicializar(self.carpeta / "recipes.db")
        self.paciente_id = basedatos.crear_paciente(
            self.con, "María Fernanda Rodríguez", cedula="V-11222333", edad=38, sexo="F"
        )
        self.codigo = basedatos.obtener_paciente(self.con, self.paciente_id)["codigo"]

    def tearDown(self) -> None:
        self.con.close()
        shutil.rmtree(self.carpeta, ignore_errors=True)


# --------------------------------------------------------------------------
# La migración: base nueva, base vieja y correrla dos veces
# --------------------------------------------------------------------------

class TestMigracion(unittest.TestCase):

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_migra_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def _tablas(self, con: sqlite3.Connection) -> set[str]:
        return {f["name"] for f in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}

    def test_base_vacia_queda_en_la_version_del_codigo(self):
        con = basedatos.inicializar(self.carpeta / "nueva.db")
        self.addCleanup(con.close)
        self.assertEqual(basedatos.version_actual(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(basedatos.VERSION_ESQUEMA, len(basedatos.MIGRACIONES))
        self.assertLessEqual(
            {"examenes", "examen_items", "analisis", "infiltraciones"},
            self._tablas(con),
        )

    def test_una_base_de_la_version_anterior_migra_sin_perder_nada(self):
        """Lo que ya está en la máquina del médico tiene que sobrevivir.

        Se arma una base parando en la versión anterior —aplicando solo las
        migraciones de antes de esta— se le mete un paciente con su récipe, y
        recién ahí se migra.
        """
        anterior = basedatos.VERSION_ESQUEMA - 1
        ruta = self.carpeta / "vieja.db"
        con = basedatos.conectar(ruta)
        self.addCleanup(con.close)
        con.execute("PRAGMA foreign_keys = OFF")
        for indice in range(anterior):
            con.executescript(
                f"BEGIN;\n{basedatos.MIGRACIONES[indice]}\n"
                f"PRAGMA user_version = {indice + 1};\nCOMMIT;"
            )
        con.execute("PRAGMA foreign_keys = ON")
        self.assertEqual(basedatos.version_actual(con), anterior)
        self.assertNotIn("analisis", self._tablas(con))

        paciente_id = basedatos.crear_paciente(con, "Pedro Antonio Silva", edad=61)
        recipe = codigos.crear_recipe(
            con, paciente_id,
            [{"medicamento": "Losartán", "presentacion": "50 mg",
              "cantidad": "30 tabletas", "dosis": "1 diaria"}],
            diagnostico="Hipertensión arterial",
        )

        self.assertEqual(basedatos.migrar(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(basedatos.version_actual(con), basedatos.VERSION_ESQUEMA)

        # El paciente y su récipe siguen enteros.
        paciente = basedatos.obtener_paciente(con, paciente_id)
        self.assertEqual(paciente["nombre"], "Pedro Antonio Silva")
        self.assertTrue(paciente["codigo"])
        vivo = basedatos.obtener_recipe(con, recipe["id"])
        self.assertEqual(vivo["codigo"], recipe["codigo"])
        self.assertEqual(vivo["diagnostico"], "Hipertensión arterial")
        self.assertEqual(len(basedatos.obtener_items(con, recipe["id"])), 1)

        # Y las tablas de la 2.1 están, con el catálogo sembrado.
        self.assertLessEqual(
            {"examenes", "examen_items", "analisis", "infiltraciones"},
            self._tablas(con),
        )
        self.assertGreaterEqual(
            con.execute("SELECT COUNT(*) FROM analisis").fetchone()[0], 70
        )

    def test_migrar_dos_veces_no_duplica_el_catalogo(self):
        con = basedatos.inicializar(self.carpeta / "dos.db")
        self.addCleanup(con.close)
        cuantos = con.execute("SELECT COUNT(*) FROM analisis").fetchone()[0]
        self.assertEqual(basedatos.migrar(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(basedatos.migrar(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM analisis").fetchone()[0], cuantos
        )
        self.assertEqual(
            con.execute(
                "SELECT COUNT(*) FROM (SELECT texto_norm FROM analisis GROUP BY texto_norm)"
            ).fetchone()[0],
            cuantos,
        )


# --------------------------------------------------------------------------
# El catálogo de análisis (contrato §2)
# --------------------------------------------------------------------------

class TestCatalogo(BaseDatos21):

    def test_viene_sembrado_con_los_grupos_del_contrato(self):
        cuantos = self.con.execute("SELECT COUNT(*) FROM analisis").fetchone()[0]
        self.assertEqual(cuantos, 75)
        grupos = {f["grupo"] for f in self.con.execute("SELECT DISTINCT grupo FROM analisis")}
        self.assertEqual(grupos, {
            "Hematología", "Química sanguínea", "Hormonas", "Orina y heces",
            "Inmunología y serología", "Marcadores", "Estudios",
        })
        de_fabrica = self.con.execute(
            "SELECT COUNT(*) FROM analisis WHERE de_fabrica = 1 AND veces_usado = 0"
        ).fetchone()[0]
        self.assertEqual(de_fabrica, cuantos)

    def test_el_texto_norm_sembrado_es_el_que_produce_normalizar(self):
        """Si se desalinearan, el catálogo se duplicaría al primer uso."""
        for fila in self.con.execute("SELECT texto, texto_norm FROM analisis"):
            self.assertEqual(fila["texto_norm"], basedatos.normalizar(fila["texto"]))

    def test_obtener_o_crear_devuelve_el_sembrado_y_no_duplica(self):
        cuantos = self.con.execute("SELECT COUNT(*) FROM analisis").fetchone()[0]
        esperado = self.con.execute(
            "SELECT id FROM analisis WHERE texto_norm = 'hematologia completa'"
        ).fetchone()["id"]
        self.assertEqual(
            basedatos.obtener_o_crear_analisis(self.con, "Hematología completa"), esperado
        )
        # También escrito sin acentos y con espacios de más.
        self.assertEqual(
            basedatos.obtener_o_crear_analisis(self.con, "  hematologia   COMPLETA "),
            esperado,
        )
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM analisis").fetchone()[0], cuantos
        )

    def test_una_fila_de_fabrica_no_se_pisa(self):
        antes = dict(self.con.execute(
            "SELECT * FROM analisis WHERE texto_norm = 'hematologia completa'"
        ).fetchone())
        basedatos.aprender_analisis(self.con, [
            {"examen": "Hematología completa", "muestra": "Suero",
             "indicaciones": "Ayuno de 3 días."},
        ])
        despues = dict(self.con.execute(
            "SELECT * FROM analisis WHERE texto_norm = 'hematologia completa'"
        ).fetchone())
        self.assertEqual(despues["grupo"], antes["grupo"])
        self.assertEqual(despues["muestra"], "Sangre")
        self.assertEqual(despues["preparacion"], "No requiere ayuno.")
        self.assertEqual(despues["veces_usado"], antes["veces_usado"] + 1)

    def test_un_analisis_nuevo_se_crea_y_se_aprende(self):
        nuevo_id = basedatos.obtener_o_crear_analisis(
            self.con, "Zinc sérico", muestra="Sangre"
        )
        fila = self.con.execute(
            "SELECT * FROM analisis WHERE id = ?", (nuevo_id,)
        ).fetchone()
        self.assertEqual(fila["texto"], "Zinc sérico")
        self.assertEqual(fila["texto_norm"], "zinc serico")
        self.assertEqual(fila["de_fabrica"], 0)
        self.assertEqual(fila["veces_usado"], 0)
        self.assertIsNone(fila["grupo"])

        basedatos.aprender_analisis(self.con, [
            {"examen": "Zinc sérico", "muestra": "Sangre",
             "indicaciones": "Ayuno de 8 a 12 horas."},
            {"examen": "  ", "muestra": "Sangre"},   # renglón vacío: se ignora
        ])
        basedatos.aprender_analisis(self.con, [{"examen": "zinc serico"}])
        fila = self.con.execute(
            "SELECT * FROM analisis WHERE id = ?", (nuevo_id,)
        ).fetchone()
        self.assertEqual(fila["veces_usado"], 2)
        self.assertIsNotNone(fila["ultima_vez"])
        # El hueco que tenía se completó con lo que escribió el médico.
        self.assertEqual(fila["preparacion"], "Ayuno de 8 a 12 horas.")
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM analisis").fetchone()[0], 76
        )

    def test_buscar_y_listar(self):
        encontrados = [f["texto"] for f in basedatos.buscar_analisis(self.con, "glicemia")]
        self.assertIn("Glicemia en ayunas", encontrados)
        # Sin acentos y por subcadena, como el resto del autocompletado.
        self.assertIn(
            "Hematología completa",
            [f["texto"] for f in basedatos.buscar_analisis(self.con, "hematolog")],
        )
        self.assertLessEqual(
            len(basedatos.buscar_analisis(self.con, "")), basedatos.LIMITE_SUGERENCIAS
        )

    def test_el_catalogo_sale_en_el_orden_clinico(self):
        """La pantalla pinta esto tal cual: el orden de acá es el que se ve.

        Alfabético pondría Estudios y Hormonas antes que Hematología, que es
        donde el médico empieza a mirar.
        """
        todos = basedatos.listar_analisis_por_grupo(self.con)
        self.assertEqual(len(todos), 75)

        grupos = [f["grupo"] for f in todos]
        vistos = list(dict.fromkeys(grupos))
        self.assertEqual(vistos, list(basedatos.ORDEN_GRUPOS_ANALISIS))
        self.assertEqual(vistos, [
            "Hematología", "Química sanguínea", "Hormonas", "Orina y heces",
            "Inmunología y serología", "Marcadores", "Estudios",
        ])
        # Cada grupo sale de una sola vez, no salteado.
        self.assertEqual(len(vistos), len(set(grupos)))
        self.assertEqual(todos[0]["texto"], "Contaje de plaquetas")

        # Y adentro de cada grupo, por texto sin acentos: "Ácido úrico" va en
        # la A, no después de la Z.
        quimica = [f["texto_norm"] for f in todos if f["grupo"] == "Química sanguínea"]
        self.assertEqual(quimica, sorted(quimica))
        self.assertEqual(quimica[0], "acido urico")

    def test_los_grupos_que_invente_el_medico_caen_al_final(self):
        basedatos.obtener_o_crear_analisis(
            self.con, "Perfil genético ampliado", grupo="Zzz genética")
        basedatos.obtener_o_crear_analisis(
            self.con, "Cariotipo", grupo="Aaa genética")
        basedatos.obtener_o_crear_analisis(self.con, "Zinc sérico")   # sin grupo

        todos = basedatos.listar_analisis_por_grupo(self.con)
        self.assertEqual(len(todos), 78)
        vistos = list(dict.fromkeys(f["grupo"] for f in todos))
        # Los de fábrica no se movieron; los inventados van detrás, alfabéticos
        # entre ellos, y el que no tiene grupo al final del todo.
        self.assertEqual(
            vistos,
            [*basedatos.ORDEN_GRUPOS_ANALISIS, "Aaa genética", "Zzz genética", None],
        )
        self.assertEqual(todos[-1]["texto"], "Zinc sérico")

    def test_analisis_entra_en_las_tablas_de_terminos(self):
        self.assertIn("analisis", basedatos.TABLAS_TERMINOS)
        # `obtener_o_crear_termino` inserta solo las columnas base: las tres
        # propias quedan en su default y no revienta el NOT NULL.
        termino_id = basedatos.obtener_o_crear_termino(self.con, "analisis", "Cobre sérico")
        fila = self.con.execute(
            "SELECT * FROM analisis WHERE id = ?", (termino_id,)
        ).fetchone()
        self.assertEqual(fila["de_fabrica"], 0)
        self.assertIsNone(fila["grupo"])
        # Y `buscar_terminos` (SELECT *) devuelve también las columnas nuevas.
        encontrado = basedatos.buscar_terminos(self.con, "analisis", "cobre")[0]
        self.assertIn("preparacion", encontrado.keys())
        self.assertIn("muestra", encontrado.keys())


# --------------------------------------------------------------------------
# Órdenes de exámenes
# --------------------------------------------------------------------------

class TestExamenes(BaseDatos21):

    def _crear(self, **extra):
        return basedatos.crear_examen(
            self.con, self.paciente_id, self.codigo, ITEMS_EXAMEN,
            fecha_emision="2026-08-26",
            diagnostico="Control anual",
            indicaciones_generales="Traer los resultados al control.\nEn ayunas.",
            **extra,
        )

    def test_alta_con_tres_items_en_orden(self):
        examen_id = self._crear()
        examen = basedatos.obtener_examen(self.con, examen_id)
        self.assertEqual(examen["codigo"], self.codigo)
        self.assertEqual(examen["paciente_id"], self.paciente_id)
        self.assertEqual(examen["fecha_emision"], "2026-08-26")
        self.assertEqual(examen["anulado"], 0)
        self.assertEqual(
            examen["indicaciones_generales"],
            "Traer los resultados al control.\nEn ayunas.",
        )

        items = basedatos.obtener_items_examen(self.con, examen_id)
        self.assertEqual([i["orden"] for i in items], [1, 2, 3])
        self.assertEqual(
            [i["examen"] for i in items],
            ["Hematología completa", "Glicemia en ayunas", "Examen de orina (uroanálisis)"],
        )
        self.assertEqual(items[2]["muestra"], "Orina")

    def test_sin_analisis_no_hay_orden(self):
        with self.assertRaises(ValueError):
            basedatos.crear_examen(self.con, self.paciente_id, self.codigo, [])
        with self.assertRaises(ValueError):
            basedatos.crear_examen(
                self.con, self.paciente_id, self.codigo, [{"examen": "   "}]
            )
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM examenes").fetchone()[0], 0
        )

    def test_sin_codigo_se_lo_resuelve_del_paciente(self):
        examen_id = basedatos.crear_examen(
            self.con, self.paciente_id, None, ITEMS_EXAMEN[:1]
        )
        self.assertEqual(
            basedatos.obtener_examen(self.con, examen_id)["codigo"], self.codigo
        )

    def test_completo_trae_al_paciente(self):
        examen_id = self._crear()
        fila = basedatos.obtener_examen_completo(self.con, examen_id)
        self.assertEqual(fila["paciente_nombre"], "María Fernanda Rodríguez")
        self.assertEqual(fila["paciente_codigo"], self.codigo)
        self.assertEqual(fila["cantidad_items"], 3)

    def test_busqueda_por_codigo_por_paciente_y_por_analisis(self):
        examen_id = self._crear()
        for termino in (self.codigo, self.codigo.lower(), "rodriguez", "glicemia",
                        "HEMATOLOGIA"):
            with self.subTest(termino=termino):
                encontrados = [f["id"] for f in basedatos.buscar_examenes(self.con, termino)]
                self.assertIn(examen_id, encontrados)
        self.assertEqual(basedatos.buscar_examenes(self.con, "resonancia"), [])

        # Rango de fechas, inclusive las dos puntas.
        self.assertEqual(
            len(basedatos.buscar_examenes(self.con, desde="2026-08-26", hasta="2026-08-26")), 1
        )
        self.assertEqual(len(basedatos.buscar_examenes(self.con, desde="2026-08-27")), 0)

    def test_resumen_y_listado_del_paciente(self):
        primero = self._crear()
        segundo = basedatos.crear_examen(
            self.con, self.paciente_id, self.codigo,
            [{"examen": "TSH", "muestra": "Sangre"}],
            fecha_emision="2026-09-02",
        )
        listado = basedatos.listar_examenes_de_paciente(self.con, self.paciente_id)
        self.assertEqual([f["id"] for f in listado], [segundo, primero])

        resumen = basedatos.analisis_por_examen(self.con, [primero, segundo])
        self.assertEqual(resumen[segundo], ["TSH"])
        self.assertEqual(resumen[primero][0], "Hematología completa")
        self.assertEqual(basedatos.analisis_por_examen(self.con, []), {})

    def test_ruta_del_pdf_y_anulacion(self):
        examen_id = self._crear()
        basedatos.guardar_ruta_pdf_examen(self.con, examen_id, r"C:\x\EXAMENES.pdf")
        self.assertEqual(
            basedatos.obtener_examen(self.con, examen_id)["ruta_pdf"], r"C:\x\EXAMENES.pdf"
        )

        with self.assertRaises(ValueError):
            basedatos.anular_examen(self.con, examen_id, "   ")
        basedatos.anular_examen(self.con, examen_id, "El paciente cambió de laboratorio")
        anulado = basedatos.obtener_examen(self.con, examen_id)
        self.assertEqual(anulado["anulado"], 1)
        self.assertEqual(anulado["motivo_anulacion"], "El paciente cambió de laboratorio")
        self.assertTrue(anulado["fecha_anulacion"])
        # No se borra, y no se anula dos veces.
        with self.assertRaises(ValueError):
            basedatos.anular_examen(self.con, examen_id, "de nuevo")
        self.assertEqual(
            len(basedatos.listar_examenes_de_paciente(
                self.con, self.paciente_id, incluir_anulados=False)),
            0,
        )

    def test_los_renglones_cuelgan_de_la_orden(self):
        examen_id = self._crear()
        self.con.execute("DELETE FROM examenes WHERE id = ?", (examen_id,))
        self.assertEqual(basedatos.obtener_items_examen(self.con, examen_id), [])


# --------------------------------------------------------------------------
# Mapa de infiltraciones
# --------------------------------------------------------------------------

class TestInfiltraciones(BaseDatos21):

    def _crear(self, **extra):
        datos = dict(
            vista="mujer-frontal", fecha="2026-08-26", calibracion=CALIBRACION,
            productos=PRODUCTOS, puntos=PUNTOS, observaciones="Primera sesión.",
        )
        datos.update(extra)
        return basedatos.crear_infiltracion(
            self.con, self.paciente_id, self.codigo, **datos
        )

    def test_alta_con_puntos_y_productos(self):
        infiltracion_id = self._crear()
        datos = basedatos.infiltracion_a_dict(
            basedatos.obtener_infiltracion(self.con, infiltracion_id)
        )
        self.assertEqual(datos["codigo"], self.codigo)
        self.assertEqual(datos["vista"], "mujer-frontal")
        self.assertEqual(datos["fecha"], "2026-08-26")
        self.assertEqual(datos["calibracion"], CALIBRACION)
        self.assertEqual(datos["productos"], PRODUCTOS)
        self.assertEqual(datos["puntos"], PUNTOS)
        self.assertIsInstance(datos["puntos"], list)
        self.assertIsInstance(datos["puntos"][0], dict)
        self.assertEqual(datos["puntos"][0]["zona"], "Frontal — línea media medial")
        self.assertEqual(datos["anulado"], 0)

    def test_los_acentos_se_guardan_legibles(self):
        infiltracion_id = self._crear()
        crudo = self.con.execute(
            "SELECT puntos FROM infiltraciones WHERE id = ?", (infiltracion_id,)
        ).fetchone()["puntos"]
        self.assertIn("línea media medial", crudo)   # ensure_ascii=False

    def test_sin_lamina_no_hay_registro(self):
        with self.assertRaises(ValueError):
            basedatos.crear_infiltracion(
                self.con, self.paciente_id, self.codigo, vista="  "
            )

    def test_una_sesion_vacia_arranca_con_listas_vacias(self):
        infiltracion_id = basedatos.crear_infiltracion(
            self.con, self.paciente_id, self.codigo, vista="hombre-frontal"
        )
        datos = basedatos.infiltracion_a_dict(
            basedatos.obtener_infiltracion(self.con, infiltracion_id)
        )
        self.assertEqual(datos["productos"], [])
        self.assertEqual(datos["puntos"], [])
        self.assertEqual(datos["calibracion"], {})

    def test_actualizar_cambia_los_puntos_y_deja_el_resto(self):
        infiltracion_id = self._crear()
        nuevos = PUNTOS + [{"orden": 3, "x": 0.5, "y": 0.31, "lado": "C",
                            "zona": "Glabela", "productoId": "p1", "dosis": 4,
                            "notas": ""}]
        basedatos.actualizar_infiltracion(
            self.con, infiltracion_id, puntos=nuevos, observaciones="Se agregó glabela."
        )
        datos = basedatos.infiltracion_a_dict(
            basedatos.obtener_infiltracion(self.con, infiltracion_id)
        )
        self.assertEqual(len(datos["puntos"]), 3)
        self.assertEqual(datos["puntos"][2]["zona"], "Glabela")
        self.assertEqual(datos["observaciones"], "Se agregó glabela.")
        self.assertEqual(datos["productos"], PRODUCTOS)      # no se tocó
        self.assertEqual(datos["vista"], "mujer-frontal")    # tampoco

        with self.assertRaises(ValueError):
            basedatos.actualizar_infiltracion(self.con, infiltracion_id, inventado="x")

    def test_listado_ruta_del_pdf_y_anulacion(self):
        vieja = self._crear(fecha="2026-06-01")
        nueva = self._crear(fecha="2026-08-26")
        self.assertEqual(
            [f["id"] for f in basedatos.listar_infiltraciones(self.con, self.paciente_id)],
            [nueva, vieja],
        )

        basedatos.guardar_ruta_pdf_infiltracion(self.con, nueva, r"C:\x\INF.pdf")
        self.assertEqual(
            basedatos.obtener_infiltracion(self.con, nueva)["ruta_pdf"], r"C:\x\INF.pdf"
        )

        with self.assertRaises(ValueError):
            basedatos.anular_infiltracion(self.con, nueva, "")
        basedatos.anular_infiltracion(self.con, nueva, "Se cargó en el paciente equivocado")
        fila = basedatos.obtener_infiltracion(self.con, nueva)
        self.assertEqual(fila["anulado"], 1)
        self.assertEqual(fila["motivo_anulacion"], "Se cargó en el paciente equivocado")
        self.assertEqual(
            len(basedatos.listar_infiltraciones(
                self.con, self.paciente_id, incluir_anuladas=False)),
            1,
        )

    def test_json_corrupto_no_revienta(self):
        """Una fila rota deja la sesión vacía, nunca la historia sin abrir."""
        infiltracion_id = self._crear()
        self.con.execute(
            """
            UPDATE infiltraciones
               SET puntos = '[{"orden": 1, ', productos = 'no soy json',
                   calibracion = '[1, 2, 3]'
             WHERE id = ?
            """,
            (infiltracion_id,),
        )
        datos = basedatos.infiltracion_a_dict(
            basedatos.obtener_infiltracion(self.con, infiltracion_id)
        )
        self.assertEqual(datos["puntos"], [])
        self.assertEqual(datos["productos"], [])
        self.assertEqual(datos["calibracion"], {})   # era una lista: tipo equivocado
        # Y sigue siendo serializable, que es para lo que se lo pide.
        json.dumps(datos)

    def test_a_dict_de_nada(self):
        self.assertEqual(basedatos.infiltracion_a_dict(None), {})


if __name__ == "__main__":
    unittest.main()
