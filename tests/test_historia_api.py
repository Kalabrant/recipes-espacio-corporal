"""Tests de la API de la historia clínica: ficha, consultas, bandeja y anexos.

Lo que se prueba acá es el contrato de la 2.0 (dec. 3 a 6, 11, 13, 15 y 17):

- la ficha y los antecedentes se guardan de a secciones y no se pisan;
- las consultas llevan sus signos vitales, con IMC y TAM calculados;
- la bandeja mira Descargas, el Escritorio y `entrada`, ofrece solo lo de los
  últimos 30 días y esconde lo que ya está anexado, sin tocar un solo archivo;
- anexar **copia** el original byte por byte y deja la miniatura al lado;
- la misma imagen no entra dos veces (409);
- el gráfico de evolución combina las mediciones tipeadas con los signos
  vitales de las consultas, rotulando la fuente;
- un token inventado responde 404 y no cuenta nada del disco.

Se usa el cliente de pruebas de Flask contra una carpeta temporal, con
`USERPROFILE` apuntando también ahí: la bandeja mira carpetas de verdad, así
que las de la máquina del que corre la suite quedan fuera de juego.

Solo `unittest` de la stdlib más lo que ya es dependencia (§3: Pillow ya se usa
para el logo).
Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import gc
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import unittest.mock
import warnings
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import basedatos  # noqa: E402
import main  # noqa: E402
import pdf_historia  # noqa: E402
import rutas  # noqa: E402


DIA = 86400


def imagen_jpeg(ruta: Path, ancho: int = 60, alto: int = 90,
                color: tuple[int, int, int] = (10, 120, 200)) -> Path:
    """Deja una imagen de verdad en disco (la bandeja no acepta archivos falsos)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (ancho, alto), color).save(ruta, format="JPEG", quality=90)
    return ruta


def envejecer(ruta: Path, dias: float) -> None:
    """Le corre la fecha al archivo, que es por lo que la bandeja filtra."""
    cuando = time.time() - dias * DIA
    os.utime(ruta, (cuando, cuando))


def sha256_de(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


class BaseHistoriaApi(unittest.TestCase):
    """App real sobre una carpeta temporal, con un paciente ya dado de alta."""

    def setUp(self) -> None:
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)

        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_historia_api_"))
        self.dir_datos = self.carpeta / "Recipes"
        for sub in main.SUBCARPETAS:
            (self.dir_datos / sub).mkdir(parents=True)

        # El perfil de mentira: la bandeja mira estas carpetas y no las del
        # que está corriendo la suite.
        self.perfil = self.carpeta / "perfil"
        self.descargas = self.perfil / "Downloads"
        self.escritorio = self.perfil / "Desktop"
        self.descargas.mkdir(parents=True)
        self.escritorio.mkdir(parents=True)
        self.entrada = self.dir_datos / "entrada"

        self._entorno = {clave: os.environ.get(clave)
                         for clave in ("USERPROFILE", "ONEDRIVE", "RECIPES_ABRIR_PDF")}
        os.environ["USERPROFILE"] = str(self.perfil)
        os.environ.pop("ONEDRIVE", None)
        os.environ["RECIPES_ABRIR_PDF"] = "0"

        self.app = rutas.crear_app(self.dir_datos)
        self.app.config.update(TESTING=True)
        self.cliente = self.app.test_client()

        con = self.conexion()
        try:
            self.paciente_id = basedatos.crear_paciente(
                con, "María González", cedula="V-7856151", edad=47, sexo="F")
            con.commit()
        finally:
            con.close()

    def tearDown(self) -> None:
        for clave, valor in self._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(self.carpeta, ignore_errors=True)

    # -- ayudas ------------------------------------------------------------

    def conexion(self):
        return basedatos.inicializar(self.dir_datos / "datos" / "recipes.db")

    def bandeja(self) -> list[dict]:
        respuesta = self.cliente.get("/api/bandeja")
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        return respuesta.get_json()["imagenes"]

    def anexar(self, token: str, fecha: str = "2026-08-14", **extra):
        cuerpo = {"token": token, "fecha_medicion": fecha, **extra}
        return self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos", json=cuerpo)

    def carpeta_del_paciente(self) -> Path:
        return self.dir_datos / "pacientes" / "EC-0001_Maria-Gonzalez"

    def anexos_en_disco(self) -> list[Path]:
        return sorted((self.carpeta_del_paciente() / "anexos").glob("*"))


# --------------------------------------------------------------------------
# Alta de paciente desde la Historia (dec. 18)
# --------------------------------------------------------------------------

