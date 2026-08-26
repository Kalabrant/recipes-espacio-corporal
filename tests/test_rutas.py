"""Tests de `rutas.py` — el flujo de récipes contra el código por paciente.

Lo que se prueba acá es la adaptación de la 2.0 (dec. 1 y 2): el récipe se
imprime con el código **del paciente**, así que dos récipes del mismo paciente
salen con el mismo número y lo que los separa es el `id`, la fecha y el sufijo
`_v2` del archivo. Y lo que NO cambió: la forma de las respuestas que la
interfaz ya consume, la vista previa que no quema números, la anulación y el
registro Excel.

Se usa el cliente de pruebas de Flask contra una carpeta de datos temporal, y
se generan PDF de verdad (el logo y las Lato salen del paquete): son unos
segundos, pero es la única manera de comprobar que el nombre de archivo
colisiona y versiona bien.

Solo `unittest` de la stdlib más lo que ya es dependencia (§3).
Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import unittest
import warnings
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from openpyxl import load_workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import basedatos  # noqa: E402
import codigos  # noqa: E402
import excel  # noqa: E402
import pdf_informe  # noqa: E402
import rutas  # noqa: E402


ITEMS = [
    {"medicamento": "Amoxicilina", "presentacion": "500 mg",
     "cantidad": "20 tabletas", "dosis": "1 cada 8 horas",
     "indicaciones": "Con las comidas"},
]

OTROS_ITEMS = [
    {"medicamento": "Losartán", "presentacion": "50 mg",
     "cantidad": "30 tabletas", "dosis": "1 diaria", "indicaciones": "En ayunas"},
]


class BaseApp(unittest.TestCase):
    """App real sobre una carpeta temporal, sin abrir nada en el escritorio."""

    def setUp(self) -> None:
        # fpdf subsetea las Lato con fontTools y le deja archivos sin cerrar al
        # recolector: son ResourceWarning de una dependencia, no de la app, y
        # llenarían la salida de la suite. Se silencian solo acá dentro.
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)

        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_rutas_"))
        # El borrado va como cleanup y no en `tearDown` por el orden: los
        # cleanups corren DESPUÉS de `tearDown` y en orden inverso, así que
        # registrándolo acá —lo primero— queda último, y para entonces ya se
        # cerraron las conexiones que abrieron las clases hijas. En Windows,
        # con `recipes.db` todavía tomado, el `rmtree` fallaba entero y
        # `ignore_errors` se lo tragaba en silencio: la suite dejaba una
        # carpeta de 200 KB en %TEMP% por cada test.
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
               fecha="2026-08-14", **extra):
        cuerpo = {
            "paciente": {"nombre": nombre, "cedula": cedula, "edad": 40},
            "items": items or ITEMS,
            "fecha_emision": fecha,
            **extra,
        }
        respuesta = self.cliente.post("/api/recipes", json=cuerpo)
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        return respuesta.get_json()

    def conexion(self):
        return basedatos.inicializar(self.dir_datos / "datos" / "recipes.db")

    def historial(self, q=""):
        respuesta = self.cliente.get(f"/api/recipes?q={q}")
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.get_json()


# --------------------------------------------------------------------------
# El código que se guarda y se imprime
# --------------------------------------------------------------------------

class TestCodigoDelPaciente(BaseApp):

    def test_el_primer_paciente_recibe_el_primer_codigo(self):
        datos = self.emitir()
        self.assertEqual(datos["codigo"], "EC-0001")

    def test_dos_recipes_del_mismo_paciente_llevan_el_mismo_codigo(self):
        """Dec. 2: el número es de la persona, no del papel."""
        primero = self.emitir()
        segundo = self.emitir(items=OTROS_ITEMS)
        self.assertEqual(primero["codigo"], "EC-0001")
        self.assertEqual(segundo["codigo"], "EC-0001")

        # Y sin embargo son dos récipes distintos, con su propio id.
        resultados = self.historial()["resultados"]
        self.assertEqual(len(resultados), 2)
        self.assertEqual({r["codigo"] for r in resultados}, {"EC-0001"})
        self.assertEqual(len({r["id"] for r in resultados}), 2)

    def test_el_segundo_paciente_recibe_el_segundo_codigo(self):
        self.emitir()
        otro = self.emitir(nombre="María Gómez", cedula="V-777")
        self.assertEqual(otro["codigo"], "EC-0002")

    def test_el_paciente_que_vuelve_no_gasta_un_numero_nuevo(self):
        self.emitir()
        self.emitir(nombre="María Gómez", cedula="V-777")
        vuelve = self.emitir()                       # el mismo Juan Pérez
        self.assertEqual(vuelve["codigo"], "EC-0001")

        con = self.conexion()
        try:
            self.assertEqual(codigos.proximo_codigo_paciente(con), "EC-0003")
        finally:
            con.close()

    def test_el_paciente_elegido_de_la_lista_conserva_su_codigo(self):
        """Con `paciente.id` —lo que manda el autocompletado— no se crea otro."""
        primero = self.emitir()
        con = self.conexion()
        try:
            fila = basedatos.obtener_paciente_por_codigo(con, primero["codigo"])
            paciente_id = int(fila["id"])
        finally:
            con.close()

        respuesta = self.cliente.post("/api/recipes", json={
            "paciente": {"id": paciente_id, "nombre": "Juan Pérez"},
            "items": OTROS_ITEMS,
            "fecha_emision": "2026-08-20",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["codigo"], "EC-0001")

    def test_el_codigo_guardado_es_el_que_devuelve_la_api(self):
        datos = self.emitir()
        con = self.conexion()
        try:
            filas = basedatos.listar_recipes_por_codigo(con, datos["codigo"])
            self.assertEqual(len(filas), 1)
            self.assertEqual(filas[0]["codigo"], datos["codigo"])
            # Las columnas de la numeración vieja quedan vacías (dec. 1).
            self.assertIsNone(filas[0]["anio"])
            self.assertIsNone(filas[0]["secuencial"])
        finally:
            con.close()

    def test_el_prefijo_configurado_manda(self):
        respuesta = self.cliente.post("/api/config", json={"prefijo": "esp"})
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        self.assertEqual(self.emitir()["codigo"], "ESP-0001")


# --------------------------------------------------------------------------
# El PDF en disco
# --------------------------------------------------------------------------

class TestArchivoPdf(BaseApp):

    def test_el_nombre_del_archivo_lleva_el_codigo_del_paciente(self):
        datos = self.emitir()
        ruta = Path(datos["ruta_pdf"])
        self.assertTrue(ruta.is_file())
        self.assertEqual(ruta.name, "EC-0001_Juan-Perez_2026-08-14.pdf")
        self.assertEqual(
            ruta.parent,
            self.dir_datos / "pacientes" / "EC-0001_Juan-Perez" / "recipes")

    def test_dos_recipes_el_mismo_dia_versionan_el_archivo(self):
        """La colisión ahora es normal: mismo paciente, mismo código, mismo día."""
        primero = self.emitir()
        segundo = self.emitir(items=OTROS_ITEMS)
        tercero = self.emitir(items=OTROS_ITEMS)

        self.assertEqual(Path(primero["ruta_pdf"]).name,
                         "EC-0001_Juan-Perez_2026-08-14.pdf")
        self.assertEqual(Path(segundo["ruta_pdf"]).name,
                         "EC-0001_Juan-Perez_2026-08-14_v2.pdf")
        self.assertEqual(Path(tercero["ruta_pdf"]).name,
                         "EC-0001_Juan-Perez_2026-08-14_v3.pdf")

        # Los tres siguen en disco: un récipe emitido no se pisa jamás (§4).
        for datos in (primero, segundo, tercero):
            self.assertTrue(Path(datos["ruta_pdf"]).is_file())

    def test_el_mismo_paciente_otro_dia_no_versiona(self):
        primero = self.emitir(fecha="2026-08-14")
        otro_dia = self.emitir(items=OTROS_ITEMS, fecha="2026-08-15")
        self.assertEqual(Path(primero["ruta_pdf"]).name,
                         "EC-0001_Juan-Perez_2026-08-14.pdf")
        self.assertEqual(Path(otro_dia["ruta_pdf"]).name,
                         "EC-0001_Juan-Perez_2026-08-15.pdf")

    def test_ruta_pdf_nueva_versiona_hasta_encontrar_lugar(self):
        """La función suelta, sin generar PDF: es la que decide el nombre."""
        carpeta = self.dir_datos / "pacientes" / "EC-0007_ANA" / "recipes"
        for esperado in ("EC-0007_ANA_2026-08-14.pdf",
                         "EC-0007_ANA_2026-08-14_v2.pdf",
                         "EC-0007_ANA_2026-08-14_v3.pdf"):
            ruta = rutas.ruta_pdf_nueva(self.dir_datos, "EC-0007", "ANA",
                                        "2026-08-14")
            self.assertEqual(ruta.name, esperado)
            self.assertEqual(ruta.parent, carpeta)
            ruta.write_bytes(b"%PDF-1.4")

    def test_el_pdf_guardado_se_devuelve_tal_cual(self):
        datos = self.emitir()
        recipe_id = self.historial()["resultados"][0]["id"]
        respuesta = self.cliente.get(f"/api/recipes/{recipe_id}/pdf")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, Path(datos["ruta_pdf"]).read_bytes())


# --------------------------------------------------------------------------
# Carpeta por paciente (dec. 17)
# --------------------------------------------------------------------------

class TestCarpetaPorPaciente(BaseApp):
    """`pacientes\\EC-NNNN_NOMBRE\\` con `recipes`, `informes` y `anexos`.

    Lo que se cuida acá: que la carpeta nazca sola con el primer récipe, que el
    nombre quede congelado (el código es la llave) y que lo emitido antes del
    cambio no se toque.
    """

    def raiz(self) -> Path:
        return self.dir_datos / "pacientes"

    def test_el_primer_recipe_crea_la_carpeta_con_las_tres_subcarpetas(self):
        self.emitir()
        carpeta = self.raiz() / "EC-0001_Juan-Perez"
        self.assertTrue(carpeta.is_dir())
        for sub in ("recipes", "informes", "anexos"):
            self.assertTrue((carpeta / sub).is_dir(), sub)

    def test_el_pdf_cae_adentro_de_recipes(self):
        datos = self.emitir()
        ruta = Path(datos["ruta_pdf"])
        self.assertEqual(ruta.parent,
                         self.raiz() / "EC-0001_Juan-Perez" / "recipes")
        self.assertTrue(ruta.is_file())

    def test_cada_paciente_tiene_la_suya(self):
        self.emitir()
        self.emitir(nombre="María Gómez", cedula="V-777")
        self.assertEqual(
            sorted(c.name for c in self.raiz().iterdir() if c.is_dir()),
            ["EC-0001_Juan-Perez", "EC-0002_Maria-Gomez"])

    def test_las_versiones_v2_quedan_en_la_carpeta_del_paciente(self):
        """Dos récipes el mismo día: el `_v2` no se escapa a otro lado."""
        primero = self.emitir()
        segundo = self.emitir(items=OTROS_ITEMS)
        carpeta = self.raiz() / "EC-0001_Juan-Perez" / "recipes"

        self.assertEqual(Path(primero["ruta_pdf"]).parent, carpeta)
        self.assertEqual(Path(segundo["ruta_pdf"]).parent, carpeta)
        self.assertEqual(
            sorted(p.name for p in carpeta.glob("*.pdf")),
            ["EC-0001_Juan-Perez_2026-08-14.pdf",
             "EC-0001_Juan-Perez_2026-08-14_v2.pdf"])

    def test_corregir_el_nombre_no_crea_una_carpeta_nueva(self):
        """Dec. 17: el nombre se congela; la llave es el código.

        El médico había escrito mal el apellido y lo corrige al segundo récipe.
        El paciente es el mismo (se elige de la lista, con su `id`), así que
        todo tiene que seguir cayendo en la carpeta de siempre.
        """
        self.emitir(nombre="Juan Perze")
        con = self.conexion()
        try:
            paciente_id = int(
                basedatos.obtener_paciente_por_codigo(con, "EC-0001")["id"])
        finally:
            con.close()

        respuesta = self.cliente.post("/api/recipes", json={
            "paciente": {"id": paciente_id, "nombre": "Juan Pérez"},
            "items": OTROS_ITEMS,
            "fecha_emision": "2026-08-20",
        })
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())

        carpetas = sorted(c.name for c in self.raiz().iterdir() if c.is_dir())
        self.assertEqual(carpetas, ["EC-0001_Juan-Perze"])
        # El PDF nuevo cae en la carpeta vieja, pero el archivo guarda el
        # nombre corregido: la carpeta agrupa, el archivo testimonia.
        nuevo = Path(respuesta.get_json()["ruta_pdf"])
        self.assertEqual(nuevo.parent,
                         self.raiz() / "EC-0001_Juan-Perze" / "recipes")
        self.assertEqual(nuevo.name, "EC-0001_Juan-Perez_2026-08-20.pdf")

    def test_carpeta_paciente_es_idempotente_y_congela(self):
        """La función suelta, sin pasar por la app."""
        primera = rutas.carpeta_paciente(self.dir_datos, "EC-0042", "Ana Ruiz")
        self.assertEqual(primera.name, "EC-0042_Ana-Ruiz")

        repetida = rutas.carpeta_paciente(self.dir_datos, "EC-0042", "Ana Ruiz")
        self.assertEqual(repetida, primera)

        renombrada = rutas.carpeta_paciente(self.dir_datos, "EC-0042",
                                            "Ana Ruiz de Pérez")
        self.assertEqual(renombrada, primera)
        self.assertEqual([c.name for c in self.raiz().iterdir() if c.is_dir()],
                         ["EC-0042_Ana-Ruiz"])

    def test_el_nombre_de_la_carpeta_se_sanitiza(self):
        """Sin tildes ni caracteres que Windows no admite en una carpeta."""
        carpeta = rutas.carpeta_paciente(self.dir_datos, "EC-0009",
                                         'Núñez/Martín <"raro">')
        self.assertTrue(carpeta.is_dir())
        self.assertEqual(carpeta.name, "EC-0009_Nunez-Martin-raro")

    def test_un_recipe_viejo_en_pdf_del_anio_se_sigue_sirviendo(self):
        """Lo emitido antes del cambio no se mueve ni se recalcula (dec. 17).

        Se simula la 1.x: el PDF vive en `pdf\\2026\\` y la base tiene esa
        ruta. Reimprimir tiene que entregar ESE archivo, byte por byte.
        """
        datos = self.emitir()
        recipe_id = self.historial()["resultados"][0]["id"]

        # El archivo se mueve a donde lo habría dejado la 1.x y la base apunta
        # ahí, como quedó en las máquinas que ya venían emitiendo.
        actual = Path(datos["ruta_pdf"])
        contenido = actual.read_bytes()
        viejo = self.dir_datos / "pdf" / "2026" / "EC-2026-0001_Juan-Perez.pdf"
        viejo.parent.mkdir(parents=True, exist_ok=True)
        viejo.write_bytes(contenido)
        actual.unlink()

        con = self.conexion()
        try:
            with basedatos.transaccion(con):
                basedatos.guardar_ruta_pdf(con, recipe_id, str(viejo))
        finally:
            con.close()

        respuesta = self.cliente.get(f"/api/recipes/{recipe_id}/pdf")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, contenido)
        # Y sigue donde estaba: nadie lo movió a `pacientes\`.
        self.assertTrue(viejo.is_file())


# --------------------------------------------------------------------------
# Vista previa: muestra el código real, pero no lo asigna
# --------------------------------------------------------------------------

class TestVistaPrevia(BaseApp):

    def previa(self, paciente):
        respuesta = self.cliente.post("/api/vista-previa", json={
            "paciente": paciente, "items": ITEMS, "fecha_emision": "2026-08-14",
        })
        self.assertEqual(respuesta.status_code, 200, respuesta.data[:200])
        return respuesta

    def test_paciente_nuevo_ve_el_relleno_y_no_quema_numero(self):
        con = self.conexion()
        try:
            self.assertEqual(rutas.codigo_para_previa(
                con, {"id": None, "nombre": "Nadie Todavía", "cedula": ""}),
                "EC-____")
            antes = codigos.proximo_codigo_paciente(con)
        finally:
            con.close()

        self.previa({"nombre": "Nadie Todavía", "cedula": ""})

        con = self.conexion()
        try:
            self.assertEqual(codigos.proximo_codigo_paciente(con), antes)
            self.assertEqual(
                con.execute("SELECT COUNT(*) AS n FROM pacientes").fetchone()["n"], 0)
        finally:
            con.close()

    def test_el_relleno_tiene_un_solo_grupo(self):
        """Dec. 1: el código del paciente no lleva año, el relleno tampoco."""
        con = self.conexion()
        try:
            self.assertEqual(rutas.codigo_relleno(con), "EC-____")
        finally:
            con.close()

    def test_paciente_conocido_ve_su_codigo_de_verdad(self):
        self.emitir()
        con = self.conexion()
        try:
            fila = basedatos.obtener_paciente_por_codigo(con, "EC-0001")
            paciente_id = int(fila["id"])
            # Por id (elegido de la lista), por cédula y por nombre exacto:
            # los tres caminos que usa el alta al guardar.
            self.assertEqual(rutas.codigo_para_previa(
                con, {"id": paciente_id, "nombre": "Juan Pérez"}), "EC-0001")
            self.assertEqual(rutas.codigo_para_previa(
                con, {"id": None, "nombre": "Otro Nombre", "cedula": "V-12345678"}),
                "EC-0001")
            self.assertEqual(rutas.codigo_para_previa(
                con, {"id": None, "nombre": "juan perez", "cedula": ""}), "EC-0001")
        finally:
            con.close()

    def test_la_previa_de_un_conocido_tampoco_escribe(self):
        self.emitir()
        con = self.conexion()
        try:
            antes = codigos.proximo_codigo_paciente(con)
            atenciones = con.execute(
                "SELECT veces_atendido AS v FROM pacientes").fetchone()["v"]
        finally:
            con.close()

        self.previa({"nombre": "Juan Pérez", "cedula": "V-12345678"})

        con = self.conexion()
        try:
            self.assertEqual(codigos.proximo_codigo_paciente(con), antes)
            self.assertEqual(con.execute(
                "SELECT veces_atendido AS v FROM pacientes").fetchone()["v"],
                atenciones)
            self.assertEqual(con.execute(
                "SELECT COUNT(*) AS n FROM recipes").fetchone()["n"], 1)
        finally:
            con.close()

    def test_la_previa_no_deja_pdf_en_la_carpeta(self):
        self.previa({"nombre": "Nadie Todavía", "cedula": ""})
        self.assertEqual(list((self.dir_datos / "pdf").rglob("*.pdf")), [])


# --------------------------------------------------------------------------
# Historial: mismo contrato, código de paciente adentro
# --------------------------------------------------------------------------

class TestHistorial(BaseApp):

    def test_la_forma_de_cada_resultado_no_cambio(self):
        self.emitir(diagnostico="Faringitis aguda")
        resultado = self.historial()["resultados"][0]
        self.assertEqual(set(resultado), {
            "id", "codigo", "fecha_emision", "paciente_nombre", "cedula",
            "diagnostico", "medicamentos", "anulado", "motivo_anulacion",
            "fecha_anulacion",
        })
        self.assertEqual(resultado["codigo"], "EC-0001")
        self.assertEqual(resultado["paciente_nombre"], "Juan Pérez")
        self.assertEqual(resultado["medicamentos"], "Amoxicilina")
        self.assertFalse(resultado["anulado"])

    def test_buscar_por_codigo_trae_todos_los_recipes_del_paciente(self):
        self.emitir(fecha="2026-08-14")
        self.emitir(items=OTROS_ITEMS, fecha="2026-08-15")
        self.emitir(nombre="María Gómez", cedula="V-777", fecha="2026-08-16")

        resultados = self.historial("EC-0001")["resultados"]
        self.assertEqual(len(resultados), 2)
        self.assertEqual([r["fecha_emision"][:10] for r in resultados],
                         ["2026-08-15", "2026-08-14"])   # más nuevo primero
        self.assertEqual({r["paciente_nombre"] for r in resultados}, {"Juan Pérez"})

    def test_cada_recipe_se_abre_y_se_anula_por_su_id(self):
        self.emitir(fecha="2026-08-14")
        self.emitir(items=OTROS_ITEMS, fecha="2026-08-15")
        resultados = self.historial()["resultados"]
        nuevo, viejo = resultados[0], resultados[1]

        respuesta = self.cliente.post(f"/api/recipes/{viejo['id']}/anular",
                                      json={"motivo": "Error en la dosis"})
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        anulado = respuesta.get_json()
        self.assertTrue(anulado["anulado"])
        self.assertEqual(anulado["codigo"], "EC-0001")
        self.assertEqual(anulado["motivo_anulacion"], "Error en la dosis")

        # El otro récipe del MISMO paciente sigue vivo: se anuló uno, no un código.
        despues = {r["id"]: r for r in self.historial()["resultados"]}
        self.assertTrue(despues[viejo["id"]]["anulado"])
        self.assertFalse(despues[nuevo["id"]]["anulado"])

    def test_anular_dos_veces_avisa_y_no_pisa_el_motivo(self):
        self.emitir()
        recipe_id = self.historial()["resultados"][0]["id"]
        self.cliente.post(f"/api/recipes/{recipe_id}/anular",
                          json={"motivo": "Error en la dosis"})
        segunda = self.cliente.post(f"/api/recipes/{recipe_id}/anular",
                                    json={"motivo": "Otra cosa"})
        self.assertEqual(segunda.status_code, 400)
        self.assertIn("EC-0001", segunda.get_json()["error"])

        resultado = self.historial()["resultados"][0]
        self.assertEqual(resultado["motivo_anulacion"], "Error en la dosis")


# --------------------------------------------------------------------------
# El registro Excel que escribe la ruta
# --------------------------------------------------------------------------

class TestRegistroExcel(BaseApp):

    def test_guardar_deja_el_registro_con_las_columnas_nuevas(self):
        primero = self.emitir(fecha="2026-08-14")
        self.emitir(items=OTROS_ITEMS, fecha="2026-08-15")

        ruta = excel.ruta_registro(self.dir_datos)
        self.assertTrue(ruta.is_file())
        libro = load_workbook(ruta)
        try:
            hoja = libro[excel.HOJA_RECIPES]
            self.assertEqual(hoja["A1"].value, "Código de paciente")
            self.assertEqual(hoja["B1"].value, "N.º interno")
            self.assertEqual(hoja.max_row, 3)
            # Un solo código para las dos filas, dos N.º internos distintos.
            self.assertEqual({hoja["A2"].value, hoja["A3"].value}, {"EC-0001"})
            self.assertNotEqual(hoja["B2"].value, hoja["B3"].value)
            # La ruta del PDF es la que devolvió la API.
            rutas_pdf = {hoja["K2"].value, hoja["K3"].value}
            self.assertIn(primero["ruta_pdf"], rutas_pdf)

            hoja_m = libro[excel.HOJA_MEDICAMENTOS]
            self.assertEqual(hoja_m["A1"].value, "Código de paciente")
            self.assertEqual(hoja_m["B1"].value, "N.º interno")
            self.assertEqual({f[0] for f in
                              hoja_m.iter_rows(min_row=2, values_only=True)},
                             {"EC-0001"})
        finally:
            libro.close()

    def test_anular_actualiza_el_registro(self):
        self.emitir()
        recipe_id = self.historial()["resultados"][0]["id"]
        self.cliente.post(f"/api/recipes/{recipe_id}/anular",
                          json={"motivo": "Paciente equivocado"})

        libro = load_workbook(excel.ruta_registro(self.dir_datos))
        try:
            hoja = libro[excel.HOJA_RECIPES]
            self.assertEqual(hoja["I2"].value, excel.ESTADO_ANULADO)
            self.assertEqual(hoja["J2"].value, "Paciente equivocado")
        finally:
            libro.close()


# --------------------------------------------------------------------------
# Informes (dec. 9 a 12) y la historia imprimible (dec. 14)
# --------------------------------------------------------------------------

class BaseInformes(BaseApp):
    """Un paciente con código, listo para que le emitan un informe."""

    CLINICO = {
        "tipo": "clinico",
        "cuerpo": ("Se trata de paciente masculino de 40 años de edad, quien "
                   "consulta por presentar dolor lumbar."),
        "diagnostico": "Lumbalgia mecánica",
        "tratamiento": "Reposo relativo y analgesia",
    }

    def setUp(self) -> None:
        super().setUp()
        self.emitir()                            # da de alta al paciente y su código
        con = self.conexion()
        self.addCleanup(con.close)
        self.paciente_id = int(
            basedatos.obtener_paciente_por_codigo(con, "EC-0001")["id"])

    def emitir_informe(self, **extra):
        cuerpo = {"paciente_id": self.paciente_id, **self.CLINICO, **extra}
        return self.cliente.post("/api/informes", json=cuerpo)

    def carpeta_del_paciente(self) -> Path:
        return self.dir_datos / "pacientes" / "EC-0001_Juan-Perez"

    def informes_en_disco(self) -> list[Path]:
        return sorted((self.carpeta_del_paciente() / "informes").glob("*.pdf"))


class TestInformes(BaseInformes):

    def test_el_informe_cae_en_la_carpeta_del_paciente(self):
        """Dec. 17: todo lo nuevo de un paciente va a su carpeta."""
        datos = self.emitir_informe(fecha="2026-08-18")
        self.assertEqual(datos.status_code, 200, datos.get_json())
        cuerpo = datos.get_json()
        ruta = Path(cuerpo["ruta_pdf"])
        self.assertTrue(ruta.is_file())
        self.assertEqual(
            ruta, self.carpeta_del_paciente() / "informes"
            / "INFORME_EC-0001_2026-08-18.pdf")
        self.assertEqual("EC-0001", cuerpo["codigo"])

    def test_dos_informes_el_mismo_dia_no_se_pisan(self):
        primero = Path(self.emitir_informe(fecha="2026-08-18")
                       .get_json()["ruta_pdf"])
        segundo = Path(self.emitir_informe(fecha="2026-08-18")
                       .get_json()["ruta_pdf"])
        self.assertNotEqual(primero, segundo)
        self.assertTrue(segundo.name.endswith("_v2.pdf"))
        self.assertTrue(primero.is_file() and segundo.is_file())

    def test_queda_guardado_en_la_historia_con_su_ruta(self):
        """Dec. 10: los informes SE GUARDAN, como los récipes."""
        respuesta = self.emitir_informe()
        informe_id = respuesta.get_json()["id"]
        con = self.conexion()
        try:
            fila = basedatos.obtener_informe(con, informe_id)
            self.assertEqual("clinico", fila["tipo"])
            self.assertEqual("EC-0001", fila["codigo_paciente"])
            self.assertEqual("Lumbalgia mecánica", fila["diagnostico"])
            self.assertEqual(respuesta.get_json()["ruta_pdf"], fila["ruta_pdf"])
            self.assertEqual(0, fila["anulado"])
        finally:
            con.close()

    def test_usa_los_datos_del_medico_de_configuracion(self):
        """Dec. 9: precargados, pero es Configuración la que manda."""
        self.cliente.post("/api/config", json={"especialidad": "Endocrinología"})
        respuesta = self.emitir_informe()
        con = self.conexion()
        try:
            fila = basedatos.obtener_informe(con, respuesta.get_json()["id"])
            self.assertEqual("Endocrinología", fila["especialidad"])
            self.assertEqual("Maracaibo", fila["ciudad"])
        finally:
            con.close()

    def test_informe_de_aseguradora(self):
        respuesta = self.emitir_informe(
            tipo="aseguradora", cuerpo="", diagnostico="Obesidad grado II",
            tratamiento="", numero_poliza="AXA-99", antecedentes="Dislipidemia",
            motivo_consulta="Aumento de peso", evolucion="Se indican exámenes")
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        cuerpo = respuesta.get_json()
        self.assertEqual("aseguradora", cuerpo["tipo"])
        self.assertTrue(Path(cuerpo["ruta_pdf"]).is_file())

    def test_un_informe_vacio_no_se_emite(self):
        respuesta = self.emitir_informe(cuerpo="", diagnostico="",
                                        tratamiento="")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("vacío", respuesta.get_json()["error"])
        self.assertEqual([], self.informes_en_disco())

    def test_el_aviso_de_vacio_nombra_campos_que_estan_en_ese_formulario(self):
        """El formulario de la aseguradora no tiene ningún campo «cuerpo».

        Mandar a escribirlo ahí es mandar a buscar algo que no está en la
        pantalla; el aviso nombra los campos del tipo que se está emitiendo.
        """
        clinico = self.emitir_informe(cuerpo="", diagnostico="", tratamiento="")
        self.assertIn("el cuerpo o el diagnóstico",
                      clinico.get_json()["error"])

        seguro = self.cliente.post("/api/informes", json={
            "paciente_id": self.paciente_id, "tipo": "aseguradora"})
        self.assertEqual(seguro.status_code, 400)
        mensaje = seguro.get_json()["error"]
        self.assertIn("el motivo de la consulta o el diagnóstico", mensaje)
        self.assertNotIn("cuerpo", mensaje)

    def test_un_informe_con_solo_el_cuerpo_se_emite(self):
        """Dec. 10: el informe es texto del médico, no un formulario obligatorio.

        Sin diagnóstico ni tratamiento el rótulo directamente no se imprime,
        que es lo que hace el `.docx` cuando el médico no llena esa parte.
        """
        respuesta = self.emitir_informe(diagnostico="", tratamiento="")
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        con = self.conexion()
        try:
            fila = basedatos.obtener_informe(
                con, respuesta.get_json()["id"])
            self.assertEqual("", fila["diagnostico"] or "")
        finally:
            con.close()

    def test_tipo_desconocido_explica_cuales_hay(self):
        respuesta = self.emitir_informe(tipo="constancia")
        self.assertEqual(respuesta.status_code, 400)
        mensaje = respuesta.get_json()["error"]
        self.assertIn("Informe médico", mensaje)
        self.assertIn("aseguradora", mensaje)

    def test_sin_paciente_pide_elegir_uno(self):
        respuesta = self.cliente.post("/api/informes", json=dict(self.CLINICO))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("Elegí a qué paciente", respuesta.get_json()["error"])

    def test_paciente_inexistente_da_404_con_instruccion(self):
        respuesta = self.emitir_informe(paciente_id=9999)
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("Volvé a buscarlo", respuesta.get_json()["error"])

    def test_un_anexo_de_otro_paciente_no_se_puede_marcar(self):
        con = self.conexion()
        try:
            otro = basedatos.crear_paciente(con, "Ana Gómez")
            anexo_id = basedatos.crear_anexo(
                con, otro, "pacientes/EC-0002_Ana-Gomez/anexos/x.jpg",
                "a" * 64, "2026-08-14")
            con.commit()
        finally:
            con.close()
        respuesta = self.emitir_informe(anexos=[anexo_id])
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("ya no está en la historia de este paciente",
                      respuesta.get_json()["error"])

    def test_un_anexo_cuyo_archivo_falta_frena_la_emision(self):
        """Un informe sin el anexo que el médico creía mandar es peor que nada."""
        con = self.conexion()
        try:
            anexo_id = basedatos.crear_anexo(
                con, self.paciente_id,
                "pacientes/EC-0001_Juan-Perez/anexos/borrada.jpg",
                "b" * 64, "2026-08-14")
            con.commit()
        finally:
            con.close()
        respuesta = self.emitir_informe(anexos=[anexo_id])
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("borrada.jpg", respuesta.get_json()["error"])
        self.assertEqual([], self.informes_en_disco())

    def test_un_anexo_real_sale_como_pagina_del_informe(self):
        origen = RAIZ / "referencias" / "medicion-whatsapp-ejemplo.jpeg"
        destino = self.carpeta_del_paciente() / "anexos" / "2026-08-14_medicion_01.jpeg"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, destino)
        con = self.conexion()
        try:
            anexo_id = basedatos.crear_anexo(
                con, self.paciente_id,
                str(destino.relative_to(self.dir_datos)).replace("\\", "/"),
                "c" * 64, "2026-08-14", tipo="Medición de composición corporal")
            con.commit()
        finally:
            con.close()
        respuesta = self.emitir_informe(anexos=[anexo_id])
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        pdf = Path(respuesta.get_json()["ruta_pdf"]).read_bytes()
        self.assertIn(b"/Count 2", pdf, "el informe tiene que tener 2 páginas")
        # y el anexo quedó vinculado, para poder reimprimir lo mismo
        con = self.conexion()
        try:
            vinculados = basedatos.listar_anexos_de_informe(
                con, respuesta.get_json()["id"])
            self.assertEqual([anexo_id], [int(f["id"]) for f in vinculados])
        finally:
            con.close()


class _EspiaInforme(pdf_informe._Informe):
    """El compositor real, anotando qué texto cayó en qué página.

    Es el mismo truco de `test_pdf_informe.py`: la única forma honesta de leer
    lo que dice el PDF sin meter un lector de PDF como dependencia (§3).
    """

    trazos: list[tuple[int, str]] = []

    def _texto(self, x, base_y, texto, estilo, pt, color):
        _EspiaInforme.trazos.append((self.page, texto))
        return super()._texto(x, base_y, texto, estilo, pt, color)


class BaseInformesConAnexos(BaseInformes):
    """`BaseInformes` más la maquinaria para anexar imágenes de verdad."""

    MEDICION = RAIZ / "referencias" / "medicion-whatsapp-ejemplo.jpeg"

    def anexar(self, nombre: str, sha: str, paciente_id: int | None = None,
               carpeta: Path | None = None, tipo: str = "medicion",
               fecha: str = "2026-08-14") -> int:
        """Copia la imagen de ejemplo a la carpeta del paciente y la registra."""
        carpeta = (carpeta or self.carpeta_del_paciente()) / "anexos"
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / nombre
        shutil.copyfile(self.MEDICION, destino)
        con = self.conexion()
        try:
            anexo_id = basedatos.crear_anexo(
                con, paciente_id or self.paciente_id,
                str(destino.relative_to(self.dir_datos)).replace("\\", "/"),
                sha, fecha, tipo=tipo)
            con.commit()
        finally:
            con.close()
        return int(anexo_id)

    def espiar_el_pdf(self) -> list[tuple[int, str]]:
        """Deja `_EspiaInforme` puesto para el próximo informe que se emita."""
        real = pdf_informe._Informe
        self.addCleanup(setattr, pdf_informe, "_Informe", real)
        _EspiaInforme.trazos = []
        pdf_informe._Informe = _EspiaInforme      # type: ignore[misc]
        return _EspiaInforme.trazos


class TestAnexosDelInforme(BaseInformesConAnexos):
    """Dec. 12: la página de anexo es opt-in y sale rotulada."""

    def test_dos_anexos_dan_dos_paginas_extra_rotuladas(self):
        primero = self.anexar("2026-08-14_medicion_01.jpeg", "a" * 64)
        segundo = self.anexar("2026-08-16_medicion_02.jpeg", "b" * 64,
                              fecha="2026-08-16")
        trazos = self.espiar_el_pdf()

        respuesta = self.emitir_informe(anexo_ids=[primero, segundo])
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        cuerpo = respuesta.get_json()
        self.assertEqual(2, cuerpo["cantidad_anexos"])

        pdf = Path(cuerpo["ruta_pdf"]).read_bytes()
        self.assertIn(b"/Count 3", pdf, "el informe más dos páginas de anexo")

        pies = [texto for _, texto in trazos if texto.startswith("Anexo ")]
        self.assertEqual(
            ["Anexo 1 — Medición de composición corporal, 14/08/2026",
             "Anexo 2 — Medición de composición corporal, 16/08/2026"],
            pies)
        # y cada rótulo cayó en su propia página, en el orden en que se marcaron
        self.assertEqual([2, 3], [pagina for pagina, texto in trazos
                                  if texto.startswith("Anexo ")])

    def test_los_anexos_quedan_vinculados_para_reimprimir_lo_mismo(self):
        primero = self.anexar("2026-08-14_medicion_01.jpeg", "a" * 64)
        segundo = self.anexar("2026-08-16_medicion_02.jpeg", "b" * 64)
        informe_id = self.emitir_informe(
            anexo_ids=[primero, segundo]).get_json()["id"]
        con = self.conexion()
        try:
            vinculados = basedatos.listar_anexos_de_informe(con, informe_id)
            self.assertEqual([primero, segundo],
                             [int(f["id"]) for f in vinculados])
        finally:
            con.close()

    def test_un_anexo_de_otro_paciente_da_400(self):
        con = self.conexion()
        try:
            otro = basedatos.crear_paciente(con, "Ana Gómez", cedula="V-999")
            con.commit()
        finally:
            con.close()
        ajeno = self.anexar(
            "2026-08-14_medicion_01.jpeg", "c" * 64, paciente_id=otro,
            carpeta=self.dir_datos / "pacientes" / "EC-0002_Ana-Gomez")

        respuesta = self.emitir_informe(anexo_ids=[ajeno])
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("ya no está en la historia de este paciente",
                      respuesta.get_json()["error"])
        self.assertEqual([], self.informes_en_disco())

    def test_un_anexo_pdf_se_frena_antes_de_guardar_el_informe(self):
        """Dec. 11 acepta laboratorios en PDF; dec. 12 no los pega como página.

        Lo que se revisa acá es *dónde* se corta. `pdf_informe` también lo
        rechaza, pero el PDF se dibuja **después** de guardar el informe en la
        base —a propósito, para que un fallo del dibujo no pierda el texto—, así
        que cortar allá dejaba un 500 y una tarjeta «informe sin PDF» en la
        historia por haber tildado un archivo que no iba. La pantalla apaga esa
        casilla, pero el pedido llega igual desde una pantalla vieja.
        """
        carpeta = self.carpeta_del_paciente() / "anexos"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "2026-08-10_laboratorio_01.pdf").write_bytes(b"%PDF-1.7\n")
        con = self.conexion()
        try:
            anexo_id = basedatos.crear_anexo(
                con, self.paciente_id,
                "pacientes/EC-0001_Juan-Perez/anexos/2026-08-10_laboratorio_01.pdf",
                "e" * 64, "2026-08-10", tipo="laboratorio")
            antes = len(basedatos.listar_informes(con, self.paciente_id))
            con.commit()
        finally:
            con.close()

        respuesta = self.emitir_informe(anexo_ids=[anexo_id])
        self.assertEqual(respuesta.status_code, 400, respuesta.get_json())
        mensaje = respuesta.get_json()["error"]
        self.assertIn("2026-08-10_laboratorio_01.pdf", mensaje)
        self.assertIn("aparte", mensaje)

        self.assertEqual([], self.informes_en_disco())
        con = self.conexion()
        try:
            self.assertEqual(
                antes, len(basedatos.listar_informes(con, self.paciente_id)),
                "un formulario mal llenado no puede dejar un informe fantasma")
        finally:
            con.close()

    def test_anexo_ids_y_anexos_son_el_mismo_campo(self):
        """La E2 los mandaba como `anexos`; el contrato nuevo, `anexo_ids`."""
        viejo = self.anexar("2026-08-14_medicion_01.jpeg", "d" * 64)
        respuesta = self.emitir_informe(anexos=[viejo])
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        self.assertEqual(1, respuesta.get_json()["cantidad_anexos"])

    def test_sin_anexos_el_informe_es_de_una_sola_pagina(self):
        cuerpo = self.emitir_informe().get_json()
        self.assertEqual(0, cuerpo["cantidad_anexos"])
        self.assertIn(b"/Count 1", Path(cuerpo["ruta_pdf"]).read_bytes())


class TestListaDeInformes(BaseInformesConAnexos):
    """`GET /api/pacientes/<id>/informes`: lo que muestra la historia."""

    def lista(self, paciente_id=None):
        return self.cliente.get(
            f"/api/pacientes/{paciente_id or self.paciente_id}/informes")

    def test_un_paciente_sin_informes_devuelve_la_lista_vacia(self):
        respuesta = self.lista()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual({"informes": []}, respuesta.get_json())

    def test_trae_los_informes_del_mas_nuevo_al_mas_viejo(self):
        self.emitir_informe(fecha="2026-08-10", diagnostico="Lumbalgia")
        self.emitir_informe(fecha="2026-08-18", diagnostico="Dislipidemia",
                            tipo="aseguradora", cuerpo="",
                            motivo_consulta="Control")
        informes = self.lista().get_json()["informes"]
        self.assertEqual(["2026-08-18", "2026-08-10"],
                         [i["fecha"] for i in informes])
        self.assertEqual(["aseguradora", "clinico"],
                         [i["tipo"] for i in informes])
        self.assertEqual(["Dislipidemia", "Lumbalgia"],
                         [i["diagnostico"] for i in informes])

    def test_cada_renglon_dice_si_tiene_pdf_y_cuantos_anexos(self):
        anexo_id = self.anexar("2026-08-14_medicion_01.jpeg", "a" * 64)
        self.emitir_informe(anexo_ids=[anexo_id])
        renglon = self.lista().get_json()["informes"][0]
        self.assertTrue(renglon["tiene_pdf"])
        self.assertEqual(1, renglon["cantidad_anexos"])
        self.assertFalse(renglon["anulado"])
        self.assertEqual("", renglon["motivo_anulacion"])

    def test_si_el_pdf_no_esta_el_renglon_lo_dice(self):
        """`tiene_pdf` mira el disco: la pantalla no ofrece reimprimir la nada."""
        ruta = Path(self.emitir_informe().get_json()["ruta_pdf"])
        ruta.unlink()
        self.assertFalse(self.lista().get_json()["informes"][0]["tiene_pdf"])

    def test_el_anulado_sigue_en_la_lista_marcado(self):
        informe_id = self.emitir_informe().get_json()["id"]
        self.cliente.post(f"/api/informes/{informe_id}/anular",
                          json={"motivo": "Paciente equivocado"})
        renglon = self.lista().get_json()["informes"][0]
        self.assertTrue(renglon["anulado"])
        self.assertEqual("Paciente equivocado", renglon["motivo_anulacion"])

    def test_los_informes_de_otro_paciente_no_se_mezclan(self):
        self.emitir_informe()
        con = self.conexion()
        try:
            otro = basedatos.crear_paciente(con, "Ana Gómez", cedula="V-999")
            con.commit()
        finally:
            con.close()
        self.assertEqual([], self.lista(otro).get_json()["informes"])

    def test_paciente_inexistente_da_404_con_instruccion(self):
        respuesta = self.lista(9999)
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("Volvé a buscarlo", respuesta.get_json()["error"])


class TestReimpresionDeInformes(BaseInformes):
    """El PDF que se entrega es el que se emitió, byte por byte."""

    def test_devuelve_el_archivo_guardado_byte_por_byte(self):
        cuerpo = self.emitir_informe().get_json()
        respuesta = self.cliente.get(f"/api/informes/{cuerpo['id']}/pdf")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual("application/pdf", respuesta.mimetype)
        self.assertEqual(Path(cuerpo["ruta_pdf"]).read_bytes(), respuesta.data)

    def test_no_regenera_nada(self):
        """Prueba dura: si el endpoint recompusiera, no diría lo que dice el disco."""
        cuerpo = self.emitir_informe().get_json()
        Path(cuerpo["ruta_pdf"]).write_bytes(b"%PDF-1.4 este es el que se emitio")
        respuesta = self.cliente.get(f"/api/informes/{cuerpo['id']}/pdf")
        self.assertEqual(b"%PDF-1.4 este es el que se emitio", respuesta.data)

    def test_el_pdf_no_queda_tomado_por_el_servidor(self):
        """Se lee a memoria: con el handle abierto Windows no lo deja borrar."""
        cuerpo = self.emitir_informe().get_json()
        self.cliente.get(f"/api/informes/{cuerpo['id']}/pdf")
        Path(cuerpo["ruta_pdf"]).unlink()          # no levanta PermissionError

    def test_informe_inexistente_da_404(self):
        respuesta = self.cliente.get("/api/informes/9999/pdf")
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("Actualizá la pantalla", respuesta.get_json()["error"])

    def test_pdf_movido_da_404_diciendo_donde_lo_buscaba(self):
        cuerpo = self.emitir_informe().get_json()
        Path(cuerpo["ruta_pdf"]).unlink()
        respuesta = self.cliente.get(f"/api/informes/{cuerpo['id']}/pdf")
        self.assertEqual(respuesta.status_code, 404)
        mensaje = respuesta.get_json()["error"]
        self.assertIn("respaldo", mensaje)
        self.assertIn(cuerpo["ruta_pdf"], mensaje)
        # …y nombra el informe por su día, no por la marca de tiempo con la
        # que se guarda (`2026-08-18T20:17:56` no le dice nada al médico).
        self.assertIn(f"del {date.today().strftime('%d/%m/%Y')}", mensaje)

    def test_abrir_responde_ok(self):
        cuerpo = self.emitir_informe().get_json()
        respuesta = self.cliente.post(f"/api/informes/{cuerpo['id']}/abrir")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual({"ok": True}, respuesta.get_json())

    def test_abrir_sin_archivo_da_404(self):
        cuerpo = self.emitir_informe().get_json()
        Path(cuerpo["ruta_pdf"]).unlink()
        respuesta = self.cliente.post(f"/api/informes/{cuerpo['id']}/abrir")
        self.assertEqual(respuesta.status_code, 404)


class TestAnulacionDeInformes(BaseInformes):
    """Espejo de la anulación del récipe: marca, conserva y no repite."""

    def anular(self, informe_id, motivo="Datos equivocados"):
        return self.cliente.post(f"/api/informes/{informe_id}/anular",
                                 json={"motivo": motivo})

    def test_anula_con_motivo_y_devuelve_el_informe(self):
        informe_id = self.emitir_informe().get_json()["id"]
        respuesta = self.anular(informe_id)
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        cuerpo = respuesta.get_json()
        self.assertTrue(cuerpo["anulado"])
        self.assertEqual("Datos equivocados", cuerpo["motivo_anulacion"])
        self.assertTrue(cuerpo["fecha_anulacion"])

        con = self.conexion()
        try:
            fila = basedatos.obtener_informe(con, informe_id)
            self.assertEqual(1, fila["anulado"])
            self.assertEqual("Datos equivocados", fila["motivo_anulacion"])
        finally:
            con.close()

    def test_anular_dos_veces_es_400_y_no_pisa_el_motivo(self):
        informe_id = self.emitir_informe().get_json()["id"]
        self.anular(informe_id, "Paciente equivocado")
        repetida = self.anular(informe_id, "Otro motivo")
        self.assertEqual(repetida.status_code, 400)
        self.assertIn("ya estaba anulado", repetida.get_json()["error"])
        self.assertIn("Paciente equivocado", repetida.get_json()["error"])
        # Un informe no tiene número propio (el código impreso es el del
        # paciente, dec. 2): lo único que lo nombra es la fecha, y en la base
        # es una marca de tiempo. Al médico se le muestra el día, no los
        # segundos.
        self.assertNotIn("T", repetida.get_json()["error"].split("Motivo")[0])
        self.assertIn(date.today().strftime("%d/%m/%Y"),
                      repetida.get_json()["error"])

        con = self.conexion()
        try:
            fila = basedatos.obtener_informe(con, informe_id)
            self.assertEqual("Paciente equivocado", fila["motivo_anulacion"])
        finally:
            con.close()

    def test_sin_motivo_no_se_anula(self):
        informe_id = self.emitir_informe().get_json()["id"]
        respuesta = self.anular(informe_id, "   ")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("motivo", respuesta.get_json()["error"])
        con = self.conexion()
        try:
            self.assertEqual(0, basedatos.obtener_informe(con, informe_id)["anulado"])
        finally:
            con.close()

    def test_el_pdf_sobrevive_a_la_anulacion(self):
        """§10: no se borra nada. El informe entregado hay que poder mirarlo."""
        cuerpo = self.emitir_informe().get_json()
        antes = Path(cuerpo["ruta_pdf"]).read_bytes()
        self.anular(cuerpo["id"])
        self.assertEqual(antes, Path(cuerpo["ruta_pdf"]).read_bytes())
        respuesta = self.cliente.get(f"/api/informes/{cuerpo['id']}/pdf")
        self.assertEqual(200, respuesta.status_code)
        self.assertEqual(antes, respuesta.data)

    def test_no_toca_el_registro_excel(self):
        """El registro de §9 es de récipes: un informe no tiene medicamentos."""
        ruta = excel.ruta_registro(self.dir_datos)
        antes = ruta.read_bytes()
        informe_id = self.emitir_informe().get_json()["id"]
        self.anular(informe_id)
        self.assertEqual(antes, ruta.read_bytes())

    def test_anular_un_informe_inexistente_da_404(self):
        respuesta = self.anular(9999)
        self.assertEqual(respuesta.status_code, 404)


class TestUltimoRecipeParaElInforme(BaseInformes):
    """El botón "Traer del último récipe" de Tratamiento indicado (dec. 10)."""

    def pedir(self, paciente_id=None):
        return self.cliente.get(
            f"/api/pacientes/{paciente_id or self.paciente_id}/ultimo-recipe")

    def test_trae_los_renglones_del_ultimo_recipe(self):
        self.emitir(items=OTROS_ITEMS, fecha="2026-08-20")
        respuesta = self.pedir()
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.get_json()
        self.assertEqual("2026-08-20", cuerpo["fecha"])
        self.assertEqual([{
            "medicamento": "Losartán", "presentacion": "50 mg",
            "cantidad": "30 tabletas", "dosis": "1 diaria",
        }], cuerpo["items"])

    def test_un_paciente_sin_recipes_no_es_un_error(self):
        con = self.conexion()
        try:
            otro = basedatos.crear_paciente(con, "Ana Gómez", cedula="V-999")
            con.commit()
        finally:
            con.close()
        respuesta = self.pedir(otro)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual([], respuesta.get_json()["items"])

    def test_el_recipe_anulado_no_se_vuelca(self):
        """Volcar lo que se anuló es justo el error que la anulación corrigió."""
        self.emitir(items=OTROS_ITEMS, fecha="2026-08-20")
        ultimo = self.historial()["resultados"][0]["id"]
        self.cliente.post(f"/api/recipes/{ultimo}/anular",
                          json={"motivo": "Dosis equivocada"})
        cuerpo = self.pedir().get_json()
        self.assertEqual("2026-08-14", cuerpo["fecha"])
        self.assertEqual(["Amoxicilina"],
                         [i["medicamento"] for i in cuerpo["items"]])

    def test_paciente_inexistente_da_404(self):
        self.assertEqual(404, self.pedir(9999).status_code)


class TestFraseInicial(BaseInformes):
    """La frase de la plantilla B, armada una vez y editable (dec. 10)."""

    def pedir(self, motivo="", paciente_id=None):
        return self.cliente.get(
            f"/api/pacientes/{paciente_id or self.paciente_id}"
            f"/frase-inicial?motivo={motivo}")

    def ficha(self, **campos):
        con = self.conexion()
        try:
            basedatos.actualizar_paciente(con, self.paciente_id, **campos)
            con.commit()
        finally:
            con.close()

    def historia(self, **campos):
        con = self.conexion()
        try:
            basedatos.guardar_historia(con, self.paciente_id, **campos)
            con.commit()
        finally:
            con.close()

    def test_la_frase_del_ejemplo_real(self):
        self.ficha(sexo="F", edad=60)
        self.historia(cronico_degenerativos="Dislipidemia\nTrastornos del sueño")
        respuesta = self.pedir("aumento de peso progresivo")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            "Se trata de paciente femenino de 60 años de edad, quien consulta "
            "por presentar aumento de peso progresivo con antecedentes de "
            "dislipidemia y trastornos del sueño.",
            respuesta.get_json()["frase"])

    def test_masculino(self):
        self.ficha(sexo="M", edad=40)
        self.assertEqual(
            "Se trata de paciente masculino de 40 años de edad, quien consulta "
            "por presentar dolor lumbar.",
            self.pedir("dolor lumbar").get_json()["frase"])

    def test_sin_sexo_la_frase_sale_neutra(self):
        """Adivinarle el sexo al paciente es peor que no decirlo."""
        self.ficha(sexo="", edad=60)
        self.assertEqual(
            "Se trata de paciente de 60 años de edad, quien consulta por "
            "presentar cefalea.",
            self.pedir("cefalea").get_json()["frase"])

    def test_sin_historia_cargada_no_hay_antecedentes(self):
        self.ficha(sexo="F", edad=60)
        frase = self.pedir("cefalea").get_json()["frase"]
        self.assertNotIn("antecedentes", frase)
        self.assertTrue(frase.endswith("cefalea."))

    def test_sin_motivo_la_frase_es_solo_la_presentacion(self):
        self.ficha(sexo="F", edad=60)
        self.assertEqual("Se trata de paciente femenino de 60 años de edad.",
                         self.pedir().get_json()["frase"])

    def test_paciente_inexistente_da_404(self):
        self.assertEqual(404, self.pedir("cefalea", 9999).status_code)


class TestResumirAntecedentes(unittest.TestCase):
    """El recuadro de crónico-degenerativos, pasado a enumeración."""

    def test_un_renglon_por_antecedente(self):
        self.assertEqual(
            "dislipidemia y trastornos del sueño",
            rutas.resumir_antecedentes("Dislipidemia\nTrastornos del sueño"))

    def test_el_punto_y_coma_tambien_separa(self):
        self.assertEqual(
            "dislipidemia y hipotiroidismo",
            rutas.resumir_antecedentes("Dislipidemia; Hipotiroidismo"))

    def test_las_siglas_no_se_tocan(self):
        self.assertEqual("HTA y diabetes mellitus tipo 2",
                         rutas.resumir_antecedentes("HTA\nDiabetes mellitus tipo 2"))

    def test_tres_o_mas_se_enumeran_con_comas(self):
        self.assertEqual(
            "dislipidemia, hipotiroidismo y asma",
            rutas.resumir_antecedentes("Dislipidemia\nHipotiroidismo\nAsma"))

    def test_no_se_lleva_la_historia_entera_a_la_frase(self):
        muchos = "\n".join(f"Antecedente {n}" for n in range(1, 9))
        resumen = rutas.resumir_antecedentes(muchos)
        self.assertEqual("antecedente 1, antecedente 2 y antecedente 3", resumen)

    def test_vacio_es_vacio(self):
        for crudo in ("", None, "   ", "\n\n", ".", "; ;"):
            self.assertEqual("", rutas.resumir_antecedentes(crudo))

    def test_los_puntos_finales_se_caen(self):
        self.assertEqual("dislipidemia desde 2021",
                         rutas.resumir_antecedentes("Dislipidemia desde 2021."))


class TestDatosDelMedico(BaseApp):
    """Dec. 9: precargados si están vacíos, editables para siempre."""

    def test_los_datos_de_fabrica_salen_precargados(self):
        datos = self.cliente.get("/api/config").get_json()
        self.assertEqual("Dr. Eleazar Shiera Bastidas", datos["nombre"])
        self.assertEqual("7414", datos["comezu"])
        self.assertEqual("34846", datos["mpps"])
        self.assertEqual("Maracaibo", datos["ciudad"])

    def test_lo_que_el_medico_edita_no_se_vuelve_a_pisar(self):
        self.cliente.post("/api/config", json={"comezu": "9999",
                                               "ciudad": "Cabimas"})
        for _ in range(3):
            datos = self.cliente.get("/api/config").get_json()
        self.assertEqual("9999", datos["comezu"])
        self.assertEqual("Cabimas", datos["ciudad"])

    def test_el_rif_no_se_precarga(self):
        """No se imprime en ningún lado: precargarlo es pedir que envejezca mal."""
        self.assertEqual("", self.cliente.get("/api/config").get_json()["rif"])


class TestHistoriaImprimible(BaseInformes):
    """La historia se imprime al vuelo y NO se guarda (no es un documento)."""

    def pedir(self, paciente_id=None):
        return self.cliente.get(
            f"/api/pacientes/{paciente_id or self.paciente_id}/historia/pdf")

    def test_devuelve_un_pdf(self):
        respuesta = self.pedir()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual("application/pdf", respuesta.mimetype)
        self.assertTrue(respuesta.data.startswith(b"%PDF"))
        self.assertIn("HISTORIA_EC-0001_Juan-Perez.pdf",
                      respuesta.headers.get("Content-Disposition", ""))

    def test_no_deja_ningun_archivo_ni_ninguna_ruta_guardada(self):
        self.pedir()
        self.assertEqual([], self.informes_en_disco())
        con = self.conexion()
        try:
            self.assertEqual([], basedatos.listar_informes(con, self.paciente_id))
        finally:
            con.close()

    def test_crece_con_lo_que_hay_en_la_base(self):
        """La historia se arma al vuelo: si se carga una consulta, sale ahí."""
        vacia = self.pedir()
        self.assertEqual(vacia.status_code, 200)

        con = self.conexion()
        try:
            consulta_id = basedatos.crear_consulta(
                con, self.paciente_id, fecha="2026-08-14",
                motivo="Control de peso",
                evolucion="Refiere aumento de cuatro kilos desde la última "
                          "consulta, con somnolencia diurna.")
            basedatos.guardar_signos_vitales(
                con, consulta_id, ta_sistolica=138, ta_diastolica=86,
                peso=97.9, talla=1.68)
            basedatos.guardar_historia(
                con, self.paciente_id, alergias="Penicilina",
                cronico_degenerativos="Dislipidemia desde 2021.")
            con.commit()
        finally:
            con.close()

        con_consulta = self.pedir()
        self.assertEqual(con_consulta.status_code, 200)
        self.assertGreater(len(con_consulta.data), len(vacia.data),
                           "el PDF tiene que traer la consulta nueva")

    def test_paciente_inexistente_da_404(self):
        respuesta = self.pedir(9999)
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("Volvé a buscarlo", respuesta.get_json()["error"])


# --------------------------------------------------------------------------
# La pantalla dice lo mismo que imprime la hoja
# --------------------------------------------------------------------------

#: Etiquetas que no cierran: si se apilaran, todo lo que sigue quedaría
#: colgando adentro de un `<input>` y la ascendencia daría cualquier cosa.
_SIN_CIERRE = {"area", "base", "br", "col", "embed", "hr", "img", "input",
               "link", "meta", "param", "source", "track", "wbr"}


class _Arbol(HTMLParser):
    """El `index.html` como árbol, para preguntarle si un selector existe.

    No es un motor de CSS: entiende `#id`, `.clase`, `etiqueta` y la
    combinación de descendencia (`#panel-nuevo .columna-previa`), que es todo
    lo que usan los pasos del tutorial. Sirve para probar contra el archivo lo
    que en la pantalla se ve enseguida y en la suite no se ve nunca: un paso
    del recorrido que apunta a un elemento que ya no está.
    """

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.nodos: list[dict] = []
        self._pila: list[int] = []
        self.feed(html)

    # -- armado ------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        self.nodos.append({
            "tag": tag,
            "id": d.get("id"),
            "clases": set((d.get("class") or "").split()),
            "attrs": d,
            "padres": tuple(self._pila),
        })
        if tag not in _SIN_CIERRE:
            self._pila.append(len(self.nodos) - 1)

    def handle_startendtag(self, tag, attrs):
        guardada = list(self._pila)
        self.handle_starttag(tag, attrs)
        self._pila = guardada

    def handle_endtag(self, tag):
        for i in range(len(self._pila) - 1, -1, -1):
            if self.nodos[self._pila[i]]["tag"] == tag:
                del self._pila[i:]
                return

    # -- consultas ---------------------------------------------------------

    @staticmethod
    def _coincide(nodo: dict, token: str) -> bool:
        partes = re.findall(r"[.#]?[A-Za-z0-9_-]+", token)
        for parte in partes:
            if parte.startswith("#"):
                if nodo["id"] != parte[1:]:
                    return False
            elif parte.startswith("."):
                if parte[1:] not in nodo["clases"]:
                    return False
            elif nodo["tag"] != parte:
                return False
        return True

    def buscar(self, selector: str) -> list[dict]:
        tokens = selector.split()
        encontrados = []
        for nodo in self.nodos:
            if not self._coincide(nodo, tokens[-1]):
                continue
            faltan = list(tokens[:-1])
            for indice in nodo["padres"]:
                if faltan and self._coincide(self.nodos[indice], faltan[0]):
                    faltan.pop(0)
            if not faltan:
                encontrados.append(nodo)
        return encontrados

    def uno(self, selector: str) -> dict | None:
        hallados = self.buscar(selector)
        return hallados[0] if hallados else None


class TestTextosDeLaInterfaz(unittest.TestCase):
    """`app/web/` no tiene suite propia, y estos textos mienten en silencio.

    Cuando el código pasó a ser del paciente (dec. 1 y 2), el frontend siguió
    diciendo `EC-____-____`, mostrando `EC-2026-0001` de ejemplo y avisando que
    el código «no se vuelve a usar» al anular. Nada de eso rompe una petición,
    así que ningún test lo iba a agarrar: se fija acá, contra el archivo.
    """

    WEB = RAIZ / "app" / "web"

    def leer(self, nombre: str) -> str:
        return (self.WEB / nombre).read_text(encoding="utf-8")

    def test_el_relleno_del_js_es_el_del_backend(self):
        js = self.leer("app.js")
        self.assertIn('return prefijoActual + "-' + rutas.RELLENO_CODIGO + '";', js)
        self.assertNotIn("-____-____", js)

    def test_el_html_no_muestra_el_formato_viejo(self):
        html = self.leer("index.html")
        for viejo in ("EC-____-____", "EC-0000-0000", "EC-2026-0001"):
            self.assertNotIn(viejo, html, f"quedó el formato viejo {viejo}")
        self.assertIn('id="relleno-codigo">EC-____<', html)

    def test_la_muestra_de_configuracion_no_lleva_anio(self):
        js = self.leer("app.js")
        self.assertNotIn('prefijo + "-" + anio + "-0001"', js)
        self.assertIn('nCfg.muestra.textContent = prefijo + "-0001";', js)

    def test_configuracion_ofrece_los_campos_del_informe(self):
        """Dec. 9: COMEZU y ciudad se editan en Configuración, no en el código."""
        html = self.leer("index.html")
        for campo in rutas.CAMPOS_MEDICO:
            self.assertIn(f'data-config="{campo}"', html,
                          f"falta el campo «{campo}» en Configuración")
        js = self.leer("app.js")
        for campo in ("comezu", "ciudad"):
            self.assertIn(f'"{campo}"', js)

    def test_configuracion_no_dice_que_los_datos_no_se_imprimen(self):
        """Desde la 2.0 sí se imprimen: van en la cabecera del informe."""
        html = self.leer("index.html")
        self.assertNotIn("no salen impresos", html)
        self.assertNotIn("la app no guarda ninguna imagen de firma", html)
        self.assertIn("informe médico", html)

    def test_anular_no_promete_que_el_codigo_se_retira(self):
        """El código es del paciente: anular un récipe no lo saca de circulación."""
        for archivo in ("app.js", "index.html"):
            self.assertNotIn("no se vuelve a usar", self.leer(archivo), archivo)

    def test_el_aviso_de_informe_vacio_dice_lo_mismo_de_los_dos_lados(self):
        """La pantalla avisa antes de mandar; el backend, si el pedido llega igual.

        Si los dos textos se separan, el médico ve un aviso al hacer clic y
        **otro distinto** cuando el pedido pasa igual (una pantalla vieja, dos
        ventanas abiertas). Peor todavía: el del backend nombraba «el cuerpo»
        también en el formulario de la aseguradora, que no tiene ningún campo
        con ese nombre.
        """
        self.assertEqual(set(pdf_informe.TIPOS), set(rutas.VACIO_POR_TIPO),
                         "hay un tipo de informe sin su aviso de vacío")
        js = self.leer("app.js")
        for tipo, campos in rutas.VACIO_POR_TIPO.items():
            self.assertIn(
                f"El informe está vacío. Escribí al menos {campos}.", js,
                f"el aviso del tipo «{tipo}» no coincide con el del backend")

    # -- dec. 18: la historia es la puerta de entrada ----------------------

    def arbol(self) -> _Arbol:
        return _Arbol(self.leer("index.html"))

    @staticmethod
    def _pegar_literales(js: str) -> str:
        """Junta los `"…" + "…"` del JS para poder buscar un texto entero.

        Los mensajes largos vienen cortados en varias líneas para entrar en el
        ancho del archivo; sin esto, cualquier búsqueda del texto completo
        fallaría por el lugar donde quedó el corte.
        """
        return re.sub(r'"\s*\+\s*"', "", js)

    def test_la_historia_es_la_primera_pestana_y_la_que_abre(self):
        """Dec. 18: va primera en la barra y es la que se ve al arrancar.

        Son tres cosas que tienen que decir lo mismo y viven en dos archivos:
        el orden de los botones, cuál nace con `activa`/`aria-selected` (que es
        de dónde `montarPestanas()` deduce la pestaña inicial) y qué panel nace
        sin `hidden`. Si se separan, la app abre en una pantalla y la barra
        marca otra.
        """
        arbol = self.arbol()
        pestanas = arbol.buscar("nav.pestanas button.pestana")
        self.assertEqual(
            ["tab-historia", "tab-nuevo", "tab-examenes", "tab-infiltraciones",
             "tab-historial", "tab-config"],
            [p["id"] for p in pestanas],
            "cambió el orden de las pestañas")

        primera = pestanas[0]
        self.assertIn("activa", primera["clases"], "la Historia no nace activa")
        self.assertEqual("true", primera["attrs"].get("aria-selected"))
        for otra in pestanas[1:]:
            self.assertNotIn("activa", otra["clases"], otra["id"])
            self.assertEqual("false", otra["attrs"].get("aria-selected"), otra["id"])

        for panel in arbol.buscar("section.panel"):
            oculto = "hidden" in panel["attrs"]
            if panel["id"] == "panel-historia":
                self.assertFalse(oculto, "el panel de la Historia arranca oculto")
            else:
                self.assertTrue(oculto, f"{panel['id']} arranca visible")

        # Y el JS arranca creyendo lo mismo, por si corre antes de montar la barra.
        self.assertIn('let pestanaActiva = "panel-historia";', self.leer("app.js"))

    def test_los_pasos_del_tutorial_apuntan_a_algo_que_existe(self):
        """El recorrido de primer uso se reordenó al flujo nuevo (dec. 18).

        Cada paso resalta un elemento por selector y pide una pestaña por id.
        Un selector que ya no existe no rompe nada: el globo se centra y el
        médico ve un cartel flotando sin saber de qué le hablan. Por eso se
        comprueban contra el HTML, uno por uno.
        """
        js = self.leer("app.js")
        bloque = js.split("const PASOS_TUTORIAL = [", 1)[1].split("\n];", 1)[0]
        pasos = bloque.split("  {\n")[1:]
        self.assertGreaterEqual(len(pasos), 8, "se perdieron pasos del tutorial")

        arbol = self.arbol()
        paneles = {p["id"] for p in arbol.buscar("section.panel")}
        vistos = 0
        for numero, paso in enumerate(pasos, start=1):
            crudo = paso.split("destino:", 1)[1].split("\n", 1)[0]
            for selector in re.findall(r'"([^"]+)"', crudo):
                vistos += 1
                self.assertIsNotNone(
                    arbol.uno(selector),
                    f"el paso {numero} apunta a «{selector}», que no está en el HTML")
            pestana = re.search(r'pestana:\s*"([^"]+)"', paso)
            if pestana:
                self.assertIn(pestana.group(1), paneles,
                              f"el paso {numero} pide una pestaña que no existe")
        self.assertGreaterEqual(vistos, 8, "los pasos se quedaron sin destino")

    def test_el_texto_de_falta_el_nombre_del_alta_es_el_del_backend(self):
        """La tarjeta del alta avisa antes de mandar; el backend, si llega igual.

        Es el mismo caso que el del informe vacío: dos textos distintos para el
        mismo error se leen como dos problemas distintos. Y el del alta nombra
        el botón que el médico apretó, así que no se puede reusar el del récipe.
        """
        js = self._pegar_literales(self.leer("app.js"))
        self.assertIn(rutas.FALTA_NOMBRE_ALTA, js,
                      "el aviso del alta no coincide con FALTA_NOMBRE_ALTA")
        self.assertNotIn(rutas.FALTA_NOMBRE_RECIPE, js.split("crearPacienteDesdeHistoria", 1)[1],
                         "el alta está usando el texto del récipe")

    def test_el_alta_manda_los_campos_que_el_backend_acepta(self):
        """Lo que arma `crearPacienteDesdeHistoria()` contra `validar_paciente`."""
        js = self.leer("app.js")
        cuerpo = js.split("async function crearPacienteDesdeHistoria", 1)[1]
        cuerpo = cuerpo.split("const cuerpo = {", 1)[1].split("};", 1)[0]
        campos = set(re.findall(r"^\s*([a-z_]+):", cuerpo, re.MULTILINE))
        aceptados = set(rutas.validar_paciente({"nombre": "X"}))
        self.assertTrue(campos <= aceptados,
                        f"el alta manda campos que el backend tira: {campos - aceptados}")
        self.assertIn("nombre", campos)

    def test_el_recipe_manda_el_id_del_paciente_de_la_historia(self):
        """Sin el id, el récipe de la banda se archiva por nombre (dec. 18).

        Es la línea que evita que un homónimo —o el nombre corregido a mano
        antes de imprimir— parta el archivo del paciente en dos.
        """
        js = self.leer("app.js")
        cuerpo = js.split("function cuerpoRecipe()", 1)[1].split("\n}", 1)[0]
        self.assertIn("paciente.id = estado.paciente.id;", cuerpo)

    def test_la_pantalla_ofrece_los_sexos_que_el_informe_entiende(self):
        """Lo que se elige en el alta arma la frase inicial del informe (dec. 10)."""
        arbol = self.arbol()
        opciones = [o["attrs"].get("value", "")
                    for o in arbol.buscar("#hc-alta-sexo option")]
        self.assertTrue(opciones, "no quedó ningún sexo para elegir en el alta")
        generos = set()
        for valor in opciones:
            frase = pdf_informe.frase_inicial(valor, 41)
            if valor:
                self.assertRegex(
                    frase, r"paciente (femenino|masculino) de 41",
                    f"el informe no entiende el sexo «{valor}» que ofrece la pantalla")
                generos.add(frase.split()[4])
        self.assertEqual({"femenino", "masculino"}, generos)


if __name__ == "__main__":
    unittest.main()
