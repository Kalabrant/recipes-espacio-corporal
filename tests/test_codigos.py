"""Tests de `codigos.py` — la pieza que no puede fallar (§6 de las instrucciones).

Cubre lo que pide el documento: reinicio de año, concurrencia de dos
escrituras simultáneas con hilos reales contra la misma base, relleno de
ceros, desborde a cinco dígitos y no reutilización tras anulación.

Solo `unittest` de la stdlib: la app no agrega dependencias (§3).
Se corre con:  py -3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import basedatos  # noqa: E402
import codigos  # noqa: E402


ITEMS = [{"medicamento": "Amoxicilina", "presentacion": "500 mg",
          "cantidad": "20 tabletas", "dosis": "1 cada 8 horas",
          "indicaciones": "Con las comidas"}]


class BaseEnDisco(unittest.TestCase):
    """Base real en disco: `:memory:` no comparte estado entre conexiones.

    Los tests de concurrencia necesitan varias conexiones sobre el mismo
    archivo, así que todos usan disco para probar contra lo mismo que corre
    en la máquina del médico.
    """

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_test_"))
        self.ruta = self.carpeta / "recipes.db"
        self.con = basedatos.inicializar(self.ruta)
        self.paciente_id = basedatos.crear_paciente(
            self.con, "Juan Pérez", cedula="V-12345678", edad=40
        )

    def tearDown(self) -> None:
        self.con.close()
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def emitir(self, fecha=None, **extra) -> dict:
        return codigos.crear_recipe(
            self.con, self.paciente_id, ITEMS, fecha_emision=fecha, **extra
        )


# --------------------------------------------------------------------------
# Formato y relleno de ceros (§6, §6.5)
# --------------------------------------------------------------------------

class TestFormato(unittest.TestCase):

    def test_relleno_de_ceros(self):
        """1 → 0001, 42 → 0042, 1234 → 1234: los tres casos del documento."""
        self.assertEqual(codigos.formatear_codigo("EC", 2026, 1), "EC-2026-0001")
        self.assertEqual(codigos.formatear_codigo("EC", 2026, 42), "EC-2026-0042")
        self.assertEqual(codigos.formatear_codigo("EC", 2026, 1234), "EC-2026-1234")
        self.assertEqual(codigos.formatear_secuencial(7), "0007")
        self.assertEqual(codigos.formatear_secuencial(999), "0999")
        self.assertEqual(codigos.formatear_secuencial(9999), "9999")

    def test_desborde_a_cinco_digitos(self):
        """Pasado 9999 se sigue con cinco dígitos, sin romper el formato (§6.5)."""
        self.assertEqual(codigos.formatear_codigo("EC", 2026, 10000), "EC-2026-10000")
        self.assertEqual(codigos.formatear_codigo("EC", 2026, 99999), "EC-2026-99999")
        self.assertEqual(codigos.formatear_codigo("EC", 2026, 100000), "EC-2026-100000")

    def test_secuencial_invalido(self):
        for malo in (0, -1):
            with self.subTest(secuencial=malo):
                with self.assertRaises(ValueError):
                    codigos.formatear_secuencial(malo)

    def test_partir_codigo(self):
        self.assertEqual(codigos.partir_codigo("EC-2026-0001"), ("EC", 2026, 1))
        self.assertEqual(codigos.partir_codigo("EC-2026-0042"), ("EC", 2026, 42))
        self.assertEqual(codigos.partir_codigo("EC-2026-10000"), ("EC", 2026, 10000))
        self.assertEqual(codigos.partir_codigo("mx-2027-1234"), ("MX", 2027, 1234))

    def test_partir_codigo_invalido(self):
        for malo in ("", "EC-2026", "EC-26-0001", "EC-2026-1", "2026-0001", "EC/2026/0001"):
            with self.subTest(codigo=malo):
                with self.assertRaises(ValueError):
                    codigos.partir_codigo(malo)

    def test_ida_y_vuelta(self):
        for secuencial in (1, 42, 1234, 9999, 10000, 123456):
            with self.subTest(secuencial=secuencial):
                codigo = codigos.formatear_codigo("EC", 2026, secuencial)
                self.assertEqual(codigos.partir_codigo(codigo), ("EC", 2026, secuencial))


# --------------------------------------------------------------------------
# Prefijo configurable (§6.6)
# --------------------------------------------------------------------------

class TestPrefijo(BaseEnDisco):

    def test_por_defecto_es_ec(self):
        self.assertEqual(codigos.obtener_prefijo(self.con), "EC")
        self.assertTrue(self.emitir("2026-08-14")["codigo"].startswith("EC-"))

    def test_prefijo_configurable(self):
        codigos.guardar_prefijo(self.con, "MX")
        self.assertEqual(codigos.obtener_prefijo(self.con), "MX")
        self.assertTrue(self.emitir("2026-08-14")["codigo"].startswith("MX-"))

    def test_los_emitidos_conservan_su_prefijo(self):
        """Cambiar el prefijo no toca los récipes ya emitidos (§6.6)."""
        viejo = self.emitir("2026-08-14")["codigo"]
        codigos.guardar_prefijo(self.con, "ZZ")
        nuevo = self.emitir("2026-08-14")["codigo"]

        self.assertEqual(viejo, "EC-2026-0001")
        self.assertEqual(nuevo, "ZZ-2026-0002")
        # Releído de la base, el primero sigue siendo EC.
        self.assertEqual(basedatos.obtener_recipe_por_codigo(self.con, viejo)["codigo"], viejo)
        # Y el secuencial es continuo: el prefijo no reinicia la numeración.

    def test_prefijo_se_normaliza_a_mayusculas(self):
        self.assertEqual(codigos.guardar_prefijo(self.con, " ec "), "EC")
        self.assertEqual(codigos.obtener_prefijo(self.con), "EC")

    def test_prefijo_invalido(self):
        for malo in ("", "   ", "EC-", "E C 1 2 3 4 5 6 7 8 9 0 1", "ÉC", "EC/1"):
            with self.subTest(prefijo=malo):
                with self.assertRaises(ValueError):
                    codigos.guardar_prefijo(self.con, malo)

    def test_prefijo_corrupto_no_impide_emitir(self):
        """Una base tocada a mano no puede dejar al médico sin poder emitir."""
        basedatos.guardar_config(self.con, codigos.CLAVE_PREFIJO, "!!!")
        self.assertEqual(codigos.obtener_prefijo(self.con), "EC")
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-0001")


# --------------------------------------------------------------------------
# Numeración correlativa y reinicio de año (§6.1)
# --------------------------------------------------------------------------

class TestNumeracion(BaseEnDisco):

    def test_tres_seguidos_son_0001_0002_0003(self):
        """Criterio de aceptación de §12."""
        emitidos = [self.emitir("2026-08-14")["codigo"] for _ in range(3)]
        self.assertEqual(emitidos, ["EC-2026-0001", "EC-2026-0002", "EC-2026-0003"])

    def test_reinicio_de_anio(self):
        """El 1 de enero el secuencial vuelve a 0001 (§6.1)."""
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-0001")
        self.assertEqual(self.emitir("2026-12-31")["codigo"], "EC-2026-0002")
        self.assertEqual(self.emitir("2027-01-01")["codigo"], "EC-2027-0001")
        self.assertEqual(self.emitir("2027-01-02")["codigo"], "EC-2027-0002")

    def test_los_contadores_de_cada_anio_son_independientes(self):
        """Volver a emitir en el año viejo retoma su propia serie, no la nueva."""
        self.emitir("2026-05-01")
        self.emitir("2027-01-10")
        self.emitir("2027-01-11")
        self.assertEqual(self.emitir("2026-06-01")["codigo"], "EC-2026-0002")
        self.assertEqual(self.emitir("2027-02-01")["codigo"], "EC-2027-0003")
        self.assertEqual(basedatos.obtener_ultimo_secuencial(self.con, 2026), 2)
        self.assertEqual(basedatos.obtener_ultimo_secuencial(self.con, 2027), 3)

    def test_el_anio_sale_de_la_fecha_de_emision(self):
        recipe = self.emitir("2027-03-09")
        self.assertEqual(recipe["anio"], 2027)
        self.assertEqual(recipe["secuencial"], 1)
        self.assertEqual(codigos.partir_codigo(recipe["codigo"])[1], 2027)

    def test_sin_fecha_usa_el_dia_de_hoy(self):
        """Sin fecha explícita manda el reloj de la máquina, que es el caso real."""
        hoy = date.today()
        recipe = self.emitir()
        self.assertEqual(recipe["anio"], hoy.year)
        self.assertEqual(recipe["codigo"], codigos.formatear_codigo("EC", hoy.year, 1))
        self.assertTrue(recipe["fecha_emision"].startswith(hoy.isoformat()))

    def test_vista_previa_no_quema_numero(self):
        """Un formulario abandonado no gasta un código (§6.2)."""
        self.assertEqual(codigos.proximo_codigo(self.con, 2026), "EC-2026-0001")
        self.assertEqual(codigos.proximo_codigo(self.con, 2026), "EC-2026-0001")
        self.assertEqual(codigos.proximo_secuencial(self.con, 2026), 1)
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-0001")

    def test_asignar_codigo_exige_transaccion(self):
        """Sin BEGIN IMMEDIATE no se reserva nada: es la garantía de §6.3."""
        with self.assertRaises(RuntimeError):
            codigos.asignar_codigo(self.con, 2026)
        self.assertEqual(basedatos.obtener_ultimo_secuencial(self.con, 2026), 0)

    def test_fecha_invalida_falla_temprano(self):
        for mala in ("14/08/2026", "2026-13-40", "ayer", "26-08-14"):
            with self.subTest(fecha=mala):
                with self.assertRaises(ValueError):
                    self.emitir(mala)

    def test_recipe_sin_medicamentos_no_quema_numero(self):
        with self.assertRaises(ValueError):
            codigos.crear_recipe(self.con, self.paciente_id, [], fecha_emision="2026-08-14")
        self.assertEqual(basedatos.obtener_ultimo_secuencial(self.con, 2026), 0)

    def test_fallo_a_mitad_deja_todo_como_estaba(self):
        """La transacción es una sola: si el insert falla, no queda número quemado."""
        with self.assertRaises(sqlite3.IntegrityError):
            codigos.crear_recipe(self.con, 999_999, ITEMS, fecha_emision="2026-08-14")
        self.assertEqual(basedatos.obtener_ultimo_secuencial(self.con, 2026), 0)
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-0001")


# --------------------------------------------------------------------------
# Desborde real, emitiendo (§6.5)
# --------------------------------------------------------------------------

class TestDesborde(BaseEnDisco):

    def _sembrar_contador(self, anio: int, ultimo: int) -> None:
        """Deja el año arrancado en `ultimo` sin emitir 9999 récipes de verdad."""
        momento = basedatos.ahora_iso()
        self.con.execute(
            """
            INSERT INTO contador_anual (anio, ultimo_secuencial, creado_en, actualizado_en)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(anio) DO UPDATE SET ultimo_secuencial = excluded.ultimo_secuencial
            """,
            (anio, ultimo, momento, momento),
        )

    def test_9999_pasa_a_cinco_digitos(self):
        """Criterio de aceptación de §12: 9999 → EC-2026-10000, sin romperse."""
        self._sembrar_contador(2026, 9998)
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-9999")
        recipe = self.emitir("2026-08-14")
        self.assertEqual(recipe["codigo"], "EC-2026-10000")
        self.assertEqual(recipe["secuencial"], 10000)
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-10001")

    def test_el_desborde_no_arrastra_al_anio_siguiente(self):
        """Aun desbordado, el año que sigue arranca en 0001 (§6.1)."""
        self._sembrar_contador(2026, 10_000)
        self.assertEqual(self.emitir("2026-12-31")["codigo"], "EC-2026-10001")
        self.assertEqual(self.emitir("2027-01-01")["codigo"], "EC-2027-0001")

    def test_el_codigo_desbordado_se_lee_de_vuelta(self):
        self._sembrar_contador(2026, 9999)
        codigo = self.emitir("2026-08-14")["codigo"]
        self.assertEqual(codigos.partir_codigo(codigo), ("EC", 2026, 10000))
        self.assertIsNotNone(basedatos.obtener_recipe_por_codigo(self.con, codigo))


# --------------------------------------------------------------------------
# No reutilización tras anulación (§6.4)
# --------------------------------------------------------------------------

class TestAnulacion(BaseEnDisco):

    def test_anular_no_libera_el_numero(self):
        """Criterio de aceptación de §12: anular no libera el número."""
        primero = self.emitir("2026-08-14")
        segundo = self.emitir("2026-08-14")
        tercero = self.emitir("2026-08-14")
        self.assertEqual(segundo["codigo"], "EC-2026-0002")

        basedatos.anular_recipe(self.con, segundo["id"], "Error de dosis")

        cuarto = self.emitir("2026-08-14")
        self.assertEqual(cuarto["codigo"], "EC-2026-0004")
        emitidos = {primero["codigo"], segundo["codigo"], tercero["codigo"], cuarto["codigo"]}
        self.assertEqual(len(emitidos), 4)

    def test_el_anulado_conserva_su_codigo(self):
        """El récipe no se borra: queda anulado, con su código y su motivo (§2.4)."""
        recipe = self.emitir("2026-08-14")
        basedatos.anular_recipe(self.con, recipe["id"], "Paciente equivocado")

        guardado = basedatos.obtener_recipe(self.con, recipe["id"])
        self.assertEqual(guardado["codigo"], recipe["codigo"])
        self.assertEqual(guardado["anulado"], 1)
        self.assertEqual(guardado["motivo_anulacion"], "Paciente equivocado")
        self.assertIsNotNone(guardado["fecha_anulacion"])

    def test_anular_todo_el_anio_no_reinicia_la_serie(self):
        recipes = [self.emitir("2026-08-14") for _ in range(3)]
        for recipe in recipes:
            basedatos.anular_recipe(self.con, recipe["id"], "Reimpresión mal hecha")
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-0004")

    def test_el_codigo_anulado_no_se_puede_reemitir(self):
        """La base misma lo impide: `codigo` es único y `(anio, secuencial)` también."""
        recipe = self.emitir("2026-08-14")
        basedatos.anular_recipe(self.con, recipe["id"], "Duplicado")
        with self.assertRaises(sqlite3.IntegrityError):
            with basedatos.transaccion(self.con, inmediata=True):
                self.con.execute(
                    """
                    INSERT INTO recipes (codigo, anio, secuencial, paciente_id, fecha_emision,
                                         creado_en, actualizado_en)
                    VALUES (?, 2026, 1, ?, '2026-08-14', '2026-08-14', '2026-08-14')
                    """,
                    (recipe["codigo"], self.paciente_id),
                )

    def test_contador_perdido_no_recicla_numeros(self):
        """Cinturón de seguridad: aunque el contador se pierda, no se repite un código."""
        for _ in range(3):
            self.emitir("2026-08-14")
        basedatos.anular_recipe(
            self.con, basedatos.obtener_recipe_por_codigo(self.con, "EC-2026-0002")["id"],
            "Error de transcripción",
        )
        self.con.execute("DELETE FROM contador_anual WHERE anio = 2026")

        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-2026-0004")


# --------------------------------------------------------------------------
# Concurrencia: dos ventanas escribiendo a la vez (§6.3)
# --------------------------------------------------------------------------

class TestConcurrencia(BaseEnDisco):

    def _emitir_en_hilo(self, ruta: Path, cantidad: int, arranque: threading.Barrier,
                        salida: list, errores: list) -> None:
        """Un hilo = una ventana de la app: conexión propia sobre el mismo archivo."""
        try:
            con = basedatos.inicializar(ruta)
        except Exception as error:  # pragma: no cover
            errores.append(error)
            return
        try:
            arranque.wait(timeout=30)
            for _ in range(cantidad):
                recipe = codigos.crear_recipe(
                    con, self.paciente_id, ITEMS, fecha_emision="2026-08-14"
                )
                salida.append(recipe["codigo"])
        except Exception as error:
            errores.append(error)
        finally:
            con.close()

    def _correr(self, hilos: int, por_hilo: int) -> list[str]:
        arranque = threading.Barrier(hilos)
        salida: list[str] = []
        errores: list[Exception] = []
        trabajadores = [
            threading.Thread(
                target=self._emitir_en_hilo,
                args=(self.ruta, por_hilo, arranque, salida, errores),
            )
            for _ in range(hilos)
        ]
        for hilo in trabajadores:
            hilo.start()
        for hilo in trabajadores:
            hilo.join(timeout=60)
            self.assertFalse(hilo.is_alive(), "Un hilo quedó colgado esperando el lock.")
        self.assertEqual(errores, [], f"Los hilos fallaron: {errores}")
        return salida

    def test_dos_ventanas_simultaneas_no_repiten_codigo(self):
        """El caso del documento: el médico con dos ventanas abiertas (§6.3)."""
        por_hilo = 25
        codigos_emitidos = self._correr(hilos=2, por_hilo=por_hilo)
        total = 2 * por_hilo

        self.assertEqual(len(codigos_emitidos), total)
        self.assertEqual(len(set(codigos_emitidos)), total, "Se repitió un código.")
        self.assertEqual(
            sorted(codigos.partir_codigo(c)[2] for c in codigos_emitidos),
            list(range(1, total + 1)),
            "La serie quedó con huecos o saltos.",
        )
        self.assertEqual(basedatos.obtener_ultimo_secuencial(self.con, 2026), total)

    def test_cuatro_escritores_simultaneos(self):
        """Más presión de la que la app va a ver nunca, para que el margen sobre."""
        por_hilo = 15
        codigos_emitidos = self._correr(hilos=4, por_hilo=por_hilo)
        total = 4 * por_hilo

        self.assertEqual(len(set(codigos_emitidos)), total)
        filas = self.con.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT codigo) AS distintos FROM recipes"
        ).fetchone()
        self.assertEqual(filas["n"], total)
        self.assertEqual(filas["distintos"], total)

    def test_los_renglones_quedan_pegados_a_su_recipe(self):
        """Con escrituras cruzadas, ningún récipe se queda sin sus renglones."""
        por_hilo = 10
        self._correr(hilos=3, por_hilo=por_hilo)
        huerfanos = self.con.execute(
            """
            SELECT COUNT(*) AS n FROM recipes r
             WHERE (SELECT COUNT(*) FROM recipe_items ri WHERE ri.recipe_id = r.id) <> ?
            """,
            (len(ITEMS),),
        ).fetchone()["n"]
        self.assertEqual(huerfanos, 0)


# --------------------------------------------------------------------------
# Lo que el récipe guarda (§5): copia literal y aprendizaje
# --------------------------------------------------------------------------

class TestGuardado(BaseEnDisco):

    def test_guarda_copia_literal_de_los_renglones(self):
        recipe = self.emitir("2026-08-14", diagnostico="Faringitis aguda")
        items = basedatos.obtener_items(self.con, recipe["id"])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["medicamento"], "Amoxicilina")
        self.assertEqual(items[0]["presentacion"], "500 mg")
        self.assertEqual(items[0]["cantidad"], "20 tabletas")
        self.assertEqual(items[0]["dosis"], "1 cada 8 horas")
        self.assertEqual(items[0]["orden"], 1)
        self.assertEqual(recipe["diagnostico"], "Faringitis aguda")

    def test_corregir_el_catalogo_no_altera_los_emitidos(self):
        """Criterio de aceptación de §12."""
        recipe = self.emitir("2026-08-14")
        self.con.execute(
            "UPDATE medicamentos SET nombre = 'Amoxicilina trihidrato', nombre_norm = ?",
            (basedatos.normalizar("Amoxicilina trihidrato"),),
        )
        items = basedatos.obtener_items(self.con, recipe["id"])
        self.assertEqual(items[0]["medicamento"], "Amoxicilina")

    def test_aprende_los_terminos_al_guardar(self):
        """Al guardar se aprende para el autocompletado (§8)."""
        self.emitir("2026-08-14", diagnostico="Faringitis aguda")

        medicamentos = basedatos.buscar_medicamentos(self.con, "amoxi")
        self.assertEqual(len(medicamentos), 1)
        self.assertEqual(medicamentos[0]["veces_usado"], 1)

        dosis = basedatos.dosis_mas_usada(self.con, medicamentos[0]["id"])
        self.assertEqual(dosis["texto"], "1 cada 8 horas")
        self.assertEqual(len(basedatos.buscar_diagnosticos(self.con, "faring")), 1)
        self.assertEqual(basedatos.obtener_paciente(self.con, self.paciente_id)["veces_atendido"], 1)

    def test_renglones_vacios_se_descartan(self):
        recipe = codigos.crear_recipe(
            self.con, self.paciente_id,
            [ITEMS[0], {"medicamento": "  ", "dosis": "1 diaria"},
             {"medicamento": "Ibuprofeno", "presentacion": "400 mg"}],
            fecha_emision="2026-08-14",
        )
        items = basedatos.obtener_items(self.con, recipe["id"])
        self.assertEqual([i["medicamento"] for i in items], ["Amoxicilina", "Ibuprofeno"])
        self.assertEqual([i["orden"] for i in items], [1, 2])


# --------------------------------------------------------------------------
# Indicaciones generales del récipe (mitad `Ind.` del modelo)
#
# La mitad derecha de la hoja lleva las indicaciones de cada medicamento
# —que viven en recipe_items— y además un texto libre del récipe entero.
# --------------------------------------------------------------------------

class TestIndicacionesGenerales(BaseEnDisco):

    TEXTO = "Reposo relativo 3 días.\nAbundante líquido.\nControl si no cede la fiebre."

    def test_guarda_y_devuelve_las_indicaciones_generales(self):
        recipe = self.emitir("2026-08-14", indicaciones_generales=self.TEXTO)
        self.assertEqual(recipe["indicaciones_generales"], self.TEXTO)

        # Y sobre todo: releídas de la base, que es de donde las va a sacar el PDF.
        guardado = basedatos.obtener_recipe(self.con, recipe["id"])
        self.assertEqual(guardado["indicaciones_generales"], self.TEXTO)

    def test_conviven_con_las_indicaciones_de_cada_medicamento(self):
        """Son dos cosas distintas: las del renglón no pisan las del récipe."""
        recipe = self.emitir("2026-08-14", indicaciones_generales=self.TEXTO)
        items = basedatos.obtener_items(self.con, recipe["id"])
        self.assertEqual(items[0]["indicaciones"], "Con las comidas")
        self.assertEqual(recipe["indicaciones_generales"], self.TEXTO)

    def test_sin_el_parametro_el_recipe_se_guarda_igual(self):
        """La columna es opcional: el flujo de siempre no cambia."""
        recipe = self.emitir("2026-08-14")
        self.assertEqual(recipe["codigo"], "EC-2026-0001")
        self.assertIsNone(recipe["indicaciones_generales"])
        self.assertIsNone(
            basedatos.obtener_recipe(self.con, recipe["id"])["indicaciones_generales"]
        )

    def test_texto_vacio_o_en_blanco_queda_en_null(self):
        for vacio in (None, "", "   ", "\n\n"):
            with self.subTest(valor=repr(vacio)):
                recipe = self.emitir("2026-08-14", indicaciones_generales=vacio)
                self.assertIsNone(recipe["indicaciones_generales"])

    def test_conserva_los_saltos_de_linea_y_recorta_los_bordes(self):
        """Cada renglón es una instrucción: colapsarlos cambiaría lo que se lee."""
        recipe = self.emitir(
            "2026-08-14",
            indicaciones_generales="\r\n  Reposo   relativo  \r\nAbundante líquido\n\n",
        )
        self.assertEqual(
            recipe["indicaciones_generales"], "Reposo relativo\nAbundante líquido"
        )

    def test_el_historial_las_devuelve(self):
        """`buscar_recipes` trae la fila entera: el Historial y el Excel las ven."""
        self.emitir("2026-08-14", indicaciones_generales=self.TEXTO)
        fila = basedatos.buscar_recipes(self.con, "EC-2026-0001")[0]
        self.assertEqual(fila["indicaciones_generales"], self.TEXTO)


# --------------------------------------------------------------------------
# Migraciones versionadas: una base v1 tiene que llegar a v2 sin perder nada
# --------------------------------------------------------------------------

class TestMigraciones(unittest.TestCase):
    """Lo que le pasa a la base que el médico ya tiene en su disco."""

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_migr_"))
        self.ruta = self.carpeta / "recipes.db"

    def tearDown(self) -> None:
        shutil.rmtree(self.carpeta, ignore_errors=True)

    # -- utilidades --------------------------------------------------------

    def _columnas(self, con: sqlite3.Connection, tabla: str) -> list[str]:
        return [f["name"] for f in con.execute(f"PRAGMA table_info({tabla})")]

    def _base_v1_con_datos(self) -> None:
        """Crea una base con el esquema v1 y un récipe emitido adentro.

        Se aplica el script v1 real y se para la versión en 1: es exactamente
        la base que quedó en la máquina del médico antes de este cambio.
        """
        con = basedatos.conectar(self.ruta)
        con.executescript(basedatos.MIGRACIONES[0])
        con.execute("PRAGMA user_version = 1")

        self.assertEqual(basedatos.version_actual(con), 1)
        self.assertNotIn("indicaciones_generales", self._columnas(con, "recipes"))

        paciente_id = basedatos.crear_paciente(con, "Juan Pérez", cedula="V-12345678", edad=40)
        con.execute(
            """
            INSERT INTO recipes (codigo, anio, secuencial, paciente_id, fecha_emision,
                                 diagnostico, notas, creado_en, actualizado_en)
            VALUES ('EC-2026-0001', 2026, 1, ?, '2026-08-14', 'Faringitis aguda',
                    'Control en 7 días', '2026-08-14', '2026-08-14')
            """,
            (paciente_id,),
        )
        recipe_id = con.execute("SELECT id FROM recipes").fetchone()["id"]
        basedatos.insertar_recipe_item(
            con, recipe_id, 1, "Amoxicilina", "500 mg", "20 tabletas",
            "1 cada 8 horas", "Con las comidas",
        )
        con.execute(
            """
            INSERT INTO contador_anual (anio, ultimo_secuencial, creado_en, actualizado_en)
            VALUES (2026, 1, '2026-08-14', '2026-08-14')
            """
        )
        con.close()

    # -- tests -------------------------------------------------------------

    def test_base_nueva_arranca_al_dia(self):
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        self.assertEqual(basedatos.version_actual(con), basedatos.VERSION_ESQUEMA)
        self.assertGreaterEqual(basedatos.VERSION_ESQUEMA, 2)
        self.assertIn("indicaciones_generales", self._columnas(con, "recipes"))

    def test_una_base_v1_migra_a_v2_sin_perder_datos(self):
        self._base_v1_con_datos()

        con = basedatos.inicializar(self.ruta)  # es lo que hace cada arranque
        self.addCleanup(con.close)

        self.assertEqual(basedatos.version_actual(con), basedatos.VERSION_ESQUEMA)
        self.assertIn("indicaciones_generales", self._columnas(con, "recipes"))

        recipe = basedatos.obtener_recipe_por_codigo(con, "EC-2026-0001")
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe["diagnostico"], "Faringitis aguda")
        self.assertEqual(recipe["notas"], "Control en 7 días")
        self.assertEqual(recipe["anulado"], 0)
        # El récipe viejo no tenía el campo: queda en NULL, que es la verdad.
        self.assertIsNone(recipe["indicaciones_generales"])

        items = basedatos.obtener_items(con, recipe["id"])
        self.assertEqual([i["medicamento"] for i in items], ["Amoxicilina"])
        self.assertEqual(items[0]["indicaciones"], "Con las comidas")
        self.assertEqual(
            basedatos.obtener_paciente(con, recipe["paciente_id"])["nombre"], "Juan Pérez"
        )

    def test_tras_migrar_se_sigue_emitiendo_donde_se_había_quedado(self):
        """La numeración no se reinicia por migrar, y el campo nuevo ya sirve."""
        self._base_v1_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)

        paciente_id = basedatos.obtener_recipe_por_codigo(con, "EC-2026-0001")["paciente_id"]
        recipe = codigos.crear_recipe(
            con, paciente_id, ITEMS, fecha_emision="2026-08-15",
            indicaciones_generales="Reposo relativo",
        )
        self.assertEqual(recipe["codigo"], "EC-2026-0002")
        self.assertEqual(recipe["indicaciones_generales"], "Reposo relativo")

    def test_migrar_dos_veces_no_rompe_nada(self):
        """Idempotente: cada arranque llama a migrar y la base ya está al día."""
        self._base_v1_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)

        self.assertEqual(basedatos.migrar(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(basedatos.migrar(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(
            self._columnas(con, "recipes").count("indicaciones_generales"), 1
        )
        self.assertIsNotNone(basedatos.obtener_recipe_por_codigo(con, "EC-2026-0001"))

    def test_una_migracion_que_falla_no_deja_la_base_a_medias(self):
        """Cada versión se aplica entera o nada: si no, no se puede usar ALTER."""
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        version_buena = basedatos.version_actual(con)

        rotas = list(basedatos.MIGRACIONES) + [
            "ALTER TABLE recipes ADD COLUMN vigencia TEXT; esto no es SQL;"
        ]
        with mock.patch.object(basedatos, "MIGRACIONES", rotas), \
             mock.patch.object(basedatos, "VERSION_ESQUEMA", len(rotas)):
            with self.assertRaises(sqlite3.OperationalError):
                basedatos.migrar(con)

        self.assertFalse(con.in_transaction, "Quedó una transacción abierta.")
        self.assertEqual(basedatos.version_actual(con), version_buena)
        self.assertNotIn("vigencia", self._columnas(con, "recipes"))

    def test_una_base_del_futuro_no_se_toca(self):
        """Si el médico abre una base más nueva, se avisa en vez de romperla."""
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        con.execute(f"PRAGMA user_version = {basedatos.VERSION_ESQUEMA + 1}")
        with self.assertRaises(RuntimeError):
            basedatos.migrar(con)


if __name__ == "__main__":
    unittest.main(verbosity=2)
