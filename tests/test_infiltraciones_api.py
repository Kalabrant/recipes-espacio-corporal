"""Tests de la API del mapa de infiltraciones (`rutas.py`, contrato 2.1 §5).

Dos cosas se prueban acá, y las dos son de fondo:

1. **La sesión de mapeo es un documento que se reabre.** A diferencia del
   récipe, el médico marca los puntos mientras infiltra y completa dosis y
   lotes después, así que `PUT` es parte del flujo normal: tiene que devolver
   los mismos puntos que se guardaron y escribir un PDF **nuevo** sin pisar el
   anterior (§0.5).
2. **Los límites del contrato §5 se hacen respetar con un mensaje que el
   médico pueda seguir.** 200 puntos, 20 productos, coordenadas en `[0, 1]`,
   dosis hasta 999, la vista tiene que existir y cada punto tiene que apuntar a
   un producto de la sesión.

Y una tercera que no es clínica pero sí seria: las láminas se sirven por **lista
blanca de nombres**, así que un nombre de archivo que no sea uno de los dos no
tiene por dónde entrar, ni siquiera escrito como un recorrido de directorios.

Como en `test_rutas.py`: cliente de Flask, carpeta de datos temporal, PDF de
verdad y nada que se abra en el escritorio.

Se corre con:  py -3 -m pytest tests/test_infiltraciones_api.py -q
"""

from __future__ import annotations

import copy
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
import pdf_infiltraciones  # noqa: E402
import rutas  # noqa: E402


PRODUCTOS = [
    {"id": "p1", "nombre": "Toxina A — marca 1", "tipo": "toxina",
     "unidad": "U", "color": "#D92B2B", "lote": "TX-7741", "caducidad": ""},
    {"id": "p3", "nombre": "AH baja densidad", "tipo": "relleno",
     "unidad": "ml", "color": "#2456C4", "lote": "AH-2210", "caducidad": ""},
]

#: Una sesión chica pero completa: toxina en el tercio superior, relleno en el
#: contorno mandibular y un punto marcado que NO se infiltró (sin producto).
PUNTOS = [
    {"orden": 1, "x": 0.4986, "y": 0.3681, "lado": "C",
     "zona": "Glabela — prócer", "plantillaId": "procer",
     "productoId": "p1", "dosis": 4, "notas": "intramuscular"},
    {"orden": 2, "x": 0.6351, "y": 0.2109, "lado": "I",
     "zona": "Frontal — línea alta", "plantillaId": "frontal-alto-i",
     "productoId": "p1", "dosis": 2, "notas": ""},
    {"orden": 3, "x": 0.6264, "y": 0.7980, "lado": "I",
     "zona": "Línea mandibular / prejowl", "plantillaId": "prejowl-i",
     "productoId": "p3", "dosis": 0.4, "notas": "cánula 25G"},
    {"orden": 4, "x": 0.5453, "y": 0.7921, "lado": "I",
     "zona": "Mentoniano", "plantillaId": "mentoniano-i",
     "productoId": "", "dosis": "", "notas": "marcado, no se infiltró"},
]

SESION = {
    "fecha": "2026-08-26",
    "vista": "mujer-frontal",
    "calibracion": {"pupilaIzq": [0.3313, 0.4133],
                    "pupilaDer": [0.664, 0.4172],
                    "menton": [0.500, 0.829]},
    "productos": PRODUCTOS,
    "puntos": PUNTOS,
    "observaciones": "Se reserva el retoque de la cola de ceja para el control.",
}


def sesion(**cambios):
    """Una copia de la sesión de referencia con lo que se quiera pisar."""
    datos = copy.deepcopy(SESION)
    datos.update(cambios)
    return datos