class TestAltaDePaciente(BaseHistoriaApi):
    """`POST /api/pacientes`: la puerta de entrada de la 2.0 (dec. 18).

    El médico escribe un nombre en el buscador de la Historia, no aparece, y lo
    crea ahí mismo: sin emitir un récipe y sin pasar por otra pantalla. Lo que
    se prueba es que el alta deja al paciente **listo para trabajar** (código y
    carpeta) y que la segunda alta de la misma persona no le parte el archivo
    en dos.
    """

    NUEVO = {"nombre": "Pedro Pérez", "cedula": "V-1234567", "edad": 60,
             "sexo": "M", "telefono": "0414-1234567",
             "fecha_nacimiento": "1966-03-12"}

    def alta(self, **campos):
        return self.cliente.post("/api/pacientes", json=campos)

    def pacientes(self) -> list[dict]:
        con = self.conexion()
        try:
            return [dict(f) for f in
                    con.execute("SELECT * FROM pacientes ORDER BY id")]
        finally:
            con.close()

    # -- alta nueva --------------------------------------------------------

    def test_alta_nueva_asigna_codigo_y_crea_la_carpeta(self):
        respuesta = self.alta(**self.NUEVO)
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        cuerpo = respuesta.get_json()

        self.assertFalse(cuerpo["ya_existia"])
        # Dec. 1: correlativo de por vida. María se llevó el EC-0001 en setUp.
        self.assertEqual("EC-0002", cuerpo["codigo"])

        paciente = cuerpo["paciente"]
        self.assertEqual("EC-0002", paciente["codigo"],
                         "el código también viaja adentro del paciente")
        self.assertEqual("Pedro Pérez", paciente["nombre"])
        self.assertEqual("V-1234567", paciente["cedula"])
        self.assertEqual(60, paciente["edad"])
        self.assertEqual("M", paciente["sexo"])
        self.assertEqual("0414-1234567", paciente["telefono"])
        self.assertEqual("1966-03-12", paciente["fecha_nacimiento"])
        self.assertIsInstance(paciente["id"], int)

        # Dec. 17: tener historia es tener carpeta propia, con las tres
        # subcarpetas hechas antes del primer anexo y del primer informe.
        carpeta = self.dir_datos / "pacientes" / "EC-0002_Pedro-Perez"
        for sub in ("recipes", "informes", "anexos"):
            self.assertTrue((carpeta / sub).is_dir(), sub)

        # Y quedó en la base, una sola vez.
        self.assertEqual(["María González", "Pedro Pérez"],
                         [p["nombre"] for p in self.pacientes()])

    def test_el_alta_abre_una_historia_vacia_de_verdad(self):
        """El id que devuelve el alta sirve para abrir la historia enseguida."""
        paciente_id = self.alta(**self.NUEVO).get_json()["paciente"]["id"]
        historia = self.cliente.get(f"/api/pacientes/{paciente_id}/historia")
        self.assertEqual(200, historia.status_code)
        datos = historia.get_json()
        self.assertEqual("EC-0002", datos["paciente"]["codigo"])
        self.assertIsNone(datos["historia"], "recién creada: todavía sin ficha")
        self.assertEqual([], datos["consultas"])

    def test_el_alta_entra_al_buscador_con_todo_lo_que_la_historia_necesita(self):
        """Dec. 18: la búsqueda de la Historia es la principal de pacientes.

        La sugerencia tiene que traer de una lo que la pantalla usa para abrir
        la historia y para arrancar el récipe con ese paciente puesto por
        omisión (id, nombre, cédula, edad y código): si faltara alguno, elegir
        un paciente costaría un segundo pedido y el récipe saldría en blanco.
        """
        self.alta(**self.NUEVO)
        respuesta = self.cliente.get("/api/sugerencias/pacientes?q=Perez")
        self.assertEqual(200, respuesta.status_code)
        resultados = respuesta.get_json()["resultados"]
        self.assertEqual(1, len(resultados))
        encontrado = resultados[0]
        for campo in ("id", "nombre", "cedula", "edad", "codigo"):
            self.assertIn(campo, encontrado, campo)
        self.assertEqual("EC-0002", encontrado["codigo"])
        self.assertEqual("V-1234567", encontrado["cedula"])
        self.assertEqual(60, encontrado["edad"])
        # Y también por código, que es lo que el médico tiene a mano mirando un
        # récipe impreso (dec. 1).
        por_codigo = self.cliente.get("/api/sugerencias/pacientes?q=EC-0002")
        self.assertEqual("Pedro Pérez",
                         por_codigo.get_json()["resultados"][0]["nombre"])

    # -- alta repetida -----------------------------------------------------

    def test_alta_repetida_por_cedula_devuelve_el_mismo_sin_duplicar(self):
        """El nombre escrito distinto no crea una segunda María González."""
        respuesta = self.alta(nombre="Maria Gonzalez R.", cedula="V-7856151")
        self.assertEqual(200, respuesta.status_code, respuesta.get_json())
        cuerpo = respuesta.get_json()

        self.assertTrue(cuerpo["ya_existia"], "es la misma cédula")
        self.assertEqual(self.paciente_id, cuerpo["paciente"]["id"])
        self.assertEqual("EC-0001", cuerpo["codigo"])
        # Se devuelve la ficha tal como está guardada, no lo que se tipeó.
        self.assertEqual("María González", cuerpo["paciente"]["nombre"])
        self.assertEqual(1, len(self.pacientes()), "no se creó un segundo")

    def test_alta_repetida_por_nombre_cuando_no_hay_cedula(self):
        """Sin cédula, el nombre normalizado alcanza (sin acentos ni mayúsculas)."""
        respuesta = self.alta(nombre="maria gonzalez")
        self.assertEqual(200, respuesta.status_code)
        cuerpo = respuesta.get_json()
        self.assertTrue(cuerpo["ya_existia"])
        self.assertEqual(self.paciente_id, cuerpo["paciente"]["id"])
        self.assertEqual(1, len(self.pacientes()))

    def test_la_repetida_completa_lo_que_faltaba_y_no_pisa_lo_que_habia(self):
        """El médico carga de a poco; corregir es un acto explícito de la ficha."""
        self.alta(nombre="María González", cedula="V-7856151",
                  edad=99, telefono="0261-7000000")
        guardado = self.pacientes()[0]
        self.assertEqual(47, guardado["edad"], "la edad que ya estaba no se pisa")
        self.assertEqual("0261-7000000", guardado["telefono"],
                         "el teléfono que faltaba sí se completa")

    def test_una_alta_repetida_no_quema_un_codigo(self):
        """Dec. 1: el correlativo es de por vida; no se saltean números."""
        self.alta(nombre="María González", cedula="V-7856151")
        primera = self.alta(**self.NUEVO)
        self.assertEqual("EC-0002", primera.get_json()["codigo"])
        segunda = self.alta(nombre="Ana Rojas")
        self.assertEqual("EC-0003", segunda.get_json()["codigo"])

    def test_dos_altas_seguidas_no_comparten_carpeta(self):
        self.alta(**self.NUEVO)
        self.alta(nombre="Ana Rojas")
        carpetas = sorted(p.name for p in
                          (self.dir_datos / "pacientes").iterdir())
        self.assertEqual(["EC-0002_Pedro-Perez", "EC-0003_Ana-Rojas"],
                         sorted(carpetas))

    # -- validaciones ------------------------------------------------------

    def test_sin_nombre_dice_que_hacer(self):
        respuesta = self.alta(cedula="V-9999999", edad=30)
        self.assertEqual(400, respuesta.status_code)
        error = respuesta.get_json()["error"]
        self.assertIn("Escribí el nombre del paciente", error)
        self.assertIn("dar", error.lower(), "el texto nombra el alta, no el récipe")
        self.assertEqual(1, len(self.pacientes()), "no se creó nada")

    def test_un_nombre_de_puros_espacios_tampoco_vale(self):
        respuesta = self.alta(nombre="   ")
        self.assertEqual(400, respuesta.status_code)
        self.assertEqual(1, len(self.pacientes()))

    def test_una_edad_imposible_se_frena_con_instruccion(self):
        respuesta = self.alta(nombre="Ana Rojas", edad=340)
        self.assertEqual(400, respuesta.status_code)
        self.assertIn("La edad", respuesta.get_json()["error"])
        self.assertEqual(1, len(self.pacientes()))

    def test_una_edad_que_no_es_numero_explica_que_dejarla_vacia(self):
        respuesta = self.alta(nombre="Ana Rojas", edad="sesenta")
        self.assertEqual(400, respuesta.status_code)
        self.assertIn("número", respuesta.get_json()["error"])

    def test_sin_cuerpo_no_revienta(self):
        respuesta = self.cliente.post("/api/pacientes")
        self.assertEqual(400, respuesta.status_code)
        self.assertIn("error", respuesta.get_json())

    def test_solo_con_el_nombre_alcanza(self):
        """Lo único obligatorio es el nombre (§15.4): el resto llega después."""
        respuesta = self.alta(nombre="Ana Rojas")
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        paciente = respuesta.get_json()["paciente"]
        self.assertEqual("EC-0002", paciente["codigo"])
        self.assertIsNone(paciente["cedula"])
        self.assertIsNone(paciente["edad"])


# --------------------------------------------------------------------------
# Ficha y antecedentes (dec. 3 a 6)
# --------------------------------------------------------------------------

