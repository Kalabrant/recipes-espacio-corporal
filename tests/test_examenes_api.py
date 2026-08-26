"""Tests de la API de órdenes de exámenes (`rutas.py`, contrato 2.1 §5).

Lo que se prueba acá es que la pestaña «Exámenes» se comporte como el récipe en
todo lo que importa —el código del paciente, la carpeta, el versionado del PDF,
la medición ANTES de escribir, la anulación con motivo— y que se distinga de él
donde tiene que distinguirse: los mensajes de error son los de una orden de
laboratorio, no los de un talonario de medicamentos.

Como en `test_rutas.py`, se usa el cliente de pruebas de Flask contra una
carpeta de datos temporal y **se generan PDF de verdad** (el logo y las Lato
salen del paquete): son unos segundos, pero es la única manera de comprobar que
el nombre de archivo colisiona y versiona bien, y que la previa de verdad no
deja nada escrito en disco.

Solo `unittest` de la stdlib más lo que ya es dependencia (§3).
Se corre con:  py -3 -m pytest tests/test_examenes_api.py -q
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import basedatos  # noqa: E402
import codigos  # noqa: E402
import rutas  # noqa: E402


#: Una orden corta y normal: dos análisis del catálogo de fábrica.
ITEMS = [
    {"examen": "Hematología completa", "muestra": "Sangre",
     "indicaciones": "No requiere ayuno."},
    {"examen": "Glicemia en ayunas", "muestra": "Sangre",
     "indicaciones": "Ayuno de 8 a 12 horas."},
]

#: Una orden que **no entra** en la media carta. Con diez análisis de renglón
#: largo ya se pasa de los 106,5 mm útiles de la mitad `Solicito:`; treinta es
#: para que no haya dudas y para que el test no dependa de un milímetro.
DEMASIADOS = [
    {"examen": f"Perfil lipídico completo, control número {i}",
     "muestra": "Sangre",
     "indicaciones": "Ayuno de 12 horas. No ingerir alcohol las 24 horas previas."}
    for i in range(30)
]


class BaseApp(unittest.TestCase):
    """App real sobre una carpeta temporal, sin abrir nada en el escritorio."""

    def setUp(self) -> None:
        # fpdf subsetea las Lato con fontTools y le deja archivos sin cerrar al
        # recolector: son ResourceWarning de una dependencia, no de la app.
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)

        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_examenes_"))
        # El borrado va como cleanup y no en `tearDown` por el orden: los
        # cleanups corren DESPUÉS de `tearDown` y en orden inverso, así que
        # registrándolo acá —lo primero— queda último, y para entonces ya se
        # cerraron las conexiones. En Windows, con `recipes.db` todavía tomado,
        # el `rmtree` fallaba entero.
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        self.dir_datos = self.carpeta / "Recipes"
        for sub in ("datos", "pdf", "registro", "respaldos", "recursos"):
            (self.dir_datos / sub).mkdir(parents=True)

        self._abrir_antes = os.environ.get("RECIPES_ABRIR_PDF")
        os.environ["RECIPES_ABRIR_PDF"] = "0"

        self.app = rutas.crear_app(self.dir_datos)
        self.app.config.update(TESTING=True)
        self.cliente = self.app.test_client()

    def tearDown(self) -> None:
        if self._abrir_antes is None:
            os.environ.pop("RECIPES_ABRIR_PDF", None)
        else:
            os.environ["RECIPES_ABRIR_PDF"] = self._abrir_antes

    # -- ayudas ------------------------------------------------------------

    def emitir(self, nombre="Juan Pérez", cedula="V-12345678", items=None,
               fecha="2026-08-26", **extra):
        cuerpo = {
            "paciente": {"nombre": nombre, "cedula": cedula, "edad": 40},
            "items": items if items is not None else ITEMS,
            "fecha_emision": fecha,
            **extra,
        }
        respuesta = self.cliente.post("/api/examenes", json=cuerpo)
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        return respuesta.get_json()

    def conexion(self):
        return basedatos.inicializar(self.dir_datos / "datos" / "recipes.db")

    def historial(self, **filtros):
        consulta = "&".join(f"{k}={v}" for k, v in filtros.items())
        respuesta = self.cliente.get(f"/api/examenes?{consulta}")
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        return respuesta.get_json()["resultados"]

    @property
    def dir_pacientes(self) -> Path:
        return self.dir_datos / "pacientes"


# --------------------------------------------------------------------------
# El catálogo de análisis
# --------------------------------------------------------------------------

class TestSugerenciasAnalisis(BaseApp):

    def test_sin_q_devuelve_el_catalogo_entero(self):
        """La pantalla pinta con esto el panel de análisis frecuentes.

        Si acá se devolvieran las ocho primeras —como en las demás
        sugerencias— el panel de casillas quedaría con ocho renglones de un
        catálogo de decenas, y la vía rápida de la pestaña dejaría de servir.
        """
        respuesta = self.cliente.get("/api/sugerencias/analisis")
        self.assertEqual(respuesta.status_code, 200)
        resultados = respuesta.get_json()["resultados"]

        self.assertGreater(len(resultados), basedatos.LIMITE_SUGERENCIAS)
        con = self.conexion()
        try:
            self.assertEqual(len(resultados),
                             len(basedatos.listar_analisis_por_grupo(con)))
        finally:
            con.close()

    def test_el_catalogo_viene_agrupado_y_con_las_tres_columnas_propias(self):
        resultados = self.cliente.get(
            "/api/sugerencias/analisis").get_json()["resultados"]
        por_texto = {r["texto"]: r for r in resultados}

        glicemia = por_texto["Glicemia en ayunas"]
        self.assertEqual(glicemia["grupo"], "Química sanguínea")
        self.assertEqual(glicemia["muestra"], "Sangre")
        self.assertEqual(glicemia["preparacion"], "Ayuno de 8 a 12 horas.")
        self.assertEqual(glicemia["veces_usado"], 0)

        # Los grupos salen en el orden clínico, no alfabético: Hematología
        # antes que Estudios, aunque la E vaya primero en el abecedario.
        grupos = []
        for fila in resultados:
            if fila["grupo"] and fila["grupo"] not in grupos:
                grupos.append(fila["grupo"])
        self.assertEqual(grupos[0], "Hematología")

    def test_con_q_busca_y_corta_en_el_tope_de_sugerencias(self):
        resultados = self.cliente.get(
            "/api/sugerencias/analisis?q=glicemia").get_json()["resultados"]
        self.assertTrue(resultados)
        self.assertLessEqual(len(resultados), basedatos.LIMITE_SUGERENCIAS)
        for fila in resultados:
            self.assertIn("glicemia", basedatos.normalizar(fila["texto"]))

    def test_con_q_sin_acentos(self):
        """§8: se busca sin acentos, como en el resto de la aplicación."""
        resultados = self.cliente.get(
            "/api/sugerencias/analisis?q=acido urico").get_json()["resultados"]
        self.assertIn("Ácido úrico", [r["texto"] for r in resultados])


# --------------------------------------------------------------------------
# Medir y vista previa: las dos consultas que no escriben
# --------------------------------------------------------------------------

class TestMedirYPrevia(BaseApp):

    def test_medir_devuelve_las_mismas_claves_que_el_recipe(self):
        """El aviso de capacidad de la pantalla es el mismo que ya anda."""
        respuesta = self.cliente.post("/api/examenes/medir", json={
            "paciente_nombre": "Juan Pérez", "items": ITEMS,
        })
        self.assertEqual(respuesta.status_code, 200)
        medida = respuesta.get_json()
        self.assertEqual(
            set(medida),
            {"entra", "rp_usado_mm", "rp_disponible_mm", "ind_usado_mm",
             "ind_disponible_mm", "nombre_estado", "nombre_impreso"},
        )
        self.assertTrue(medida["entra"])
        self.assertGreater(medida["rp_usado_mm"], 0)

    def test_medir_admite_el_formulario_a_medio_llenar(self):
        """Es una consulta, no un guardado: sin análisis todavía no es un error.

        La pantalla mide mientras el médico escribe el nombre del paciente, y
        un 400 en cada tecla haría el aviso inservible.
        """
        respuesta = self.cliente.post("/api/examenes/medir", json={
            "paciente_nombre": "Juan", "items": [],
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.get_json()["entra"])

    def test_medir_avisa_cuando_no_entra(self):
        medida = self.cliente.post("/api/examenes/medir", json={
            "paciente_nombre": "Juan Pérez", "items": DEMASIADOS,
        }).get_json()
        self.assertFalse(medida["entra"])
        self.assertGreater(medida["rp_usado_mm"], medida["rp_disponible_mm"])

    def test_la_previa_devuelve_un_pdf(self):
        respuesta = self.cliente.post("/api/examenes/vista-previa", json={
            "paciente": {"nombre": "Juan Pérez"}, "items": ITEMS,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.mimetype, "application/pdf")
        self.assertTrue(respuesta.data.startswith(b"%PDF-"))

    def test_la_previa_no_escribe_nada_en_pacientes(self):
        """§6.2: un formulario abandonado no deja rastro ni quema un número."""
        self.cliente.post("/api/examenes/vista-previa", json={
            "paciente": {"nombre": "Juan Pérez"}, "items": ITEMS,
        })
        self.assertFalse(self.dir_pacientes.exists())

        con = self.conexion()
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM examenes").fetchone()[0], 0)
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM pacientes").fetchone()[0], 0)
            self.assertEqual(codigos.proximo_codigo_paciente(con), "EC-0001")
        finally:
            con.close()

    def test_la_previa_exige_al_menos_un_analisis(self):
        respuesta = self.cliente.post("/api/examenes/vista-previa", json={
            "paciente": {"nombre": "Juan Pérez"}, "items": [],
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("análisis", respuesta.get_json()["error"])


# --------------------------------------------------------------------------
# El alta: la orden, el código y el PDF en la carpeta del paciente
# --------------------------------------------------------------------------

class TestGuardarOrden(BaseApp):

    def test_el_alta_crea_el_paciente_y_le_da_su_codigo(self):
        datos = self.emitir()
        self.assertEqual(datos["codigo"], "EC-0001")
        self.assertEqual(datos["cantidad_items"], 2)

        con = self.conexion()
        try:
            fila = basedatos.obtener_paciente_por_codigo(con, "EC-0001")
            self.assertIsNotNone(fila)
            self.assertEqual(fila["nombre"], "Juan Pérez")
        finally:
            con.close()

    def test_el_pdf_cae_en_la_carpeta_del_paciente(self):
        datos = self.emitir()
        ruta = Path(datos["ruta_pdf"])
        self.assertTrue(ruta.is_file())
        self.assertEqual(ruta.name, "EXAMENES_EC-0001_2026-08-26.pdf")
        self.assertEqual(ruta.parent.name, "examenes")
        # La carpeta es la del paciente, con el código de llave (dec. 17).
        self.assertEqual(ruta.parent.parent.name, "EC-0001_Juan-Perez")
        self.assertEqual(ruta.parent.parent.parent.name, "pacientes")
        self.assertTrue(ruta.read_bytes().startswith(b"%PDF-"))

    def test_la_carpeta_del_paciente_trae_las_cinco_subcarpetas(self):
        """dec. 17 ampliada: `examenes\\` e `infiltraciones\\` se suman a las tres."""
        self.emitir()
        carpeta = next(self.dir_pacientes.iterdir())
        self.assertEqual(
            sorted(h.name for h in carpeta.iterdir() if h.is_dir()),
            sorted(rutas.SUBCARPETAS_PACIENTE),
        )

    def test_la_segunda_orden_del_mismo_dia_sale_v2(self):
        """§0.5: una orden emitida no se sobrescribe nunca."""
        primera = self.emitir()
        segunda = self.emitir()
        self.assertEqual(Path(primera["ruta_pdf"]).name,
                         "EXAMENES_EC-0001_2026-08-26.pdf")
        self.assertEqual(Path(segunda["ruta_pdf"]).name,
                         "EXAMENES_EC-0001_2026-08-26_v2.pdf")
        self.assertTrue(Path(primera["ruta_pdf"]).is_file())
        self.assertTrue(Path(segunda["ruta_pdf"]).is_file())
        # Mismo paciente, mismo código; lo que las separa es el id.
        self.assertEqual(primera["codigo"], segunda["codigo"])
        self.assertNotEqual(primera["id"], segunda["id"])

    def test_el_paciente_que_ya_estaba_no_gasta_un_numero_nuevo(self):
        self.emitir()
        self.emitir(nombre="María Gómez", cedula="V-777")
        vuelve = self.emitir()
        self.assertEqual(vuelve["codigo"], "EC-0001")

        con = self.conexion()
        try:
            self.assertEqual(codigos.proximo_codigo_paciente(con), "EC-0003")
        finally:
            con.close()

    def test_el_paciente_elegido_de_la_lista_conserva_su_codigo(self):
        """Con `paciente.id` —lo que manda el autocompletado— no se crea otro."""
        primera = self.emitir()
        con = self.conexion()
        try:
            paciente_id = int(basedatos.obtener_paciente_por_codigo(
                con, primera["codigo"])["id"])
        finally:
            con.close()

        respuesta = self.cliente.post("/api/examenes", json={
            "paciente": {"id": paciente_id, "nombre": "Juan Pérez"},
            "items": ITEMS,
        })
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        self.assertEqual(respuesta.get_json()["codigo"], "EC-0001")

    def test_los_renglones_se_guardan_literales_y_en_orden(self):
        """§5: lo que queda escrito es lo que se pidió ese día."""
        datos = self.emitir()
        con = self.conexion()
        try:
            items = basedatos.obtener_items_examen(con, datos["id"])
            self.assertEqual([i["examen"] for i in items],
                             [i["examen"] for i in ITEMS])
            self.assertEqual([i["orden"] for i in items], [1, 2])
            self.assertEqual(items[1]["indicaciones"], "Ayuno de 8 a 12 horas.")
        finally:
            con.close()

    def test_un_renglon_vacio_del_formulario_no_es_un_error(self):
        datos = self.emitir(items=[*ITEMS, {"examen": "", "muestra": "",
                                            "indicaciones": ""}])
        self.assertEqual(datos["cantidad_items"], 2)

    def test_sin_analisis_no_se_guarda_nada(self):
        respuesta = self.cliente.post("/api/examenes", json={
            "paciente": {"nombre": "Juan Pérez"}, "items": [],
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("análisis", respuesta.get_json()["error"])
        self.assertFalse(self.dir_pacientes.exists())

    def test_sin_nombre_de_paciente_no_se_guarda_nada(self):
        respuesta = self.cliente.post("/api/examenes", json={
            "paciente": {"nombre": "  "}, "items": ITEMS,
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("orden", respuesta.get_json()["error"])


# --------------------------------------------------------------------------
# El aprendizaje del catálogo (§8 y contrato §2)
# --------------------------------------------------------------------------

class TestAprendizaje(BaseApp):

    def test_un_analisis_que_no_esta_en_el_catalogo_se_aprende(self):
        """§0.6: el médico manda, el catálogo es un punto de partida.

        Escribe un estudio que no viene sembrado y a partir de ahí lo tiene en
        el autocompletado, con la muestra y la preparación que él le puso.
        """
        propio = {"examen": "Espirometría con broncodilatador",
                  "muestra": "", "indicaciones": "No fumar 24 horas antes."}
        self.emitir(items=[propio])

        resultados = self.cliente.get(
            "/api/sugerencias/analisis?q=espirometria").get_json()["resultados"]
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["texto"],
                         "Espirometría con broncodilatador")
        self.assertEqual(resultados[0]["preparacion"], "No fumar 24 horas antes.")
        self.assertEqual(resultados[0]["veces_usado"], 1)

    def test_usar_un_analisis_de_fabrica_le_suma_un_uso(self):
        self.emitir()
        self.emitir()
        resultados = self.cliente.get(
            "/api/sugerencias/analisis?q=hematologia completa"
        ).get_json()["resultados"]
        self.assertEqual(resultados[0]["veces_usado"], 2)

    def test_una_orden_que_no_se_guarda_no_ensucia_el_catalogo(self):
        """Si la orden no entró en la hoja, tampoco se aprendió nada."""
        respuesta = self.cliente.post("/api/examenes", json={
            "paciente": {"nombre": "Juan Pérez"},
            "items": [{"examen": "Estudio inventado que no entra",
                       "muestra": "", "indicaciones": "x" * 400},
                      *DEMASIADOS],
        })
        self.assertEqual(respuesta.status_code, 400)
        resultados = self.cliente.get(
            "/api/sugerencias/analisis?q=inventado").get_json()["resultados"]
        self.assertEqual(resultados, [])


# --------------------------------------------------------------------------
# Lo que NO entra en la hoja no llega a la base
# --------------------------------------------------------------------------

class TestNoEntraEnLaHoja(BaseApp):

    def test_una_orden_que_no_entra_no_deja_nada_escrito(self):
        """Se mide ANTES de tocar la base (§6.2).

        Es la razón entera del orden de operaciones: si midiéramos después de
        guardar, el médico quedaría con una orden en el historial que nunca
        pudo imprimir y con un número de paciente quemado.
        """
        respuesta = self.cliente.post("/api/examenes", json={
            "paciente": {"nombre": "Juan Pérez", "cedula": "V-1"},
            "items": DEMASIADOS,
        })
        self.assertEqual(respuesta.status_code, 400, respuesta.get_json())
        self.assertIn("no entra en la hoja", respuesta.get_json()["error"])

        con = self.conexion()
        try:
            for tabla in ("examenes", "examen_items", "pacientes"):
                self.assertEqual(
                    con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0],
                    0, f"quedaron filas en {tabla}")
            self.assertEqual(codigos.proximo_codigo_paciente(con), "EC-0001")
        finally:
            con.close()
        self.assertFalse(self.dir_pacientes.exists())

    def test_el_aviso_de_la_orden_no_es_el_del_recipe(self):
        """Los manejadores de error de los dos PDF no se cruzan.

        `pdf_examenes` tiene su propia familia de errores (cuelga de
        `ExamenesError`, no de `RecipeError`) justamente para esto: una orden
        de laboratorio que no entra no puede pedirle al médico que "saque un
        medicamento", que es una instrucción que ahí no puede seguir.

        La previa es el camino que llega hasta el compositor sin medir antes,
        así que es la que hace saltar de verdad el `ContenidoNoCabeError` de
        cada módulo.
        """
        de_examenes = self.cliente.post("/api/examenes/vista-previa", json={
            "paciente": {"nombre": "Juan Pérez"}, "items": DEMASIADOS,
        })
        self.assertEqual(de_examenes.status_code, 400)
        error_examenes = de_examenes.get_json()["error"]
        self.assertIn("La orden no entra en la hoja", error_examenes)
        self.assertIn("Sacá un análisis", error_examenes)
        self.assertNotIn("medicamento", error_examenes)

        de_recipe = self.cliente.post("/api/vista-previa", json={
            "paciente": {"nombre": "Juan Pérez"},
            "items": [{"medicamento": f"Medicamento número {i}",
                       "presentacion": "500 mg", "cantidad": "20 tabletas",
                       "dosis": "1 cada 8 horas",
                       "indicaciones": "Con las comidas, sin faltar un día."}
                      for i in range(30)],
        })
        self.assertEqual(de_recipe.status_code, 400)
        error_recipe = de_recipe.get_json()["error"]
        self.assertIn("El contenido no entra en la hoja", error_recipe)
        self.assertIn("Sacá un medicamento", error_recipe)
        self.assertNotIn("análisis", error_recipe)

    def test_el_logo_que_falta_lo_dice_cada_documento_con_su_nombre(self):
        """La otra mitad del cruce: `RecursoFaltanteError` son hermanas.

        `pdf_examenes.RecursoFaltanteError` hereda de la de `pdf_comun`, igual
        que la del récipe, pero ninguna está en el MRO de la otra: Flask
        encuentra el manejador exacto de cada una.
        """
        self.app.config["RUTA_LOGO_FORZADA"] = str(
            self.dir_datos / "no-esta-el-logo.png")

        de_examenes = self.cliente.post("/api/examenes/vista-previa", json={
            "paciente": {"nombre": "Juan Pérez"}, "items": ITEMS,
        })
        self.assertEqual(de_examenes.status_code, 500)
        self.assertIn("orden de exámenes", de_examenes.get_json()["error"])

        de_recipe = self.cliente.post("/api/vista-previa", json={
            "paciente": {"nombre": "Juan Pérez"},
            "items": [{"medicamento": "Amoxicilina", "presentacion": "500 mg",
                       "cantidad": "20 tabletas", "dosis": "1 cada 8 horas",
                       "indicaciones": ""}],
        })
        self.assertEqual(de_recipe.status_code, 500)
        self.assertIn("logo del récipe", de_recipe.get_json()["error"])


# --------------------------------------------------------------------------
# Historial y lista por paciente
# --------------------------------------------------------------------------

class TestHistorial(BaseApp):

    def test_busca_por_nombre_del_analisis(self):
        self.emitir()
        self.emitir(nombre="María Gómez", cedula="V-777", items=[
            {"examen": "Ecosonograma abdominal", "muestra": "",
             "indicaciones": "Ayuno de 8 horas."}])

        resultados = self.historial(q="ecosonograma")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["paciente_nombre"], "María Gómez")
        self.assertEqual(resultados[0]["analisis"], "Ecosonograma abdominal")

    def test_busca_por_codigo_y_trae_todas_las_del_paciente(self):
        self.emitir()
        self.emitir()
        self.emitir(nombre="María Gómez", cedula="V-777")

        resultados = self.historial(q="EC-0001")
        self.assertEqual(len(resultados), 2)
        self.assertEqual({r["codigo"] for r in resultados}, {"EC-0001"})

    def test_busca_por_nombre_del_paciente_sin_acentos(self):
        self.emitir()
        self.assertEqual(len(self.historial(q="perez")), 1)

    def test_el_rango_de_fechas_acota(self):
        self.emitir(fecha="2026-08-01")
        self.emitir(fecha="2026-08-26")
        self.emitir(fecha="2026-09-15")

        self.assertEqual(len(self.historial(desde="2026-08-01",
                                            hasta="2026-08-31")), 2)
        self.assertEqual(len(self.historial(desde="2026-09-01")), 1)
        self.assertEqual(len(self.historial(hasta="2026-08-01")), 1)

    def test_una_fecha_mal_escrita_se_explica(self):
        respuesta = self.cliente.get("/api/examenes?desde=26-08-2026")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("AAAA-MM-DD", respuesta.get_json()["error"])

    def test_las_ordenes_del_paciente_para_la_historia(self):
        datos = self.emitir()
        con = self.conexion()
        try:
            paciente_id = int(basedatos.obtener_paciente_por_codigo(
                con, datos["codigo"])["id"])
        finally:
            con.close()

        respuesta = self.cliente.get(f"/api/pacientes/{paciente_id}/examenes")
        self.assertEqual(respuesta.status_code, 200)
        ordenes = respuesta.get_json()["examenes"]
        self.assertEqual(len(ordenes), 1)
        self.assertEqual(ordenes[0]["id"], datos["id"])
        self.assertEqual(ordenes[0]["analisis"],
                         "Hematología completa, Glicemia en ayunas")
        self.assertTrue(ordenes[0]["tiene_pdf"])

    def test_un_paciente_que_no_esta_da_404(self):
        respuesta = self.cliente.get("/api/pacientes/999/examenes")
        self.assertEqual(respuesta.status_code, 404)


# --------------------------------------------------------------------------
# Reimprimir y anular
# --------------------------------------------------------------------------

class TestReimprimirYAnular(BaseApp):

    def test_el_pdf_que_se_devuelve_es_el_mismo_archivo(self):
        """§7-B: un documento emitido se reimprime, no se recompone."""
        datos = self.emitir()
        en_disco = Path(datos["ruta_pdf"]).read_bytes()

        respuesta = self.cliente.get(f"/api/examenes/{datos['id']}/pdf")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.mimetype, "application/pdf")
        self.assertEqual(respuesta.data, en_disco)

    def test_el_pdf_movido_se_explica_con_la_ruta_que_se_buscaba(self):
        datos = self.emitir()
        Path(datos["ruta_pdf"]).unlink()

        respuesta = self.cliente.get(f"/api/examenes/{datos['id']}/pdf")
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("EXAMENES_EC-0001", respuesta.get_json()["error"])

    def test_abrir_no_falla_con_el_visor_apagado(self):
        datos = self.emitir()
        respuesta = self.cliente.post(f"/api/examenes/{datos['id']}/abrir")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.get_json()["ok"])

    def test_una_orden_que_no_esta_da_404(self):
        respuesta = self.cliente.get("/api/examenes/999/pdf")
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("historial", respuesta.get_json()["error"])

    def test_anular_exige_motivo(self):
        datos = self.emitir()
        respuesta = self.cliente.post(f"/api/examenes/{datos['id']}/anular",
                                      json={"motivo": "   "})
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("motivo", respuesta.get_json()["error"])

    def test_anular_deja_el_motivo_y_no_borra_el_pdf(self):
        """§2.4: no se borra nada, nunca."""
        datos = self.emitir()
        respuesta = self.cliente.post(f"/api/examenes/{datos['id']}/anular",
                                      json={"motivo": "El paciente ya se los hizo"})
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        orden = respuesta.get_json()

        self.assertTrue(orden["anulado"])
        self.assertEqual(orden["motivo_anulacion"], "El paciente ya se los hizo")
        self.assertTrue(orden["fecha_anulacion"])
        self.assertTrue(Path(datos["ruta_pdf"]).is_file())
        self.assertTrue(orden["tiene_pdf"])

    def test_anular_dos_veces_no_pisa_el_motivo_original(self):
        datos = self.emitir()
        self.cliente.post(f"/api/examenes/{datos['id']}/anular",
                          json={"motivo": "El primero"})
        segunda = self.cliente.post(f"/api/examenes/{datos['id']}/anular",
                                    json={"motivo": "El segundo"})
        self.assertEqual(segunda.status_code, 400)
        self.assertIn("El primero", segunda.get_json()["error"])

        con = self.conexion()
        try:
            fila = basedatos.obtener_examen(con, datos["id"])
            self.assertEqual(fila["motivo_anulacion"], "El primero")
        finally:
            con.close()

    def test_la_orden_anulada_sigue_en_el_historial_marcada(self):
        datos = self.emitir()
        self.cliente.post(f"/api/examenes/{datos['id']}/anular",
                          json={"motivo": "Se repitió"})
        resultados = self.historial()
        self.assertEqual(len(resultados), 1)
        self.assertTrue(resultados[0]["anulado"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