class BaseApp(unittest.TestCase):
    """App real sobre una carpeta temporal, sin abrir nada en el escritorio."""

    def setUp(self) -> None:
        # fpdf subsetea las Lato con fontTools y le deja archivos sin cerrar al
        # recolector: son ResourceWarning de una dependencia, no de la app.
        gestor = warnings.catch_warnings()
        gestor.__enter__()
        self.addCleanup(gestor.__exit__, None, None, None)
        warnings.filterwarnings("ignore", category=ResourceWarning)

        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_infiltra_"))
        # Se registra primero para que corra último, con las conexiones ya
        # cerradas: en Windows, con `recipes.db` tomado, el `rmtree` fallaba.
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

    def alta_paciente(self, nombre="Ana Gómez", **extra):
        respuesta = self.cliente.post("/api/pacientes", json={
            "nombre": nombre, "edad": 38, **extra})
        self.assertEqual(respuesta.status_code, 201, respuesta.get_json())
        return respuesta.get_json()["paciente"]

    def crear(self, paciente_id=None, cuerpo=None, esperado=201):
        if paciente_id is None:
            paciente_id = self.alta_paciente()["id"]
        respuesta = self.cliente.post(
            f"/api/pacientes/{paciente_id}/infiltraciones",
            json=SESION if cuerpo is None else cuerpo)
        self.assertEqual(respuesta.status_code, esperado, respuesta.get_json())
        return respuesta.get_json()

    def conexion(self):
        return basedatos.inicializar(self.dir_datos / "datos" / "recipes.db")


# --------------------------------------------------------------------------
# El catálogo: todo lo que la pestaña necesita para dibujar el mapa
# --------------------------------------------------------------------------

class TestCatalogo(BaseApp):

    def setUp(self) -> None:
        super().setUp()
        respuesta = self.cliente.get("/api/infiltraciones/catalogo")
        self.assertEqual(respuesta.status_code, 200)
        self.catalogo = respuesta.get_json()

    def test_trae_las_cinco_partes(self):
        self.assertEqual(
            set(self.catalogo),
            {"vistas", "puntos", "plantillas", "zonas", "productos"})

    def test_las_dos_vistas_con_su_calibracion_de_fabrica(self):
        """Estos números no se estiman: de ellos salen los 35 puntos sobre la cara."""
        vistas = {v["id"]: v for v in self.catalogo["vistas"]}
        self.assertEqual(set(vistas), {"hombre-frontal", "mujer-frontal"})

        hombre = vistas["hombre-frontal"]
        self.assertEqual(hombre["url"], "recursos/infiltraciones/base-hombre.jpg")
        self.assertEqual((hombre["ancho"], hombre["alto"]), (896, 1200))
        self.assertEqual(hombre["calibracion"], {
            "pupilaIzq": [0.330, 0.4118],
            "pupilaDer": [0.656, 0.4115],
            "menton": [0.493, 0.820],
        })

        mujer = vistas["mujer-frontal"]
        self.assertEqual(mujer["url"], "recursos/infiltraciones/base-mujer.jpg")
        self.assertEqual((mujer["ancho"], mujer["alto"]), (896, 1200))
        self.assertEqual(mujer["calibracion"], {
            "pupilaIzq": [0.3313, 0.4133],
            "pupilaDer": [0.664, 0.4172],
            "menton": [0.500, 0.829],
        })

    def test_los_35_puntos_y_las_5_plantillas_de_fabrica(self):
        self.assertEqual(len(self.catalogo["puntos"]), 35)
        self.assertEqual(len(self.catalogo["plantillas"]), 5)

        # Salen tal cual del archivo, con sus coordenadas faciales (u, v).
        procer = next(p for p in self.catalogo["puntos"] if p["id"] == "procer")
        self.assertEqual(procer["zona"], "Glabela — prócer")
        self.assertEqual(procer["lado"], "C")
        self.assertEqual((procer["u"], procer["v"]), (0.0, -0.19))

        full = next(p for p in self.catalogo["plantillas"]
                    if p["id"] == "full-face")
        self.assertEqual(len(full["puntos"]), 35)

    def test_las_zonas_vienen_agrupadas_en_orden_anatomico(self):
        zonas = self.catalogo["zonas"]
        textos = [z["texto"] for z in zonas]

        # Las de las plantillas están todas.
        for punto in self.catalogo["puntos"]:
            self.assertIn(punto["zona"], textos)
        # Y también las del catálogo del encargo que no marca ningún punto.
        for suelta in ("Sien", "Párpado inferior — pretarsal", "Mejilla",
                       "Lip flip", "Nefertiti", "Bruxismo",
                       "Otra (texto libre)"):
            self.assertIn(suelta, textos)

        # Sin repetidas y de la frente al cuello, no alfabético.
        self.assertEqual(len(textos), len(set(textos)))
        regiones = []
        for zona in zonas:
            if zona["region"] not in regiones:
                regiones.append(zona["region"])
        esperado = [r for r in pdf_infiltraciones.ORDEN_REGIONES
                    if r in regiones]
        self.assertEqual(regiones, esperado)
        self.assertEqual(regiones[0], "frente")
        self.assertEqual(regiones[-1], "otras")

    def test_la_region_de_cada_zona_es_la_misma_que_agrupa_el_pdf(self):
        """La tabla de la pantalla y la del papel tienen que agrupar igual."""
        for zona in self.catalogo["zonas"]:
            self.assertEqual(zona["region"],
                             pdf_infiltraciones.region_de_zona(zona["texto"]))
            self.assertEqual(
                zona["region_etiqueta"],
                pdf_infiltraciones.ETIQUETA_REGION[zona["region"]])

    def test_los_productos_precargados_son_genericos(self):
        productos = self.catalogo["productos"]
        self.assertGreaterEqual(len(productos), 4)
        self.assertLessEqual(len(productos), 5)
        for producto in productos:
            self.assertEqual(
                set(producto),
                {"id", "nombre", "tipo", "unidad", "color", "lote", "caducidad"})
            self.assertEqual(producto["lote"], "")
            self.assertEqual(producto["caducidad"], "")
            self.assertRegex(producto["color"], r"^#[0-9A-F]{6}$")
            self.assertIn(producto["unidad"], ("U", "ml", "mg"))
        self.assertIn("Toxina A — marca 1", [p["nombre"] for p in productos])