class TestHistoriaFicha(BaseHistoriaApi):

    def test_arranca_en_null_y_se_llena_por_secciones(self):
        vacia = self.cliente.get(f"/api/pacientes/{self.paciente_id}/historia")
        self.assertEqual(vacia.status_code, 200)
        datos = vacia.get_json()
        self.assertIsNone(datos["historia"], "sin ficha todavía: null, no {}")
        self.assertEqual("EC-0001", datos["paciente"]["codigo"])
        self.assertEqual([], datos["consultas"])
        self.assertEqual([], datos["anexos"])
        self.assertEqual([], datos["mediciones"])

        primera = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/historia",
            json={"ocupacion": "Docente", "estado_civil": "Casada",
                  "tipo_sangre": "O+", "alergias": "Penicilina"})
        self.assertEqual(primera.status_code, 200, primera.get_json())
        self.assertEqual("Docente", primera.get_json()["historia"]["ocupacion"])

        # Guardar otra sección no pisa la anterior (pantalla plegable).
        segunda = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/historia",
            json={"fam_madre": "HTA", "fam_padre": "DM2"})
        historia = segunda.get_json()["historia"]
        self.assertEqual("Docente", historia["ocupacion"])
        self.assertEqual("Penicilina", historia["alergias"])
        self.assertEqual("HTA", historia["fam_madre"])

    def test_los_siete_numeradores_de_alimentacion(self):
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/historia",
            json={"alim_comidas_dia": 2, "alim_frutas_verduras": "4",
                  "alim_pollo": 3, "alim_pescado": 1, "alim_carnes_rojas": 2,
                  "alim_carbohidratos": 7, "alim_litros_agua": 3,
                  "habitacion": "Casa propia, servicios completos",
                  "actividad_fisica": "Caminata 3 veces por semana"})
        historia = respuesta.get_json()["historia"]
        self.assertEqual(2, historia["alim_comidas_dia"])
        self.assertEqual(4, historia["alim_frutas_verduras"])
        # Dec. 5: la vivienda es una nota libre, no doce casillas.
        self.assertEqual("Casa propia, servicios completos", historia["habitacion"])
        # El denominador impreso dice 2, pero si toma 3 litros se escribe 3.
        self.assertEqual(3, historia["alim_litros_agua"])

    def test_un_numerador_que_no_es_numero_explica_que_hacer(self):
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/historia",
            json={"alim_pollo": "bastante"})
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("Pollo", respuesta.get_json()["error"])

    def test_guardar_la_ficha_crea_la_carpeta_del_paciente(self):
        """Dec. 17: tener historia es tener carpeta propia."""
        self.assertFalse(self.carpeta_del_paciente().exists())
        self.cliente.post(f"/api/pacientes/{self.paciente_id}/historia",
                          json={"ocupacion": "Docente"})
        for sub in ("recipes", "informes", "anexos"):
            self.assertTrue((self.carpeta_del_paciente() / sub).is_dir(), sub)

    def test_mirar_la_historia_no_escribe_nada(self):
        """Abrir la historia para mirarla no puede crear carpetas ni filas."""
        self.cliente.get(f"/api/pacientes/{self.paciente_id}/historia")
        self.assertFalse(self.carpeta_del_paciente().exists())
        con = self.conexion()
        try:
            self.assertIsNone(basedatos.obtener_historia(con, self.paciente_id))
        finally:
            con.close()

    def test_paciente_inexistente_da_404(self):
        respuesta = self.cliente.get("/api/pacientes/9999/historia")
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("Volvé a buscarlo", respuesta.get_json()["error"])

    def test_el_buscador_de_pacientes_devuelve_el_codigo(self):
        """La pantalla de la historia muestra el EC-… ya en la lista (dec. 1).

        El médico busca al paciente teniendo a mano un récipe impreso, donde lo
        único inequívoco es el código: si la sugerencia no lo trae, tiene que
        elegir a ciegas entre dos personas del mismo apellido.
        """
        respuesta = self.cliente.get("/api/sugerencias/pacientes?q=Gonz")
        self.assertEqual(200, respuesta.status_code)
        primero = respuesta.get_json()["resultados"][0]
        self.assertEqual("EC-0001", primero["codigo"])


# --------------------------------------------------------------------------
# Consultas y signos vitales (dec. 3)
# --------------------------------------------------------------------------

class TestConsultas(BaseHistoriaApi):

    CONSULTA = {
        "fecha": "2026-08-18",
        "motivo": "Control de peso",
        "examen_fisico": "Buenas condiciones generales",
        "evolucion": "Refiere mejoría del sueño",
        "diagnostico": "Obesidad grado II",
        "plan": "Dieta y control en un mes",
        "signos": {"ta_sistolica": 120, "ta_diastolica": 80, "fc": 72,
                   "fr": 16, "temperatura": 36.5, "spo2": 98,
                   "peso": 97.9, "talla": 1.68},
    }

    def crear(self, **extra):
        cuerpo = {**self.CONSULTA, **extra}
        return self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/consultas", json=cuerpo)

    def test_crea_la_consulta_con_imc_y_tam_calculados(self):
        respuesta = self.crear()
        self.assertEqual(respuesta.status_code, 201, respuesta.get_json())
        consulta = respuesta.get_json()
        self.assertEqual("2026-08-18", consulta["fecha"])
        self.assertEqual("Control de peso", consulta["motivo"])
        signos = consulta["signos_vitales"]
        self.assertEqual(34.7, signos["imc"])       # 97,9 / 1,68²
        self.assertEqual(93.3, signos["tam"])       # (120 + 2×80) / 3
        self.assertEqual(98, signos["spo2"])

    def test_lo_que_el_medico_escribio_a_mano_gana(self):
        consulta = self.crear(signos={**self.CONSULTA["signos"], "imc": 33.0}).get_json()
        self.assertEqual(33.0, consulta["signos_vitales"]["imc"])

    def test_la_talla_en_centimetros_tambien_vale(self):
        consulta = self.crear(
            signos={"peso": 97.9, "talla": 168}).get_json()
        self.assertEqual(34.7, consulta["signos_vitales"]["imc"])

    def test_sin_fecha_es_hoy(self):
        from datetime import date
        cuerpo = {k: v for k, v in self.CONSULTA.items() if k != "fecha"}
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/consultas", json=cuerpo)
        self.assertEqual(date.today().isoformat(), respuesta.get_json()["fecha"])

    def test_una_consulta_sin_signos_no_inventa_ceros(self):
        consulta = self.crear(signos={}).get_json()
        self.assertIsNone(consulta["signos_vitales"])

    def test_editar_la_consulta_del_dia(self):
        creada = self.crear().get_json()
        respuesta = self.cliente.put(
            f"/api/consultas/{creada['id']}",
            json={**self.CONSULTA, "plan": "Se agrega vitamina D",
                  "signos": {**self.CONSULTA["signos"], "peso": 96.4}})
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        editada = respuesta.get_json()
        self.assertEqual(creada["id"], editada["id"])
        self.assertEqual("Se agrega vitamina D", editada["plan"])
        self.assertEqual(96.4, editada["signos_vitales"]["peso"])
        self.assertEqual(34.2, editada["signos_vitales"]["imc"], "el IMC se rehace")

        # Y sigue habiendo una sola consulta, no dos.
        historia = self.cliente.get(
            f"/api/pacientes/{self.paciente_id}/historia").get_json()
        self.assertEqual(1, len(historia["consultas"]))

    def test_editar_una_consulta_que_no_esta(self):
        respuesta = self.cliente.put("/api/consultas/9999", json=self.CONSULTA)
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("Actualizá la pantalla", respuesta.get_json()["error"])

    def test_un_signo_vital_absurdo_se_frena_con_instruccion(self):
        respuesta = self.crear(signos={"temperatura": 365})
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("La temperatura", respuesta.get_json()["error"])

    def test_la_coma_decimal_vale(self):
        consulta = self.crear(signos={"peso": "97,9", "talla": "1,68"}).get_json()
        self.assertEqual(97.9, consulta["signos_vitales"]["peso"])

    def test_la_historia_lista_las_consultas_con_sus_signos(self):
        self.crear()
        self.crear(fecha="2026-09-18", motivo="Control mensual")
        historia = self.cliente.get(
            f"/api/pacientes/{self.paciente_id}/historia").get_json()
        consultas = historia["consultas"]
        self.assertEqual(2, len(consultas))
        self.assertEqual("2026-09-18", consultas[0]["fecha"], "la más nueva primero")
        self.assertEqual(97.9, consultas[0]["signos_vitales"]["peso"])
        self.assertEqual(0, consultas[0]["cantidad_anexos"])


# --------------------------------------------------------------------------
# La bandeja de imágenes recientes (dec. 11, Parte C §4)
# --------------------------------------------------------------------------

class TestBandeja(BaseHistoriaApi):

    def sembrar(self) -> dict[str, Path]:
        """Tres carpetas, con una imagen nueva en cada una y una vieja."""
        archivos = {
            "descarga": imagen_jpeg(
                self.descargas / "WhatsApp Image 2026-08-18 at 3.14.48 PM.jpeg",
                color=(10, 120, 200)),
            "escritorio": imagen_jpeg(self.escritorio / "medicion.png",
                                      color=(200, 30, 30)),
            "entrada": imagen_jpeg(self.entrada / "control.webp",
                                   color=(20, 200, 90)),
            "vieja": imagen_jpeg(self.descargas / "foto-del-año-pasado.jpg",
                                 color=(90, 90, 90)),
        }
        envejecer(archivos["vieja"], 60)
        envejecer(archivos["descarga"], 0.1)
        envejecer(archivos["escritorio"], 2)
        envejecer(archivos["entrada"], 5)
        return archivos

    def test_muestra_lo_reciente_de_las_tres_carpetas_y_no_lo_viejo(self):
        archivos = self.sembrar()
        imagenes = self.bandeja()
        self.assertEqual(3, len(imagenes), imagenes)
        self.assertEqual(
            ["Descargas", "Escritorio", "Entrada"],
            [i["carpeta"] for i in imagenes], "de la más nueva a la más vieja")
        self.assertEqual(archivos["descarga"].name, imagenes[0]["nombre"])
        self.assertEqual(60, imagenes[0]["ancho"])
        self.assertEqual(90, imagenes[0]["alto"])
        self.assertNotIn("foto-del-año-pasado.jpg",
                         [i["nombre"] for i in imagenes])

    def test_el_token_no_dice_nada_de_la_ruta(self):
        self.sembrar()
        for imagen in self.bandeja():
            self.assertNotIn("\\", imagen["token"])
            self.assertNotIn("/", imagen["token"])
            self.assertNotIn(".jpeg", imagen["token"])
            self.assertGreaterEqual(len(imagen["token"]), 16)

    def test_la_fecha_es_la_del_archivo(self):
        from datetime import date
        archivos = self.sembrar()
        cuando = date.fromtimestamp(archivos["escritorio"].stat().st_mtime)
        por_nombre = {i["nombre"]: i for i in self.bandeja()}
        self.assertEqual(cuando.isoformat(),
                         por_nombre["medicion.png"]["fecha_archivo"])

    def test_la_miniatura_sale_en_jpeg(self):
        self.sembrar()
        token = self.bandeja()[0]["token"]
        respuesta = self.cliente.get(f"/api/bandeja/{token}/miniatura")
        self.assertEqual(200, respuesta.status_code)
        self.assertEqual("image/jpeg", respuesta.mimetype)
        with Image.open(io.BytesIO(respuesta.data)) as abierta:
            self.assertEqual("JPEG", abierta.format)
            self.assertLessEqual(max(abierta.size), rutas.LADO_MINIATURA)

    def test_un_token_inventado_da_404_y_no_cuenta_nada(self):
        respuesta = self.cliente.get("/api/bandeja/no-existe-este-token/miniatura")
        self.assertEqual(404, respuesta.status_code)
        error = respuesta.get_json()["error"]
        self.assertIn("Actualizá la bandeja", error)
        for filtracion in ("\\", "/", "Downloads", "Desktop", str(self.perfil)):
            self.assertNotIn(filtracion, error)

    def test_un_token_de_un_archivo_borrado_da_404(self):
        archivos = self.sembrar()
        token = self.bandeja()[0]["token"]
        archivos["descarga"].unlink()
        self.assertEqual(
            404, self.cliente.get(f"/api/bandeja/{token}/miniatura").status_code)

    def test_lo_ya_anexado_desaparece_de_la_bandeja(self):
        """Dec. 11: la bandeja se vacía sola, sin borrar un solo archivo."""
        archivos = self.sembrar()
        antes = self.bandeja()
        elegida = next(i for i in antes if i["nombre"] == "medicion.png")
        self.assertEqual(201, self.anexar(elegida["token"]).status_code)

        despues = [i["nombre"] for i in self.bandeja()]
        self.assertNotIn("medicion.png", despues)
        self.assertEqual(2, len(despues))
        self.assertTrue(archivos["escritorio"].is_file(),
                        "el original no se toca nunca")

    def test_la_misma_imagen_con_otro_nombre_tampoco_vuelve_a_aparecer(self):
        """La marca es el SHA-256, no el nombre del archivo."""
        self.sembrar()
        elegida = next(i for i in self.bandeja() if i["nombre"] == "medicion.png")
        self.anexar(elegida["token"])
        shutil.copyfile(self.escritorio / "medicion.png",
                        self.descargas / "copia (1).png")
        self.assertNotIn("copia (1).png", [i["nombre"] for i in self.bandeja()])

    def test_no_ofrece_lo_que_no_es_imagen(self):
        (self.descargas / "laboratorio.pdf").write_bytes(b"%PDF-1.4 no soy imagen")
        (self.descargas / "instalador.exe").write_bytes(b"MZ")
        (self.descargas / "rota.jpg").write_bytes(b"esto no es un JPEG")
        self.assertEqual([], self.bandeja())

    def test_la_carpeta_de_entrada_se_crea_sola(self):
        shutil.rmtree(self.entrada)
        self.assertEqual([], self.bandeja())
        self.assertTrue(self.entrada.is_dir())

    def test_el_boton_abre_la_carpeta_de_entrada(self):
        respuesta = self.cliente.post("/api/abrir-carpeta",
                                      json={"carpeta": "entrada"})
        self.assertEqual(200, respuesta.status_code, respuesta.get_json())
        self.assertTrue(self.entrada.is_dir())


# --------------------------------------------------------------------------
# Anexar (dec. 11, Parte C §5)
# --------------------------------------------------------------------------