# --------------------------------------------------------------------------
# Las láminas: lista blanca de nombres
# --------------------------------------------------------------------------

class TestLaminas(BaseApp):

    def test_las_dos_laminas_se_sirven(self):
        for archivo in ("base-mujer.jpg", "base-hombre.jpg"):
            respuesta = self.cliente.get(f"/recursos/infiltraciones/{archivo}")
            self.assertEqual(respuesta.status_code, 200, archivo)
            self.assertEqual(respuesta.mimetype, "image/jpeg")
            self.assertTrue(respuesta.data.startswith(b"\xff\xd8"), archivo)
            self.assertEqual(
                len(respuesta.data),
                (Path(pdf_infiltraciones.DIR_LAMINAS_DEFECTO) / archivo)
                .stat().st_size)

    def test_un_nombre_fuera_de_la_lista_blanca_da_404(self):
        for archivo in ("base-perro.jpg", "logo.png", "plantillas.json",
                        "base-mujer.JPG", "base-mujer.jpg.bak", ""):
            respuesta = self.cliente.get(f"/recursos/infiltraciones/{archivo}")
            self.assertEqual(respuesta.status_code, 404, repr(archivo))

    def test_un_recorrido_de_directorios_da_404(self):
        """La ruta se arma con la clave de la constante, no con lo que llegó.

        Se prueban las dos formas de escribirlo, la de Windows y la de POSIX, y
        también un absoluto: ninguna encuentra clave en la lista blanca, así
        que ninguna llega a tocar el disco.
        """
        for intento in (r"..\..\algo",
                        r"..\..\..\Windows\win.ini",
                        "..%2F..%2Fdatos%2Frecipes.db",
                        "....//....//recipes.db",
                        "C:\\Windows\\win.ini"):
            respuesta = self.cliente.get(f"/recursos/infiltraciones/{intento}")
            self.assertIn(respuesta.status_code, (301, 308, 404), repr(intento))
            if respuesta.status_code == 404 and respuesta.is_json:
                # El mensaje no dice ni una ruta del disco.
                self.assertNotIn("\\Windows", respuesta.get_json()["error"])

    def test_la_lista_blanca_es_la_de_las_vistas_del_catalogo(self):
        """No hay dos listas que se puedan desincronizar."""
        del_catalogo = {
            v["url"].rsplit("/", 1)[-1]
            for v in self.cliente.get(
                "/api/infiltraciones/catalogo").get_json()["vistas"]
        }
        self.assertEqual(set(rutas.LAMINAS_SERVIBLES), del_catalogo)
        self.assertEqual(set(rutas.LAMINAS_SERVIBLES),
                         set(pdf_infiltraciones.LAMINAS.values()))


# --------------------------------------------------------------------------
# El alta de una sesión
# --------------------------------------------------------------------------