class TestAnexos(BaseHistoriaApi):

    def sembrar_una(self, nombre: str = "medicion.jpg",
                    color: tuple[int, int, int] = (10, 120, 200)) -> tuple[str, Path]:
        archivo = imagen_jpeg(self.descargas / nombre, color=color)
        token = next(i["token"] for i in self.bandeja() if i["nombre"] == nombre)
        return token, archivo

    def test_anexar_por_token_copia_el_original_byte_por_byte(self):
        token, origen = self.sembrar_una()
        antes = origen.read_bytes()

        respuesta = self.anexar(token, tipo="medicion", nota="Báscula del paciente")
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        anexo = respuesta.get_json()

        destino = (self.carpeta_del_paciente() / "anexos"
                   / "2026-08-14_medicion_01.jpg")
        self.assertTrue(destino.is_file())
        self.assertEqual(antes, destino.read_bytes(), "la copia es idéntica")
        self.assertTrue(origen.is_file(), "el original nunca se mueve ni se borra")
        self.assertEqual(antes, origen.read_bytes())

        self.assertEqual("2026-08-14_medicion_01.jpg", anexo["nombre"])
        self.assertEqual("medicion", anexo["tipo"])
        self.assertEqual("Báscula del paciente", anexo["nota"])
        self.assertEqual(sha256_de(origen), anexo["sha256"])
        self.assertEqual(60, anexo["ancho_px"])
        self.assertEqual(90, anexo["alto_px"])
        self.assertEqual(len(antes), anexo["bytes"])
        self.assertEqual(
            "pacientes/EC-0001_Maria-Gonzalez/anexos/2026-08-14_medicion_01.jpg",
            anexo["ruta_relativa"], "ruta relativa: mover la carpeta no rompe nada")

    def test_deja_la_miniatura_al_lado(self):
        token, _ = self.sembrar_una()
        self.anexar(token)
        thumb = (self.carpeta_del_paciente() / "anexos"
                 / "2026-08-14_medicion_01.thumb.jpg")
        self.assertTrue(thumb.is_file())
        with Image.open(thumb) as abierta:
            self.assertEqual("JPEG", abierta.format)

    def test_dos_anexos_el_mismo_dia_no_se_pisan(self):
        primero, _ = self.sembrar_una("una.jpg")
        self.anexar(primero)
        # Otro color: otra imagen y otro hash, si no la bandeja la esconde.
        segundo, _ = self.sembrar_una("otra.jpg", color=(1, 2, 3))
        respuesta = self.anexar(segundo)
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        nombres = [p.name for p in self.anexos_en_disco()]
        self.assertIn("2026-08-14_medicion_01.jpg", nombres)
        self.assertIn("2026-08-14_medicion_02.jpg", nombres)

    def test_la_fecha_de_la_medicion_manda_sobre_la_del_archivo(self):
        """Probado en el ejemplo real: cuatro días de diferencia."""
        token, origen = self.sembrar_una()
        envejecer(origen, 4)
        self.anexar(token, fecha="2026-08-14")
        self.assertEqual(["2026-08-14_medicion_01.jpg",
                          "2026-08-14_medicion_01.thumb.jpg"],
                         [p.name for p in self.anexos_en_disco()])

    def test_sin_fecha_no_se_anexa(self):
        token, _ = self.sembrar_una()
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos", json={"token": token})
        self.assertEqual(400, respuesta.status_code)
        self.assertIn("Confirmá la fecha", respuesta.get_json()["error"])
        self.assertFalse((self.carpeta_del_paciente() / "anexos").exists())

    def test_un_tipo_que_no_existe_ofrece_los_que_hay(self):
        token, _ = self.sembrar_una()
        respuesta = self.anexar(token, tipo="radiografía")
        self.assertEqual(400, respuesta.status_code)
        self.assertIn("Laboratorio", respuesta.get_json()["error"])

    def test_token_invalido_da_404_sin_filtrar_rutas(self):
        respuesta = self.anexar("token-de-fantasia")
        self.assertEqual(404, respuesta.status_code)
        error = respuesta.get_json()["error"]
        self.assertIn("Actualizá la bandeja", error)
        self.assertNotIn(str(self.perfil), error)

    def test_una_ruta_del_cliente_no_se_acepta_como_token(self):
        """El token es la única llave: una ruta no abre nada."""
        secreto = self.carpeta / "secreto.jpg"
        imagen_jpeg(secreto)
        for intento in (str(secreto), "../../secreto.jpg", "C:/Windows/win.ini"):
            respuesta = self.anexar(intento)
            self.assertEqual(404, respuesta.status_code, intento)
        self.assertFalse((self.carpeta_del_paciente() / "anexos").exists())

    def test_anexar_por_multipart(self):
        """El botón «Adjuntar imagen…», que es la salida de emergencia."""
        origen = imagen_jpeg(self.carpeta / "suelta" / "estudio.png",
                             ancho=80, alto=40)
        datos = {
            "archivo": (io.BytesIO(origen.read_bytes()), "estudio.png"),
            "fecha_medicion": "2026-09-01",
            "tipo": "laboratorio",
            "nota": "Perfil 20",
        }
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos",
            data=datos, content_type="multipart/form-data")
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        anexo = respuesta.get_json()
        self.assertEqual("2026-09-01_laboratorio_01.png", anexo["nombre"])
        self.assertEqual("laboratorio", anexo["tipo"])
        destino = self.carpeta_del_paciente() / "anexos" / anexo["nombre"]
        self.assertEqual(origen.read_bytes(), destino.read_bytes())
        self.assertEqual(80, anexo["ancho_px"])

    def test_multipart_con_medicion_suelta(self):
        origen = imagen_jpeg(self.carpeta / "suelta" / "bascula.jpg")
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos",
            data={"archivo": (io.BytesIO(origen.read_bytes()), "bascula.jpg"),
                  "fecha_medicion": "2026-08-14",
                  "peso": "97,9", "imc": "34.6", "grasa_pct": "44.3"},
            content_type="multipart/form-data")
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        medicion = respuesta.get_json()["medicion"]
        self.assertEqual(97.9, medicion["peso"])
        self.assertEqual(44.3, medicion["grasa_pct"])

    def test_un_archivo_que_no_se_puede_anexar(self):
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos",
            data={"archivo": (io.BytesIO(b"MZ..."), "instalador.exe"),
                  "fecha_medicion": "2026-08-14"},
            content_type="multipart/form-data")
        self.assertEqual(400, respuesta.status_code)
        self.assertIn("EXE", respuesta.get_json()["error"])

    def test_un_pdf_de_laboratorio_si_se_anexa(self):
        """Dec. 11: acepta PDF. No tiene miniatura y no pasa nada."""
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos",
            data={"archivo": (io.BytesIO(b"%PDF-1.4\n%fin"), "hematologia.pdf"),
                  "fecha_medicion": "2026-08-14", "tipo": "laboratorio"},
            content_type="multipart/form-data")
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        anexo = respuesta.get_json()
        self.assertEqual("2026-08-14_laboratorio_01.pdf", anexo["nombre"])
        self.assertIsNone(anexo["ancho_px"])
        miniatura = self.cliente.get(f"/api/anexos/{anexo['id']}/miniatura")
        self.assertEqual(404, miniatura.status_code)
        self.assertIn("PDF", miniatura.get_json()["error"])

    def test_la_misma_imagen_dos_veces_da_409(self):
        token, _ = self.sembrar_una()
        self.assertEqual(201, self.anexar(token).status_code)
        de_nuevo = self.anexar(token, fecha="2026-08-20")
        self.assertEqual(409, de_nuevo.status_code)
        error = de_nuevo.get_json()["error"]
        self.assertIn("María González", error)
        self.assertIn("EC-0001", error)
        self.assertIn("2026-08-14", error)
        self.assertEqual(2, len(self.anexos_en_disco()),
                         "no quedó una copia de más")

    def test_la_misma_imagen_en_otro_paciente_tambien_avisa(self):
        token, _ = self.sembrar_una()
        self.anexar(token)
        con = self.conexion()
        try:
            otro = basedatos.crear_paciente(con, "Pedro Ruiz")
            con.commit()
        finally:
            con.close()
        respuesta = self.cliente.post(
            f"/api/pacientes/{otro}/anexos",
            json={"token": token, "fecha_medicion": "2026-08-14"})
        self.assertEqual(409, respuesta.status_code)
        self.assertIn("María González", respuesta.get_json()["error"])

    def test_anexo_con_medicion_y_consulta(self):
        """Dec. 13: los valores clave son opcionales y viajan con el anexo."""
        consulta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/consultas",
            json={"fecha": "2026-08-14", "motivo": "Control"}).get_json()
        token, _ = self.sembrar_una()
        respuesta = self.anexar(
            token, consulta_id=consulta["id"],
            medicion={"peso": 97.9, "imc": 34.6, "grasa_pct": 44.3,
                      "musculo_kg": 30.2, "grasa_visceral": 19})
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        anexo = respuesta.get_json()
        self.assertEqual(consulta["id"], anexo["consulta_id"])
        medicion = anexo["medicion"]
        self.assertEqual(97.9, medicion["peso"])
        self.assertEqual(19.0, medicion["grasa_visceral"])
        self.assertEqual(anexo["id"], medicion["anexo_id"])
        self.assertEqual("2026-08-14", medicion["fecha"])

        historia = self.cliente.get(
            f"/api/pacientes/{self.paciente_id}/historia").get_json()
        self.assertEqual(1, len(historia["anexos"]))
        self.assertEqual(1, len(historia["mediciones"]))
        self.assertEqual(1, historia["consultas"][0]["cantidad_anexos"])

    def test_un_anexo_sin_medicion_no_deja_una_fila_vacia(self):
        token, _ = self.sembrar_una()
        self.anexar(token)
        historia = self.cliente.get(
            f"/api/pacientes/{self.paciente_id}/historia").get_json()
        self.assertEqual([], historia["mediciones"])
        self.assertIsNone(self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos",
            json={"token": token}).get_json().get("medicion"))

    def test_una_consulta_de_otro_paciente_no_se_puede_colgar(self):
        con = self.conexion()
        try:
            otro = basedatos.crear_paciente(con, "Pedro Ruiz")
            consulta_id = basedatos.crear_consulta(con, otro, fecha="2026-08-14")
            con.commit()
        finally:
            con.close()
        token, _ = self.sembrar_una()
        respuesta = self.anexar(token, consulta_id=consulta_id)
        self.assertEqual(400, respuesta.status_code)
        self.assertIn("no es de este paciente", respuesta.get_json()["error"])

    def test_se_sirve_la_imagen_y_la_miniatura_del_anexo(self):
        token, origen = self.sembrar_una()
        anexo = self.anexar(token).get_json()

        imagen = self.cliente.get(f"/api/anexos/{anexo['id']}/imagen")
        self.assertEqual(200, imagen.status_code)
        self.assertEqual("image/jpeg", imagen.mimetype)
        self.assertEqual(origen.read_bytes(), imagen.data)

        miniatura = self.cliente.get(f"/api/anexos/{anexo['id']}/miniatura")
        self.assertEqual(200, miniatura.status_code)
        with Image.open(io.BytesIO(miniatura.data)) as abierta:
            self.assertLessEqual(max(abierta.size), rutas.LADO_MINIATURA)

    def test_la_miniatura_se_rehace_si_alguien_la_borro(self):
        token, _ = self.sembrar_una()
        anexo = self.anexar(token).get_json()
        thumb = (self.carpeta_del_paciente() / "anexos"
                 / "2026-08-14_medicion_01.thumb.jpg")
        thumb.unlink()
        self.assertEqual(
            200, self.cliente.get(f"/api/anexos/{anexo['id']}/miniatura").status_code)
        self.assertTrue(thumb.is_file(), "y queda escrita para la próxima")

    def test_un_anexo_cuyo_archivo_desaparecio(self):
        token, _ = self.sembrar_una()
        anexo = self.anexar(token).get_json()
        (self.carpeta_del_paciente() / "anexos"
         / "2026-08-14_medicion_01.jpg").unlink()
        respuesta = self.cliente.get(f"/api/anexos/{anexo['id']}/imagen")
        self.assertEqual(404, respuesta.status_code)
        self.assertIn("respaldo", respuesta.get_json()["error"])

    def test_anexo_inexistente(self):
        respuesta = self.cliente.get("/api/anexos/9999/imagen")
        self.assertEqual(404, respuesta.status_code)

    def test_un_archivo_que_dice_ser_imagen_pero_no_lo_es(self):
        """Un `.jpg` cortado a la mitad no puede entrar a la historia.

        Si se copiara, quedaría un anexo que no se ve, no se imprime y no tiene
        medidas: mejor frenarlo antes de tocar el disco.
        """
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/anexos",
            data={"archivo": (io.BytesIO(b"esto no es una imagen"), "medicion.jpg"),
                  "fecha_medicion": "2026-08-14"},
            content_type="multipart/form-data")
        self.assertEqual(400, respuesta.status_code, respuesta.get_json())
        self.assertIn("a medio descargar", respuesta.get_json()["error"])
        self.assertEqual([], self.anexos_en_disco(),
                         "no se copió nada a la carpeta del paciente")

    def test_el_boton_de_abrirlo_con_el_visor_de_windows(self):
        token, _ = self.sembrar_una()
        anexo = self.anexar(token).get_json()
        # Con RECIPES_ABRIR_PDF=0 no se abre nada de verdad, pero la ruta
        # existe y responde: es lo que la pantalla necesita saber.
        respuesta = self.cliente.post(f"/api/anexos/{anexo['id']}/abrir")
        self.assertEqual(200, respuesta.status_code, respuesta.get_json())
        self.assertEqual(404, self.cliente.post("/api/anexos/9999/abrir").status_code)


# --------------------------------------------------------------------------
# Evolución (dec. 13 ampliada)
# --------------------------------------------------------------------------

class TestEvolucion(BaseHistoriaApi):

    def test_combina_mediciones_y_consultas_rotulando_la_fuente(self):
        self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/consultas",
            json={"fecha": "2026-07-01", "motivo": "Primera",
                  "signos": {"peso": 99.0, "talla": 1.68}})
        self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/consultas",
            json={"fecha": "2026-09-01", "motivo": "Control",
                  "signos": {"peso": 95.0, "talla": 1.68}})

        imagen_jpeg(self.descargas / "bascula.jpg")
        token = next(i["token"] for i in self.bandeja())
        self.anexar(token, fecha="2026-08-14",
                    medicion={"peso": 97.9, "imc": 34.6, "grasa_pct": 44.3,
                              "musculo_kg": 30.2, "grasa_visceral": 19})

        respuesta = self.cliente.get(
            f"/api/pacientes/{self.paciente_id}/evolucion")
        self.assertEqual(200, respuesta.status_code)
        series = respuesta.get_json()["series"]
        self.assertEqual(
            sorted(("peso", "imc", "grasa_pct", "musculo_kg", "grasa_visceral")),
            sorted(series))

        peso = series["peso"]
        self.assertEqual(["2026-07-01", "2026-08-14", "2026-09-01"],
                         [p["fecha"] for p in peso], "en orden cronológico")
        self.assertEqual([99.0, 97.9, 95.0], [p["valor"] for p in peso])
        self.assertEqual(["consulta", "medicion", "consulta"],
                         [p["fuente"] for p in peso])

        # El IMC sale de las dos fuentes; el % de grasa, solo de la medición.
        self.assertEqual(3, len(series["imc"]))
        self.assertEqual([44.3], [p["valor"] for p in series["grasa_pct"]])
        self.assertEqual("medicion", series["grasa_pct"][0]["fuente"])

    def test_el_pdf_de_la_historia_lleva_los_graficos(self):
        """Dec. 13 ampliada: la tendencia va TAMBIÉN adentro del PDF.

        `pdf_historia` sabe dibujar los mini-gráficos desde `datos["evolucion"]`,
        pero eso solo sirve si el endpoint del PDF se los pasa: sin este test,
        el papel puede salir sin la sección y nadie se entera hasta imprimirlo.
        """
        self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/consultas",
            json={"fecha": "2026-07-01", "motivo": "Primera",
                  "signos": {"peso": 99.0, "talla": 1.68}})
        imagen_jpeg(self.descargas / "bascula.jpg")
        token = next(i["token"] for i in self.bandeja())
        self.anexar(token, fecha="2026-08-14",
                    medicion={"peso": 97.9, "imc": 34.6, "grasa_pct": 44.3,
                              "musculo_kg": 30.2, "grasa_visceral": 19})
        imagen_jpeg(self.descargas / "bascula2.jpg", color=(9, 99, 199))
        token2 = next(i["token"] for i in self.bandeja()
                      if i["nombre"] == "bascula2.jpg")
        self.anexar(token2, fecha="2026-09-14",
                    medicion={"peso": 95.1, "imc": 33.7, "grasa_pct": 42.0,
                              "musculo_kg": 30.9, "grasa_visceral": 17})

        recibido: dict = {}
        real = pdf_historia.generar_historia

        def espiar(datos, destino, **extra):
            recibido.update(datos)
            return real(datos, destino, **extra)

        with unittest.mock.patch.object(pdf_historia, "generar_historia", espiar):
            respuesta = self.cliente.get(
                f"/api/pacientes/{self.paciente_id}/historia/pdf")
        self.assertEqual(200, respuesta.status_code)
        self.assertTrue(respuesta.data.startswith(b"%PDF"))

        series = recibido.get("evolucion") or {}
        self.assertEqual(
            sorted(("peso", "imc", "grasa_pct", "musculo_kg", "grasa_visceral")),
            sorted(series), "el PDF recibe las cinco series, como la pantalla")
        self.assertEqual(["consulta", "medicion", "medicion"],
                         [p["fuente"] for p in series["peso"]])

        # Y lo que el compositor de verdad va a dibujar con eso: las cinco.
        dibujadas = [titulo for titulo, _, _ in
                     pdf_historia._series_evolucion(recibido)]
        self.assertEqual(["Peso (kg)", "IMC", "Grasa (%)", "Músculo (kg)",
                          "Grasa visceral"], dibujadas)

    def test_sin_datos_devuelve_las_cinco_series_vacias(self):
        series = self.cliente.get(
            f"/api/pacientes/{self.paciente_id}/evolucion").get_json()["series"]
        self.assertEqual(5, len(series))
        self.assertTrue(all(puntos == [] for puntos in series.values()))

    def test_paciente_inexistente(self):
        self.assertEqual(
            404, self.cliente.get("/api/pacientes/9999/evolucion").status_code)