class TestAlta(BaseApp):

    def test_guarda_la_sesion_y_genera_el_pdf(self):
        datos = self.crear()
        self.assertEqual(datos["codigo"], "EC-0001")
        self.assertEqual(datos["vista"], "mujer-frontal")
        self.assertEqual(datos["fecha"], "2026-08-26")
        self.assertEqual(datos["cantidad_puntos"], 4)
        self.assertFalse(datos["anulado"])

        ruta = Path(datos["ruta_pdf"])
        self.assertTrue(ruta.is_file())
        self.assertEqual(ruta.name, "INFILTRACIONES_EC-0001_2026-08-26.pdf")
        self.assertEqual(ruta.parent.name, "infiltraciones")
        self.assertEqual(ruta.parent.parent.name, "EC-0001_Ana-Gomez")
        self.assertTrue(ruta.read_bytes().startswith(b"%PDF-"))
        self.assertTrue(datos["tiene_pdf"])

    def test_la_lamina_elegida_manda(self):
        datos = self.crear(cuerpo=sesion(vista="hombre-frontal"))
        self.assertEqual(datos["vista"], "hombre-frontal")
        self.assertTrue(Path(datos["ruta_pdf"]).is_file())

    def test_la_segunda_sesion_del_mismo_dia_sale_v2(self):
        paciente_id = self.alta_paciente()["id"]
        primera = self.crear(paciente_id)
        segunda = self.crear(paciente_id)
        self.assertEqual(Path(primera["ruta_pdf"]).name,
                         "INFILTRACIONES_EC-0001_2026-08-26.pdf")
        self.assertEqual(Path(segunda["ruta_pdf"]).name,
                         "INFILTRACIONES_EC-0001_2026-08-26_v2.pdf")
        self.assertTrue(Path(primera["ruta_pdf"]).is_file())

    def test_una_sesion_sin_puntos_es_valida(self):
        """Marcar la lámina y no infiltrar nada es un registro legítimo."""
        datos = self.crear(cuerpo=sesion(puntos=[], productos=[]))
        self.assertEqual(datos["cantidad_puntos"], 0)
        self.assertTrue(Path(datos["ruta_pdf"]).is_file())

    def test_el_paciente_sale_de_la_historia_no_del_formulario(self):
        respuesta = self.cliente.post("/api/pacientes/999/infiltraciones",
                                      json=SESION)
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("paciente", respuesta.get_json()["error"])

    def test_la_sesion_queda_en_la_lista_del_paciente(self):
        paciente_id = self.alta_paciente()["id"]
        creada = self.crear(paciente_id)

        respuesta = self.cliente.get(
            f"/api/pacientes/{paciente_id}/infiltraciones")
        self.assertEqual(respuesta.status_code, 200)
        sesiones = respuesta.get_json()["infiltraciones"]
        self.assertEqual([s["id"] for s in sesiones], [creada["id"]])
        self.assertEqual(sesiones[0]["cantidad_puntos"], 4)


# --------------------------------------------------------------------------
# Reabrir y corregir
# --------------------------------------------------------------------------