# --------------------------------------------------------------------------
# Carpeta de entrada y acceso directo (dec. 11, pieza 3)
# --------------------------------------------------------------------------

class TestCarpetaDeEntrada(unittest.TestCase):

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_entrada_"))
        self._perfil = os.environ.get("USERPROFILE")
        self._onedrive = os.environ.get("ONEDRIVE")

    def tearDown(self) -> None:
        for clave, valor in (("USERPROFILE", self._perfil),
                             ("ONEDRIVE", self._onedrive)):
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def test_preparar_carpeta_datos_crea_entrada(self):
        destino = main.preparar_carpeta_datos(self.carpeta / "Recipes")
        self.assertTrue((destino / "entrada").is_dir())
        # Idempotente: correrlo dos veces no rompe ni pisa nada.
        (destino / "entrada" / "medicion.jpg").write_bytes(b"x")
        main.preparar_carpeta_datos(destino)
        self.assertTrue((destino / "entrada" / "medicion.jpg").is_file())

    def test_el_acceso_directo_se_intenta_una_sola_vez(self):
        """Falle o no, no se reintenta en cada arranque (dec. 11, pieza 3)."""
        perfil = self.carpeta / "perfil"
        (perfil / "Desktop").mkdir(parents=True)
        os.environ["USERPROFILE"] = str(perfil)
        os.environ.pop("ONEDRIVE", None)

        dir_datos = main.preparar_carpeta_datos(self.carpeta / "Recipes")
        con = basedatos.inicializar(dir_datos / "datos" / "recipes.db")
        try:
            primero = main.crear_acceso_entrada(con, dir_datos)
            self.assertIn(primero, ("1", "fallo"))
            self.assertTrue(basedatos.obtener_config(con, main.CLAVE_ACCESO_ENTRADA))
            self.assertEqual("ya", main.crear_acceso_entrada(con, dir_datos))
            if primero == "1":
                self.assertTrue(
                    (perfil / "Desktop" / main.NOMBRE_ACCESO_ENTRADA).is_file())
        finally:
            con.close()

    def test_sin_escritorio_no_rompe_el_arranque(self):
        perfil = self.carpeta / "sin-escritorio"
        perfil.mkdir()
        os.environ["USERPROFILE"] = str(perfil)
        os.environ.pop("ONEDRIVE", None)
        dir_datos = main.preparar_carpeta_datos(self.carpeta / "Recipes2")
        con = basedatos.inicializar(dir_datos / "datos" / "recipes.db")
        try:
            self.assertEqual("fallo", main.crear_acceso_entrada(con, dir_datos))
            # No se anota: un Escritorio que hoy no está puede ser un OneDrive
            # que todavía no montó, y mañana el acceso directo sí se puede
            # crear. Lo que no se reintenta es lo que PowerShell rechazó.
            self.assertIsNone(
                basedatos.obtener_config(con, main.CLAVE_ACCESO_ENTRADA))
            self.assertEqual([], sorted(perfil.iterdir()),
                             "no se crea ninguna carpeta en el perfil del médico")
        finally:
            con.close()

    def test_si_powershell_no_deja_no_se_reintenta(self):
        """Lo que falló de verdad queda anotado y no molesta en cada arranque."""
        perfil = self.carpeta / "con-escritorio"
        (perfil / "Desktop").mkdir(parents=True)
        os.environ["USERPROFILE"] = str(perfil)
        os.environ.pop("ONEDRIVE", None)
        dir_datos = main.preparar_carpeta_datos(self.carpeta / "Recipes3")
        con = basedatos.inicializar(dir_datos / "datos" / "recipes.db")

        def explotar(*args, **kwargs):
            raise OSError("PowerShell restringido por política")

        try:
            with unittest.mock.patch.object(main.subprocess, "run", explotar):
                self.assertEqual("fallo", main.crear_acceso_entrada(con, dir_datos))
            self.assertEqual(
                "fallo", basedatos.obtener_config(con, main.CLAVE_ACCESO_ENTRADA))
            self.assertEqual("ya", main.crear_acceso_entrada(con, dir_datos),
                             "no se vuelve a lanzar PowerShell en cada arranque")
            self.assertTrue((dir_datos / "entrada").is_dir(),
                            "la carpeta de entrada queda igual, con acceso o sin él")
        finally:
            con.close()


# --------------------------------------------------------------------------
# El camino entero: alta en la Historia → récipe con ese paciente (dec. 18)
# --------------------------------------------------------------------------