class TestReabrirYCorregir(BaseApp):

    def test_reabrir_devuelve_los_mismos_puntos(self):
        """Es la razón por la que la sesión viaja entera y no resumida."""
        creada = self.crear()
        respuesta = self.cliente.get(f"/api/infiltraciones/{creada['id']}")
        self.assertEqual(respuesta.status_code, 200)
        vuelta = respuesta.get_json()

        self.assertEqual(vuelta["vista"], "mujer-frontal")
        self.assertEqual(vuelta["calibracion"], SESION["calibracion"])
        self.assertEqual([p["id"] for p in vuelta["productos"]], ["p1", "p3"])
        self.assertEqual(vuelta["productos"][0]["lote"], "TX-7741")
        self.assertEqual(vuelta["observaciones"], SESION["observaciones"])

        self.assertEqual(len(vuelta["puntos"]), 4)
        for guardado, original in zip(vuelta["puntos"], PUNTOS):
            self.assertAlmostEqual(guardado["x"], original["x"])
            self.assertAlmostEqual(guardado["y"], original["y"])
            self.assertEqual(guardado["zona"], original["zona"])
            self.assertEqual(guardado["lado"], original["lado"])
            self.assertEqual(guardado["plantillaId"], original["plantillaId"])
            self.assertEqual(guardado["productoId"], original["productoId"])
        self.assertEqual(vuelta["puntos"][0]["dosis"], 4.0)
        # El punto marcado y no infiltrado conserva su hueco, no un cero.
        self.assertIsNone(vuelta["puntos"][3]["dosis"])
        self.assertEqual(vuelta["puntos"][3]["notas"], "marcado, no se infiltró")

    def test_una_sesion_que_no_esta_da_404(self):
        respuesta = self.cliente.get("/api/infiltraciones/999")
        self.assertEqual(respuesta.status_code, 404)

    def test_corregir_regenera_el_pdf_sin_pisar_el_viejo(self):
        """§0.5: el PDF anterior es el papel que se firmó antes de corregir."""
        creada = self.crear()
        viejo = Path(creada["ruta_pdf"])
        bytes_viejos = viejo.read_bytes()

        corregida = copy.deepcopy(SESION)
        corregida["puntos"][0]["dosis"] = 6
        corregida["productos"][0]["lote"] = "TX-9999"
        corregida["observaciones"] = "Se corrigió la dosis de la glabela."

        respuesta = self.cliente.put(f"/api/infiltraciones/{creada['id']}",
                                     json=corregida)
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        datos = respuesta.get_json()
        nuevo = Path(datos["ruta_pdf"])

        self.assertNotEqual(nuevo, viejo)
        self.assertEqual(nuevo.name, "INFILTRACIONES_EC-0001_2026-08-26_v2.pdf")
        self.assertTrue(nuevo.is_file())
        # El viejo sigue ahí y sin tocar.
        self.assertTrue(viejo.is_file())
        self.assertEqual(viejo.read_bytes(), bytes_viejos)
        self.assertEqual(
            sorted(h.name for h in nuevo.parent.iterdir()),
            ["INFILTRACIONES_EC-0001_2026-08-26.pdf",
             "INFILTRACIONES_EC-0001_2026-08-26_v2.pdf"])

        # La corrección quedó guardada y `ruta_pdf` apunta al último.
        self.assertEqual(datos["puntos"][0]["dosis"], 6.0)
        self.assertEqual(datos["productos"][0]["lote"], "TX-9999")
        self.assertEqual(datos["observaciones"],
                         "Se corrigió la dosis de la glabela.")
        con = self.conexion()
        try:
            fila = basedatos.obtener_infiltracion(con, creada["id"])
            self.assertEqual(fila["ruta_pdf"], str(nuevo))
        finally:
            con.close()

    def test_corregir_puede_sacar_y_agregar_puntos(self):
        creada = self.crear()
        respuesta = self.cliente.put(
            f"/api/infiltraciones/{creada['id']}",
            json=sesion(puntos=[PUNTOS[0]]))
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        self.assertEqual(respuesta.get_json()["cantidad_puntos"], 1)

    def test_una_sesion_anulada_no_se_corrige(self):
        creada = self.crear()
        self.cliente.post(f"/api/infiltraciones/{creada['id']}/anular",
                          json={"motivo": "Se cargó al paciente equivocado"})
        respuesta = self.cliente.put(f"/api/infiltraciones/{creada['id']}",
                                     json=SESION)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("anulado", respuesta.get_json()["error"])


# --------------------------------------------------------------------------
# Los límites del contrato §5
# --------------------------------------------------------------------------