class TestRecipeDesdeLaHistoria(BaseHistoriaApi):
    """Lo que pasa cuando el récipe arranca con el paciente de la historia.

    La pantalla manda el **id** del paciente abierto además del nombre (es lo
    que arma `cuerpoRecipe()` mientras se ve la banda «Récipe para EC-000N ·
    Fulano»). Ese id es lo único que garantiza que el récipe se archive bajo la
    persona correcta: sin él, dos homónimos o un nombre corregido a mano
    terminan repartiendo los récipes entre dos fichas. Acá se prueba el
    encadenado completo contra la API, que es como corre en la máquina del
    médico: alta → récipe → dónde quedó.
    """

    NUEVO = {"nombre": "Rosa María Peña", "cedula": "V-12345678", "edad": 41,
             "fecha_nacimiento": "1985-03-02", "sexo": "Femenino",
             "telefono": "0414-1112233"}

    ITEMS = [{"medicamento": "Losartán", "presentacion": "50 mg",
              "cantidad": "30 tabletas", "dosis": "1 diaria",
              "indicaciones": "Con el desayuno"}]

    # Esta clase es la única del módulo que emite PDF, y fpdf subsetea las Lato
    # con fontTools dejándole el `.ttf` abierto al recolector. El filtro por
    # test de `BaseHistoriaApi` no alcanza: lo que se recolecta tarde sale como
    # ResourceWarning **en medio del módulo siguiente**, que no lo filtra, y
    # ensucia una salida que el resto del proyecto mantiene limpia. Así que el
    # filtro dura toda la clase y la recolección se fuerza adentro.

    @classmethod
    def setUpClass(cls) -> None:
        cls._silencio = warnings.catch_warnings()
        cls._silencio.__enter__()
        warnings.filterwarnings("ignore", category=ResourceWarning)

    @classmethod
    def tearDownClass(cls) -> None:
        gc.collect()
        cls._silencio.__exit__(None, None, None)

    def tearDown(self) -> None:
        super().tearDown()
        # La app y su cliente son los que sostienen lo que fpdf dejó abierto.
        self.cliente = None
        self.app = None
        gc.collect()

    def dar_de_alta(self) -> dict:
        respuesta = self.cliente.post("/api/pacientes", json=self.NUEVO)
        self.assertEqual(201, respuesta.status_code, respuesta.get_json())
        return respuesta.get_json()["paciente"]

    def cuerpo_de_la_banda(self, paciente: dict, **cambios) -> dict:
        """El JSON tal cual lo arma `cuerpoRecipe()` con la banda puesta."""
        bloque = {
            "nombre": paciente["nombre"],
            "cedula": paciente["cedula"],
            "edad": paciente["edad"],
            "fecha_nacimiento": paciente["fecha_nacimiento"],
            "sexo": paciente["sexo"],
            "telefono": paciente["telefono"],
            "id": paciente["id"],
        }
        bloque.update(cambios)
        return {"paciente": bloque, "diagnostico": "Control", "notas": "",
                "items": self.ITEMS, "indicaciones_generales": "Dieta baja en sal"}

    def recipes(self) -> list[dict]:
        con = self.conexion()
        try:
            return [dict(f) for f in
                    con.execute("SELECT * FROM recipes ORDER BY id")]
        finally:
            con.close()

    def cuantos_pacientes(self) -> int:
        con = self.conexion()
        try:
            return con.execute("SELECT COUNT(*) FROM pacientes").fetchone()[0]
        finally:
            con.close()

    def test_el_recipe_de_la_banda_queda_bajo_el_paciente_de_la_historia(self):
        paciente = self.dar_de_alta()
        antes = self.cuantos_pacientes()

        respuesta = self.cliente.post(
            "/api/recipes", json=self.cuerpo_de_la_banda(paciente))
        self.assertEqual(200, respuesta.status_code, respuesta.get_json())
        datos = respuesta.get_json()

        # El código impreso es el del paciente, el mismo del alta (dec. 2).
        self.assertEqual(paciente["codigo"], datos["codigo"])

        emitidos = self.recipes()
        self.assertEqual(1, len(emitidos))
        self.assertEqual(paciente["id"], emitidos[0]["paciente_id"],
                         "el récipe quedó archivado bajo otro paciente")
        self.assertEqual(antes, self.cuantos_pacientes(),
                         "el récipe creó un paciente en vez de usar el abierto")

        # Y el PDF cayó en la carpeta del paciente (dec. 17), no en `pdf\`.
        ruta = Path(datos["ruta_pdf"])
        self.assertTrue(ruta.is_file(), ruta)
        self.assertEqual(
            self.dir_datos / "pacientes" / "EC-0002_Rosa-Maria-Pena" / "recipes",
            ruta.parent)

    def test_con_el_id_puesto_un_nombre_distinto_no_abre_otra_ficha(self):
        """La banda manda el id: el texto del campo ya no decide nada.

        Pasa de verdad: el médico corrige la tilde del apellido antes de
        imprimir. Si mandara solo el nombre, ese récipe arrancaría una segunda
        ficha con el mismo paciente adentro.
        """
        paciente = self.dar_de_alta()
        respuesta = self.cliente.post("/api/recipes", json=self.cuerpo_de_la_banda(
            paciente, nombre="Rosa Maria Pena"))
        self.assertEqual(200, respuesta.status_code, respuesta.get_json())
        self.assertEqual(paciente["codigo"], respuesta.get_json()["codigo"])
        self.assertEqual(2, self.cuantos_pacientes(),
                         "María del setUp y Rosa: nadie más")
        self.assertEqual([paciente["id"]],
                         [r["paciente_id"] for r in self.recipes()])

    def test_el_recipe_rapido_sin_historia_sigue_funcionando(self):
        """Dec. 18: el campo de paciente del récipe sigue valiendo solo.

        Sin abrir ninguna historia y sin id: solo el nombre, como en la 1.x. El
        paciente se crea al vuelo, con su código y su carpeta, y el PDF sale.
        """
        antes = self.cuantos_pacientes()
        respuesta = self.cliente.post("/api/recipes", json={
            "paciente": {"nombre": "Juan Sin Historia", "cedula": "",
                         "edad": None, "fecha_nacimiento": None,
                         "sexo": None, "telefono": None},
            "diagnostico": "", "notas": "",
            "items": [{"medicamento": "Ibuprofeno", "presentacion": "400 mg",
                       "cantidad": "20 tabletas", "dosis": "c/8h",
                       "indicaciones": ""}],
            "indicaciones_generales": "",
        })
        self.assertEqual(200, respuesta.status_code, respuesta.get_json())
        datos = respuesta.get_json()
        self.assertEqual("EC-0002", datos["codigo"])
        self.assertEqual(antes + 1, self.cuantos_pacientes())
        self.assertTrue(Path(datos["ruta_pdf"]).is_file())
        self.assertEqual(
            self.dir_datos / "pacientes" / "EC-0002_Juan-Sin-Historia" / "recipes",
            Path(datos["ruta_pdf"]).parent)

    def test_el_sexo_que_manda_el_alta_arma_la_frase_del_informe(self):
        """Dec. 10 y 18: lo que se elige en el alta tiene que servirle al informe.

        La pantalla ofrece «Femenino»/«Masculino» y `frase_inicial` mira la
        primera letra. Si alguien cambiara el `value` del `<select>` por «F» o
        por «femenino» nadie se enteraría hasta leer un informe que empieza
        «Se trata de paciente de 41 años».
        """
        paciente = self.dar_de_alta()
        respuesta = self.cliente.get(
            f"/api/pacientes/{paciente['id']}/frase-inicial?motivo=aumento de peso")
        self.assertEqual(200, respuesta.status_code)
        self.assertEqual(
            "Se trata de paciente femenino de 41 años de edad, quien consulta "
            "por presentar aumento de peso.",
            respuesta.get_json()["frase"])


if __name__ == "__main__":
    unittest.main()