class TestValidacion(BaseApp):

    def setUp(self) -> None:
        super().setUp()
        self.paciente_id = self.alta_paciente()["id"]

    def rechaza(self, cuerpo, *fragmentos):
        respuesta = self.cliente.post(
            f"/api/pacientes/{self.paciente_id}/infiltraciones", json=cuerpo)
        self.assertEqual(respuesta.status_code, 400, respuesta.get_json())
        error = respuesta.get_json()["error"]
        for fragmento in fragmentos:
            self.assertIn(fragmento, error)
        # Y no quedó nada escrito.
        con = self.conexion()
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM infiltraciones")
                .fetchone()[0], 0)
        finally:
            con.close()
        return error

    def test_mas_de_200_puntos(self):
        muchos = [{"x": 0.5, "y": 0.5, "productoId": "p1"} for _ in range(201)]
        self.rechaza(sesion(puntos=muchos), "201", "200")

    def test_exactamente_200_puntos_entra(self):
        """El tope es un tope, no un margen: 200 tiene que pasar."""
        justos = [{"orden": i + 1, "x": 0.5, "y": 0.5, "productoId": "p1",
                   "zona": "Frontal — línea alta", "dosis": 2}
                  for i in range(200)]
        datos = self.crear(self.paciente_id, cuerpo=sesion(puntos=justos))
        self.assertEqual(datos["cantidad_puntos"], 200)

    def test_x_fuera_de_rango(self):
        self.rechaza(sesion(puntos=[{"x": 1.5, "y": 0.5, "productoId": "p1"}]),
                     "punto 1", "0.0 y 1.0")

    def test_y_fuera_de_rango(self):
        self.rechaza(sesion(puntos=[{"x": 0.5, "y": -0.2, "productoId": "p1"}]),
                     "punto 1", "0.0 y 1.0")

    def test_un_punto_sin_coordenadas(self):
        self.rechaza(sesion(puntos=[{"productoId": "p1"}]),
                     "punto 1", "Volvé a marcar")

    def test_una_coordenada_que_no_es_un_numero(self):
        self.rechaza(sesion(puntos=[{"x": "por ahí", "y": 0.5}]),
                     "tiene que ser un número")

    def test_un_producto_que_no_esta_en_la_sesion(self):
        self.rechaza(
            sesion(puntos=[{"x": 0.5, "y": 0.5, "productoId": "no-existe"}]),
            "punto 1", "no está en la lista de la sesión")

    def test_un_punto_sin_producto_si_se_acepta(self):
        """El punto marcado y no infiltrado es un registro válido."""
        datos = self.crear(self.paciente_id, cuerpo=sesion(
            puntos=[{"x": 0.5, "y": 0.5, "productoId": "", "zona": "Mentoniano"}]))
        self.assertEqual(datos["cantidad_puntos"], 1)

    def test_una_vista_desconocida(self):
        error = self.rechaza(sesion(vista="perro-frontal"), "perro-frontal")
        self.assertIn("mujer-frontal", error)
        self.assertIn("hombre-frontal", error)

    def test_sin_vista(self):
        self.rechaza(sesion(vista=""), "lámina")

    def test_mas_de_20_productos(self):
        muchos = [{"id": f"p{i}", "nombre": f"Producto {i}", "color": "#123456"}
                  for i in range(21)]
        self.rechaza(sesion(productos=muchos, puntos=[]), "21", "20")

    def test_dos_productos_con_el_mismo_id(self):
        self.rechaza(
            sesion(productos=[{"id": "p1", "nombre": "Uno"},
                              {"id": "p1", "nombre": "Otro"}], puntos=[]),
            "mismo identificador")

    def test_un_producto_sin_nombre(self):
        self.rechaza(sesion(productos=[{"id": "p1", "nombre": "  "}], puntos=[]),
                     "nombre al producto 1")

    def test_un_color_que_no_es_rrggbb(self):
        self.rechaza(
            sesion(productos=[{"id": "p1", "nombre": "Toxina", "color": "rojo"}],
                   puntos=[]),
            "#RRGGBB")

    def test_la_dosis_no_pasa_de_999(self):
        self.rechaza(
            sesion(puntos=[{"x": 0.5, "y": 0.5, "productoId": "p1",
                            "dosis": 1000}]),
            "dosis del punto 1", "999")

    def test_la_dosis_no_es_negativa(self):
        self.rechaza(
            sesion(puntos=[{"x": 0.5, "y": 0.5, "productoId": "p1",
                            "dosis": -1}]),
            "dosis del punto 1")

    def test_la_dosis_admite_la_coma_decimal(self):
        """El médico escribe «0,4» tanto como «0.4»."""
        datos = self.crear(self.paciente_id, cuerpo=sesion(
            puntos=[{"x": 0.5, "y": 0.5, "productoId": "p3", "dosis": "0,4"}]))
        vuelta = self.cliente.get(
            f"/api/infiltraciones/{datos['id']}").get_json()
        self.assertAlmostEqual(vuelta["puntos"][0]["dosis"], 0.4)

    def test_una_calibracion_a_medias(self):
        self.rechaza(sesion(calibracion={"pupilaIzq": [0.3]}), "pupilaIzq")

    def test_una_calibracion_fuera_de_la_lamina(self):
        self.rechaza(
            sesion(calibracion={"pupilaIzq": [0.3, 0.4],
                                "pupilaDer": [1.4, 0.4],
                                "menton": [0.5, 0.8]}),
            "pupilaDer")

    def test_sin_calibrar_tambien_vale(self):
        """Marcar a ojo sobre la lámina es válido: la calibración es opcional."""
        datos = self.crear(self.paciente_id, cuerpo=sesion(calibracion={}))
        vuelta = self.cliente.get(
            f"/api/infiltraciones/{datos['id']}").get_json()
        self.assertEqual(vuelta["calibracion"], {})

    def test_una_fecha_mal_escrita(self):
        self.rechaza(sesion(fecha="26-08-2026"), "AAAA-MM-DD")

    def test_los_limites_valen_igual_al_corregir(self):
        """Una corrección no puede aceptar lo que el alta rechaza."""
        creada = self.crear(self.paciente_id)
        respuesta = self.cliente.put(
            f"/api/infiltraciones/{creada['id']}",
            json=sesion(puntos=[{"x": 2.0, "y": 0.5, "productoId": "p1"}]))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("0.0 y 1.0", respuesta.get_json()["error"])


# --------------------------------------------------------------------------
# Reimprimir y anular
# --------------------------------------------------------------------------

class TestReimprimirYAnular(BaseApp):

    def test_el_pdf_que_se_devuelve_es_el_mismo_archivo(self):
        creada = self.crear()
        respuesta = self.cliente.get(f"/api/infiltraciones/{creada['id']}/pdf")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.mimetype, "application/pdf")
        self.assertEqual(respuesta.data, Path(creada["ruta_pdf"]).read_bytes())

    def test_despues_de_corregir_se_devuelve_el_pdf_nuevo(self):
        creada = self.crear()
        corregida = self.cliente.put(f"/api/infiltraciones/{creada['id']}",
                                     json=sesion(observaciones="Corregida."))
        nuevo = Path(corregida.get_json()["ruta_pdf"])

        respuesta = self.cliente.get(f"/api/infiltraciones/{creada['id']}/pdf")
        self.assertEqual(respuesta.data, nuevo.read_bytes())

    def test_el_pdf_movido_se_explica(self):
        creada = self.crear()
        Path(creada["ruta_pdf"]).unlink()
        respuesta = self.cliente.get(f"/api/infiltraciones/{creada['id']}/pdf")
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("2026-08-26", respuesta.get_json()["error"])

    def test_abrir_no_falla_con_el_visor_apagado(self):
        creada = self.crear()
        respuesta = self.cliente.post(
            f"/api/infiltraciones/{creada['id']}/abrir")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.get_json()["ok"])

    def test_anular_exige_motivo(self):
        creada = self.crear()
        respuesta = self.cliente.post(
            f"/api/infiltraciones/{creada['id']}/anular", json={"motivo": " "})
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("motivo", respuesta.get_json()["error"])

    def test_anular_deja_el_motivo_y_no_borra_el_pdf(self):
        creada = self.crear()
        respuesta = self.cliente.post(
            f"/api/infiltraciones/{creada['id']}/anular",
            json={"motivo": "Se cargó al paciente equivocado"})
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())
        datos = respuesta.get_json()

        self.assertTrue(datos["anulado"])
        self.assertEqual(datos["motivo_anulacion"],
                         "Se cargó al paciente equivocado")
        self.assertTrue(datos["fecha_anulacion"])
        self.assertTrue(Path(creada["ruta_pdf"]).is_file())
        # Los puntos siguen ahí: anular no borra el registro de lo que se hizo.
        self.assertEqual(datos["cantidad_puntos"], 4)

    def test_anular_dos_veces_no_pisa_el_motivo_original(self):
        creada = self.crear()
        self.cliente.post(f"/api/infiltraciones/{creada['id']}/anular",
                          json={"motivo": "El primero"})
        segunda = self.cliente.post(f"/api/infiltraciones/{creada['id']}/anular",
                                    json={"motivo": "El segundo"})
        self.assertEqual(segunda.status_code, 400)
        self.assertIn("El primero", segunda.get_json()["error"])

    def test_la_sesion_anulada_sigue_en_la_lista_marcada(self):
        paciente_id = self.alta_paciente()["id"]
        creada = self.crear(paciente_id)
        self.cliente.post(f"/api/infiltraciones/{creada['id']}/anular",
                          json={"motivo": "Se repitió"})
        sesiones = self.cliente.get(
            f"/api/pacientes/{paciente_id}/infiltraciones"
        ).get_json()["infiltraciones"]
        self.assertEqual(len(sesiones), 1)
        self.assertTrue(sesiones[0]["anulado"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
