"""Tests de `codigos.py` — la pieza que no puede fallar (§6, revisado por dec. 1 y 2).

Desde la 2.0 el código es **del paciente**: correlativo de por vida (`EC-0001`),
sin año y sin reinicio, y todos los récipes de ese paciente lo llevan impreso.
Acá se cubre lo que pide el documento con esa semántica: correlativo continuo,
concurrencia de dos escrituras simultáneas con hilos reales contra la misma
base, relleno de ceros, desborde a cinco dígitos, no reciclado, y la migración
de una base v2 —la que hoy tiene el médico en el disco— que conserva los
códigos con los que ya salieron impresos los récipes viejos.

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

    # -- ayudas ------------------------------------------------------------

    def emitir(self, fecha=None, paciente_id=None, **extra) -> dict:
        return codigos.crear_recipe(
            self.con, paciente_id or self.paciente_id, ITEMS, fecha_emision=fecha, **extra
        )

    def alta(self, nombre: str, **datos) -> int:
        return basedatos.crear_paciente(self.con, nombre, **datos)

    def codigo_de(self, paciente_id: int) -> str:
        return basedatos.obtener_paciente(self.con, paciente_id)["codigo"]


# --------------------------------------------------------------------------
# Formato y relleno de ceros del código de paciente (dec. 1, §6.5)
# --------------------------------------------------------------------------

class TestFormatoPaciente(unittest.TestCase):

    def test_relleno_de_ceros(self):
        """1 → 0001, 42 → 0042, 1234 → 1234: los tres casos del documento."""
        self.assertEqual(codigos.formatear_codigo_paciente("EC", 1), "EC-0001")
        self.assertEqual(codigos.formatear_codigo_paciente("EC", 42), "EC-0042")
        self.assertEqual(codigos.formatear_codigo_paciente("EC", 1234), "EC-1234")
        self.assertEqual(codigos.formatear_secuencial(7), "0007")
        self.assertEqual(codigos.formatear_secuencial(9999), "9999")

    def test_sin_anio(self):
        """El código del paciente no lleva año: es de por vida (dec. 1)."""
        self.assertEqual(codigos.formatear_codigo_paciente("EC", 1).count("-"), 1)

    def test_desborde_a_cinco_digitos(self):
        """Pasado 9999 se sigue con cinco dígitos, sin romper el formato (§6.5)."""
        self.assertEqual(codigos.formatear_codigo_paciente("EC", 10000), "EC-10000")
        self.assertEqual(codigos.formatear_codigo_paciente("EC", 99999), "EC-99999")
        self.assertEqual(codigos.formatear_codigo_paciente("EC", 100000), "EC-100000")

    def test_secuencial_invalido(self):
        for malo in (0, -1):
            with self.subTest(secuencial=malo):
                with self.assertRaises(ValueError):
                    codigos.formatear_codigo_paciente("EC", malo)

    def test_partir_codigo_paciente(self):
        self.assertEqual(codigos.partir_codigo_paciente("EC-0001"), ("EC", 1))
        self.assertEqual(codigos.partir_codigo_paciente("EC-0042"), ("EC", 42))
        self.assertEqual(codigos.partir_codigo_paciente("EC-10000"), ("EC", 10000))
        self.assertEqual(codigos.partir_codigo_paciente("mx-1234"), ("MX", 1234))

    def test_partir_codigo_paciente_invalido(self):
        for malo in ("", "EC", "EC-1", "0001", "EC/0001", "EC-2026-0001"):
            with self.subTest(codigo=malo):
                with self.assertRaises(ValueError):
                    codigos.partir_codigo_paciente(malo)

    def test_ida_y_vuelta(self):
        for secuencial in (1, 42, 1234, 9999, 10000, 123456):
            with self.subTest(secuencial=secuencial):
                codigo = codigos.formatear_codigo_paciente("EC", secuencial)
                self.assertEqual(codigos.partir_codigo_paciente(codigo), ("EC", secuencial))

    def test_los_dos_formatos_no_se_pisan(self):
        """El del récipe viejo tiene dos guiones; el del paciente, uno."""
        self.assertTrue(codigos.es_codigo_paciente("EC-0001"))
        self.assertFalse(codigos.es_codigo_paciente("EC-2026-0001"))
        with self.assertRaises(ValueError):
            codigos.partir_codigo("EC-0001")


# --------------------------------------------------------------------------
# Formato del código viejo del récipe: legado, para leer lo ya impreso
# --------------------------------------------------------------------------

class TestFormatoLegado(unittest.TestCase):

    def test_se_siguen_entendiendo_los_codigos_viejos(self):
        self.assertEqual(codigos.formatear_codigo("EC", 2026, 1), "EC-2026-0001")
        self.assertEqual(codigos.partir_codigo("EC-2026-0042"), ("EC", 2026, 42))
        self.assertEqual(codigos.partir_codigo("EC-2026-10000"), ("EC", 2026, 10000))

    def test_partir_codigo_invalido(self):
        for malo in ("", "EC-2026", "EC-26-0001", "EC-2026-1", "2026-0001", "EC/2026/0001"):
            with self.subTest(codigo=malo):
                with self.assertRaises(ValueError):
                    codigos.partir_codigo(malo)


# --------------------------------------------------------------------------
# Prefijo configurable (§6.6)
# --------------------------------------------------------------------------

class TestPrefijo(BaseEnDisco):

    def test_por_defecto_es_ec(self):
        self.assertEqual(codigos.obtener_prefijo(self.con), "EC")
        self.assertEqual(self.codigo_de(self.paciente_id), "EC-0001")
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-0001")

    def test_prefijo_configurable(self):
        codigos.guardar_prefijo(self.con, "MX")
        self.assertEqual(codigos.obtener_prefijo(self.con), "MX")
        otro = self.alta("María Gómez", cedula="V-777")
        self.assertEqual(self.codigo_de(otro), "MX-0002")
        self.assertTrue(self.emitir("2026-08-14", paciente_id=otro)["codigo"].startswith("MX-"))

    def test_los_ya_asignados_conservan_su_prefijo(self):
        """Cambiar el prefijo no toca los códigos ya dados (§6.6, dec. 1)."""
        viejo = self.codigo_de(self.paciente_id)
        codigos.guardar_prefijo(self.con, "ZZ")
        nuevo = self.alta("María Gómez", cedula="V-777")

        self.assertEqual(viejo, "EC-0001")
        self.assertEqual(self.codigo_de(nuevo), "ZZ-0002")
        # El paciente viejo sigue siendo EC, y sus récipes también.
        self.assertEqual(self.codigo_de(self.paciente_id), "EC-0001")
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-0001")
        # Y el secuencial es continuo: el prefijo no reinicia la numeración.

    def test_prefijo_se_normaliza_a_mayusculas(self):
        self.assertEqual(codigos.guardar_prefijo(self.con, " ec "), "EC")
        self.assertEqual(codigos.obtener_prefijo(self.con), "EC")

    def test_prefijo_invalido(self):
        for malo in ("", "   ", "EC-", "E C 1 2 3 4 5 6 7 8 9 0 1", "ÉC", "EC/1"):
            with self.subTest(prefijo=malo):
                with self.assertRaises(ValueError):
                    codigos.guardar_prefijo(self.con, malo)

    def test_prefijo_corrupto_no_impide_dar_de_alta(self):
        """Una base tocada a mano no puede dejar al médico sin poder atender."""
        basedatos.guardar_config(self.con, codigos.CLAVE_PREFIJO, "!!!")
        self.assertEqual(codigos.obtener_prefijo(self.con), "EC")
        self.assertEqual(self.codigo_de(self.alta("María Gómez")), "EC-0002")


# --------------------------------------------------------------------------
# Numeración de pacientes: correlativa y de por vida (dec. 1)
# --------------------------------------------------------------------------

class TestNumeracionPacientes(BaseEnDisco):

    def test_tres_seguidos_son_0001_0002_0003(self):
        """Criterio de aceptación de §12, ahora contando pacientes."""
        otros = [self.alta("María Gómez"), self.alta("Pedro Ruiz")]
        self.assertEqual(
            [self.codigo_de(self.paciente_id)] + [self.codigo_de(p) for p in otros],
            ["EC-0001", "EC-0002", "EC-0003"],
        )

    def test_no_hay_reinicio_de_anio(self):
        """El 1 de enero NO vuelve a 0001: el código es de por vida (dec. 1)."""
        self.assertEqual(self.emitir("2026-12-31")["codigo"], "EC-0001")
        segundo = self.alta("María Gómez")
        self.assertEqual(self.emitir("2027-01-01", paciente_id=segundo)["codigo"], "EC-0002")
        tercero = self.alta("Pedro Ruiz")
        self.assertEqual(self.emitir("2027-01-02", paciente_id=tercero)["codigo"], "EC-0003")

    def test_dos_recipes_del_mismo_paciente_comparten_codigo(self):
        """Lo que pidió el médico (dec. 2): el código impreso es el suyo."""
        primero = self.emitir("2026-08-14")
        segundo = self.emitir("2027-03-09")
        self.assertEqual(primero["codigo"], "EC-0001")
        self.assertEqual(segundo["codigo"], "EC-0001")
        self.assertNotEqual(primero["id"], segundo["id"])
        # Cada récipe conserva su registro propio para el historial.
        self.assertEqual(
            [f["fecha_emision"] for f in
             basedatos.listar_recipes_por_codigo(self.con, "EC-0001")],
            ["2027-03-09", "2026-08-14"],
        )

    def test_recipes_de_pacientes_distintos_llevan_codigos_distintos(self):
        otra = self.alta("María Gómez", cedula="V-777")
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-0001")
        self.assertEqual(self.emitir("2026-08-14", paciente_id=otra)["codigo"], "EC-0002")

    def test_el_recipe_no_saca_numero_propio(self):
        """`anio` y `secuencial` quedan de legado: en NULL para lo nuevo."""
        recipe = self.emitir("2027-03-09")
        self.assertIsNone(recipe["anio"])
        self.assertIsNone(recipe["secuencial"])
        self.assertEqual(basedatos.obtener_ultimo_secuencial(self.con, 2027), 0)

    def test_emitir_no_consume_numeros_de_paciente(self):
        """Diez récipes del mismo paciente no mueven el contador."""
        for _ in range(10):
            self.emitir("2026-08-14")
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(self.con), 1)
        self.assertEqual(self.codigo_de(self.alta("María Gómez")), "EC-0002")

    def test_sin_fecha_usa_el_dia_de_hoy(self):
        """Sin fecha explícita manda el reloj de la máquina, que es el caso real."""
        recipe = self.emitir()
        self.assertEqual(recipe["codigo"], "EC-0001")
        self.assertTrue(recipe["fecha_emision"].startswith(date.today().isoformat()))

    def test_vista_previa_no_quema_numero(self):
        """Un formulario abandonado no gasta un código (§6.2)."""
        self.assertEqual(codigos.proximo_codigo_paciente(self.con), "EC-0002")
        self.assertEqual(codigos.proximo_codigo_paciente(self.con), "EC-0002")
        self.assertEqual(codigos.proximo_secuencial_paciente(self.con), 2)
        self.assertEqual(self.codigo_de(self.alta("María Gómez")), "EC-0002")

    def test_fecha_invalida_falla_temprano(self):
        for mala in ("14/08/2026", "2026-13-40", "ayer", "26-08-14"):
            with self.subTest(fecha=mala):
                with self.assertRaises(ValueError):
                    self.emitir(mala)

    def test_recipe_sin_medicamentos_no_toca_nada(self):
        with self.assertRaises(ValueError):
            codigos.crear_recipe(self.con, self.paciente_id, [], fecha_emision="2026-08-14")
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(self.con), 1)

    def test_recipe_a_un_paciente_que_no_existe_falla_sin_dejar_rastro(self):
        """La transacción es una sola: si algo falla, no queda nada a medias."""
        with self.assertRaises(ValueError):
            codigos.crear_recipe(self.con, 999_999, ITEMS, fecha_emision="2026-08-14")
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(self.con), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0], 0)
        self.assertEqual(self.emitir("2026-08-14")["codigo"], "EC-0001")

    def test_un_alta_fallida_no_quema_un_numero(self):
        """Cédula repetida: el alta se cae y el código vuelve a estar libre."""
        with self.assertRaises(sqlite3.IntegrityError):
            basedatos.crear_paciente(self.con, "Otro Juan", cedula="V-12345678")
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(self.con), 1)
        self.assertEqual(self.codigo_de(self.alta("María Gómez")), "EC-0002")

    def test_asignar_codigo_paciente_devuelve_secuencial_y_codigo(self):
        secuencial, codigo = codigos.asignar_codigo_paciente(self.con)
        self.assertEqual((secuencial, codigo), (2, "EC-0002"))
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(self.con), 2)

    def test_asignar_codigo_paciente_respeta_la_transaccion_de_quien_llama(self):
        """Metido en una transacción más grande, se deshace con ella."""
        with self.assertRaises(RuntimeError):
            with basedatos.transaccion(self.con, inmediata=True):
                codigos.asignar_codigo_paciente(self.con)
                raise RuntimeError("algo salió mal después")
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(self.con), 1)

    def test_asegurar_le_da_codigo_a_un_paciente_que_no_lo_tenia(self):
        """Un paciente cargado por otro camino igual se lleva su número.

        Le toca el **siguiente** libre, no el 0001: el 1 ya se reservó cuando
        se lo dio de alta y los números no se reciclan (§6.4).
        """
        self.con.execute(
            "UPDATE pacientes SET codigo = NULL WHERE id = ?", (self.paciente_id,)
        )
        self.assertEqual(codigos.asegurar_codigo_paciente(self.con, self.paciente_id), "EC-0002")
        self.assertEqual(self.codigo_de(self.paciente_id), "EC-0002")

    def test_emitir_le_da_codigo_a_un_paciente_viejo_sin_codigo(self):
        """El récipe nunca sale sin código: si falta, se asigna al emitir."""
        self.con.execute(
            "UPDATE pacientes SET codigo = NULL WHERE id = ?", (self.paciente_id,)
        )
        recipe = self.emitir("2026-08-14")
        self.assertEqual(recipe["codigo"], "EC-0002")
        self.assertEqual(self.codigo_de(self.paciente_id), "EC-0002")

    def test_asegurar_no_cambia_el_que_ya_tenia(self):
        codigos.guardar_prefijo(self.con, "ZZ")
        self.assertEqual(codigos.asegurar_codigo_paciente(self.con, self.paciente_id), "EC-0001")

    def test_se_puede_buscar_al_paciente_por_su_codigo(self):
        """Es lo que el médico tiene a mano mirando un récipe impreso."""
        self.alta("María Gómez", cedula="V-777")
        encontrados = basedatos.buscar_pacientes(self.con, "EC-0002")
        self.assertEqual([f["nombre"] for f in encontrados], ["María Gómez"])
        self.assertEqual(
            basedatos.obtener_paciente_por_codigo(self.con, "EC-0001")["id"],
            self.paciente_id,
        )
        self.assertIsNone(basedatos.obtener_paciente_por_codigo(self.con, "EC-9999"))

    def test_asegurar_falla_si_el_paciente_no_existe(self):
        with self.assertRaises(ValueError):
            codigos.asegurar_codigo_paciente(self.con, 999_999)


# --------------------------------------------------------------------------
# Desborde real, dando de alta (§6.5)
# --------------------------------------------------------------------------

class TestDesborde(BaseEnDisco):

    def _sembrar_contador(self, ultimo: int) -> None:
        """Deja el contador arrancado en `ultimo` sin dar de alta 9999 pacientes."""
        momento = basedatos.ahora_iso()
        self.con.execute(
            """
            INSERT INTO contador_pacientes (id, ultimo_secuencial, creado_en, actualizado_en)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET ultimo_secuencial = excluded.ultimo_secuencial
            """,
            (ultimo, momento, momento),
        )

    def test_9999_pasa_a_cinco_digitos(self):
        """Criterio de aceptación de §12: 9999 → EC-10000, sin romperse."""
        self._sembrar_contador(9998)
        self.assertEqual(self.codigo_de(self.alta("Paciente 9999")), "EC-9999")
        desbordado = self.alta("Paciente 10000")
        self.assertEqual(self.codigo_de(desbordado), "EC-10000")
        self.assertEqual(self.codigo_de(self.alta("Paciente 10001")), "EC-10001")

    def test_el_codigo_desbordado_se_lee_de_vuelta(self):
        self._sembrar_contador(9999)
        paciente = self.alta("Paciente 10000")
        codigo = self.codigo_de(paciente)
        self.assertEqual(codigos.partir_codigo_paciente(codigo), ("EC", 10000))
        self.assertEqual(
            basedatos.obtener_paciente_por_codigo(self.con, codigo)["id"], paciente
        )
        self.assertEqual(self.emitir(paciente_id=paciente)["codigo"], "EC-10000")

    def test_el_desborde_ordena_bien_el_maximo(self):
        """El máximo se compara como número, no como texto: 10000 > 9999."""
        self._sembrar_contador(9999)
        self.alta("Paciente 10000")
        self.con.execute("DELETE FROM contador_pacientes")
        self.assertEqual(codigos.proximo_secuencial_paciente(self.con), 10001)


# --------------------------------------------------------------------------
# No reciclado (§6.4) y anulación (§2.4)
# --------------------------------------------------------------------------

class TestNoReciclado(BaseEnDisco):

    def test_contador_perdido_no_recicla_numeros(self):
        """Cinturón de seguridad: aunque el contador se pierda, no se repite."""
        self.alta("María Gómez")
        self.alta("Pedro Ruiz")
        self.con.execute("DELETE FROM contador_pacientes")

        self.assertEqual(self.codigo_de(self.alta("Ana Díaz")), "EC-0004")

    def test_contador_atrasado_no_recicla_numeros(self):
        """Una base restaurada a medias tampoco puede devolver un número usado."""
        self.alta("María Gómez")
        self.con.execute("UPDATE contador_pacientes SET ultimo_secuencial = 1")
        self.assertEqual(self.codigo_de(self.alta("Pedro Ruiz")), "EC-0003")

    def test_el_codigo_de_paciente_no_se_puede_duplicar(self):
        """La base misma lo impide: el índice de `pacientes.codigo` es único."""
        with self.assertRaises(sqlite3.IntegrityError):
            basedatos.crear_paciente(self.con, "Otro Juan", codigo="EC-0001")

    def test_anular_un_recipe_no_toca_el_codigo_del_paciente(self):
        primero = self.emitir("2026-08-14")
        segundo = self.emitir("2026-08-15")
        basedatos.anular_recipe(self.con, segundo["id"], "Error de dosis")

        tercero = self.emitir("2026-08-16")
        self.assertEqual(
            [primero["codigo"], segundo["codigo"], tercero["codigo"]],
            ["EC-0001"] * 3,
        )
        guardado = basedatos.obtener_recipe(self.con, segundo["id"])
        self.assertEqual(guardado["anulado"], 1)
        self.assertEqual(guardado["motivo_anulacion"], "Error de dosis")
        self.assertIsNotNone(guardado["fecha_anulacion"])
        # El anulado sigue estando: se anula, no se borra (§2.4).
        self.assertEqual(len(basedatos.listar_recipes_por_codigo(self.con, "EC-0001")), 3)

    def test_anular_todos_los_recipes_no_libera_el_codigo(self):
        recipes = [self.emitir("2026-08-14") for _ in range(3)]
        for recipe in recipes:
            basedatos.anular_recipe(self.con, recipe["id"], "Reimpresión mal hecha")
        self.assertEqual(self.codigo_de(self.paciente_id), "EC-0001")
        self.assertEqual(self.codigo_de(self.alta("María Gómez")), "EC-0002")


# --------------------------------------------------------------------------
# Concurrencia: dos ventanas escribiendo a la vez (§6.3)
# --------------------------------------------------------------------------

class TestConcurrencia(BaseEnDisco):

    def _correr(self, tarea, hilos: int, por_hilo: int) -> list:
        arranque = threading.Barrier(hilos)
        salida: list = []
        errores: list[Exception] = []

        def trabajar(indice: int) -> None:
            try:
                con = basedatos.inicializar(self.ruta)
            except Exception as error:  # pragma: no cover
                errores.append(error)
                return
            try:
                arranque.wait(timeout=30)
                for numero in range(por_hilo):
                    salida.append(tarea(con, indice, numero))
            except Exception as error:
                errores.append(error)
            finally:
                con.close()

        trabajadores = [threading.Thread(target=trabajar, args=(i,)) for i in range(hilos)]
        for hilo in trabajadores:
            hilo.start()
        for hilo in trabajadores:
            hilo.join(timeout=60)
            self.assertFalse(hilo.is_alive(), "Un hilo quedó colgado esperando el lock.")
        self.assertEqual(errores, [], f"Los hilos fallaron: {errores}")
        return salida

    # -- altas de pacientes ------------------------------------------------

    @staticmethod
    def _alta(con, hilo: int, numero: int) -> str:
        paciente_id = basedatos.crear_paciente(con, f"Paciente {hilo}-{numero}")
        return basedatos.obtener_paciente(con, paciente_id)["codigo"]

    def test_dos_ventanas_simultaneas_no_repiten_codigo_de_paciente(self):
        """El caso del documento: el médico con dos ventanas abiertas (§6.3)."""
        por_hilo = 25
        emitidos = self._correr(self._alta, hilos=2, por_hilo=por_hilo)
        total = 2 * por_hilo

        self.assertEqual(len(emitidos), total)
        self.assertEqual(len(set(emitidos)), total, "Se repitió un código.")
        self.assertEqual(
            sorted(codigos.partir_codigo_paciente(c)[1] for c in emitidos),
            list(range(2, total + 2)),  # el 1 es el paciente del setUp
            "La serie quedó con huecos o saltos.",
        )
        self.assertEqual(
            basedatos.obtener_ultimo_secuencial_paciente(self.con), total + 1
        )

    def test_cuatro_escritores_simultaneos(self):
        """Más presión de la que la app va a ver nunca, para que el margen sobre."""
        por_hilo = 15
        emitidos = self._correr(self._alta, hilos=4, por_hilo=por_hilo)
        total = 4 * por_hilo

        self.assertEqual(len(set(emitidos)), total)
        filas = self.con.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT codigo) AS distintos FROM pacientes"
        ).fetchone()
        self.assertEqual(filas["n"], total + 1)
        self.assertEqual(filas["distintos"], total + 1)

    # -- récipes del mismo paciente ---------------------------------------

    def _emitir_concurrente(self, con, hilo: int, numero: int) -> str:
        return codigos.crear_recipe(
            con, self.paciente_id, ITEMS, fecha_emision="2026-08-14"
        )["codigo"]

    def test_dos_ventanas_emitiendo_al_mismo_paciente(self):
        """Todos los récipes salen con el mismo código y ninguno se pierde."""
        por_hilo = 20
        emitidos = self._correr(self._emitir_concurrente, hilos=2, por_hilo=por_hilo)
        total = 2 * por_hilo

        self.assertEqual(emitidos, ["EC-0001"] * total)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0], total)
        # Y el paciente sigue teniendo un solo código.
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(self.con), 1)

    def test_los_renglones_quedan_pegados_a_su_recipe(self):
        """Con escrituras cruzadas, ningún récipe se queda sin sus renglones."""
        self._correr(self._emitir_concurrente, hilos=3, por_hilo=10)
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

    def test_el_recipe_puede_colgar_de_una_consulta(self):
        """El récipe emitido en una visita aparece en su línea de tiempo."""
        consulta_id = basedatos.crear_consulta(
            self.con, self.paciente_id, fecha="2026-08-14", motivo="Control de peso"
        )
        recipe = self.emitir("2026-08-14", consulta_id=consulta_id)
        self.assertEqual(recipe["consulta_id"], consulta_id)
        self.assertEqual(
            basedatos.listar_consultas(self.con, self.paciente_id)[0]["cantidad_recipes"], 1
        )

    def test_el_ultimo_recipe_es_de_donde_sale_el_tratamiento_del_informe(self):
        self.emitir("2026-08-14")
        ultimo = self.emitir("2026-09-01")
        fila = basedatos.ultimo_recipe_de_paciente(self.con, self.paciente_id)
        self.assertEqual(fila["id"], ultimo["id"])
        basedatos.anular_recipe(self.con, ultimo["id"], "Error")
        self.assertEqual(
            basedatos.ultimo_recipe_de_paciente(self.con, self.paciente_id)["fecha_emision"],
            "2026-08-14",
        )


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
        self.assertEqual(recipe["codigo"], "EC-0001")
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
        fila = basedatos.buscar_recipes(self.con, "EC-0001")[0]
        self.assertEqual(fila["indicaciones_generales"], self.TEXTO)


# --------------------------------------------------------------------------
# Migraciones versionadas: la base que el médico ya tiene en su disco
# --------------------------------------------------------------------------

class TestMigraciones(unittest.TestCase):

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_migr_"))
        # Como cleanup y no en `tearDown`: los cleanups corren después de
        # `tearDown` y en orden inverso, así que registrado acá queda último y
        # para entonces ya se cerraron las conexiones de cada test. En Windows,
        # con `recipes.db` todavía tomado, el `rmtree` fallaba entero y
        # `ignore_errors` se lo tragaba en silencio: quedaba una carpeta en
        # %TEMP% por cada test de migración.
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        self.ruta = self.carpeta / "recipes.db"

    # -- utilidades --------------------------------------------------------

    def _columnas(self, con: sqlite3.Connection, tabla: str) -> list[str]:
        return [f["name"] for f in con.execute(f"PRAGMA table_info({tabla})")]

    def _tablas(self, con: sqlite3.Connection) -> set[str]:
        return {f["name"] for f in
                con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def _base_v2_con_datos(self, prefijo: str | None = None) -> None:
        """Crea una base con el esquema v2 y datos adentro.

        Se aplican los scripts v1 y v2 reales y se para la versión en 2: es
        exactamente la base que quedó en la máquina del médico con la 1.0.1.
        Los pacientes se insertan a mano porque `crear_paciente` ya asigna
        código, y en la v2 esa columna todavía no existe.
        """
        con = basedatos.conectar(self.ruta)
        con.executescript(basedatos.MIGRACIONES[0])
        con.executescript(basedatos.MIGRACIONES[1])
        con.execute("PRAGMA user_version = 2")

        self.assertEqual(basedatos.version_actual(con), 2)
        self.assertNotIn("codigo", self._columnas(con, "pacientes"))

        if prefijo is not None:
            basedatos.guardar_config(con, codigos.CLAVE_PREFIJO, prefijo)

        for nombre, cedula in (("Juan Pérez", "V-12345678"),
                               ("María Gómez", "V-777"),
                               ("Pedro Ruiz", None)):
            con.execute(
                """
                INSERT INTO pacientes (nombre, nombre_norm, cedula, edad, veces_atendido,
                                       creado_en, actualizado_en)
                VALUES (?, ?, ?, 40, 1, '2026-01-01', '2026-01-01')
                """,
                (nombre, basedatos.normalizar(nombre), cedula),
            )
        con.execute(
            """
            INSERT INTO recipes (codigo, anio, secuencial, paciente_id, fecha_emision,
                                 diagnostico, notas, indicaciones_generales,
                                 creado_en, actualizado_en)
            VALUES ('EC-2026-0001', 2026, 1, 1, '2026-08-14', 'Faringitis aguda',
                    'Control en 7 días', 'Reposo relativo', '2026-08-14', '2026-08-14')
            """
        )
        con.execute(
            """
            INSERT INTO recipes (codigo, anio, secuencial, paciente_id, fecha_emision,
                                 creado_en, actualizado_en)
            VALUES ('EC-2026-0002', 2026, 2, 2, '2026-08-15', '2026-08-15', '2026-08-15')
            """
        )
        basedatos.insertar_recipe_item(
            con, 1, 1, "Amoxicilina", "500 mg", "20 tabletas",
            "1 cada 8 horas", "Con las comidas",
        )
        basedatos.insertar_recipe_item(con, 2, 1, "Losartán", "50 mg", "30 tabletas", "1 diaria")
        con.execute(
            """
            INSERT INTO contador_anual (anio, ultimo_secuencial, creado_en, actualizado_en)
            VALUES (2026, 2, '2026-08-14', '2026-08-14')
            """
        )
        con.close()

    # -- tests -------------------------------------------------------------

    def test_base_nueva_arranca_al_dia(self):
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        self.assertEqual(basedatos.version_actual(con), basedatos.VERSION_ESQUEMA)
        self.assertGreaterEqual(basedatos.VERSION_ESQUEMA, 3)
        self.assertIn("codigo", self._columnas(con, "pacientes"))
        self.assertLessEqual(
            {"historias", "consultas", "signos_vitales", "anexos", "mediciones",
             "informes", "informe_anexos", "contador_pacientes"},
            self._tablas(con),
        )

    def test_los_pacientes_existentes_reciben_codigo_por_orden_de_id(self):
        self._base_v2_con_datos()
        con = basedatos.inicializar(self.ruta)  # es lo que hace cada arranque
        self.addCleanup(con.close)

        self.assertEqual(
            [(f["id"], f["codigo"]) for f in con.execute("SELECT * FROM pacientes ORDER BY id")],
            [(1, "EC-0001"), (2, "EC-0002"), (3, "EC-0003")],
        )
        # Y el contador queda parado donde corresponde, sin reciclar.
        self.assertEqual(basedatos.obtener_ultimo_secuencial_paciente(con), 3)
        self.assertEqual(codigos.proximo_codigo_paciente(con), "EC-0004")

    def test_la_migracion_respeta_el_prefijo_configurado(self):
        self._base_v2_con_datos(prefijo="MX")
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        self.assertEqual(
            [f["codigo"] for f in con.execute("SELECT codigo FROM pacientes ORDER BY id")],
            ["MX-0001", "MX-0002", "MX-0003"],
        )

    def test_un_prefijo_corrupto_no_frena_la_migracion(self):
        self._base_v2_con_datos(prefijo="!!!")
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        self.assertEqual(
            con.execute("SELECT codigo FROM pacientes WHERE id = 1").fetchone()["codigo"],
            "EC-0001",
        )

    def test_los_recipes_viejos_conservan_el_codigo_con_el_que_se_imprimieron(self):
        """Un documento emitido es histórico: no se le puede cambiar el código."""
        self._base_v2_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)

        filas = list(con.execute("SELECT * FROM recipes ORDER BY id"))
        self.assertEqual([f["codigo"] for f in filas], ["EC-2026-0001", "EC-2026-0002"])
        self.assertEqual([f["anio"] for f in filas], [2026, 2026])
        self.assertEqual([f["secuencial"] for f in filas], [1, 2])
        self.assertEqual(filas[0]["diagnostico"], "Faringitis aguda")
        self.assertEqual(filas[0]["notas"], "Control en 7 días")
        self.assertEqual(filas[0]["indicaciones_generales"], "Reposo relativo")
        self.assertEqual(filas[0]["anulado"], 0)
        self.assertIsNone(filas[0]["consulta_id"])

    def test_la_reconstruccion_de_recipes_no_se_lleva_los_renglones(self):
        """La tabla se rehace entera: los renglones tienen que sobrevivir."""
        self._base_v2_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)

        self.assertEqual(
            [i["medicamento"] for i in basedatos.obtener_items(con, 1)], ["Amoxicilina"]
        )
        self.assertEqual(basedatos.obtener_items(con, 1)[0]["indicaciones"], "Con las comidas")
        self.assertEqual(
            [i["medicamento"] for i in basedatos.obtener_items(con, 2)], ["Losartán"]
        )
        self.assertEqual(con.execute("SELECT COUNT(*) FROM recipe_items").fetchone()[0], 2)
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_el_codigo_del_recipe_deja_de_ser_unico(self):
        """Dos récipes del mismo paciente pueden llevar el mismo código (dec. 2)."""
        self._base_v2_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)

        primero = codigos.crear_recipe(con, 1, ITEMS, fecha_emision="2026-08-16")
        segundo = codigos.crear_recipe(con, 1, ITEMS, fecha_emision="2026-08-17")
        self.assertEqual(primero["codigo"], "EC-0001")
        self.assertEqual(segundo["codigo"], "EC-0001")
        self.assertEqual(len(basedatos.listar_recipes_por_codigo(con, "EC-0001")), 2)

    def test_las_claves_foraneas_quedan_encendidas_despues_de_migrar(self):
        """Se apagan solo para reconstruir la tabla; después vuelven."""
        self._base_v2_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        self.assertEqual(int(con.execute("PRAGMA foreign_keys").fetchone()[0]), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO recipes (codigo, paciente_id, fecha_emision, creado_en, actualizado_en)
                VALUES ('EC-0001', 999999, '2026-08-14', 'x', 'x')
                """
            )

    def test_migrar_dos_veces_no_rompe_nada(self):
        """Idempotente: cada arranque llama a migrar y la base ya está al día."""
        self._base_v2_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)

        self.assertEqual(basedatos.migrar(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(basedatos.migrar(con), basedatos.VERSION_ESQUEMA)
        self.assertEqual(self._columnas(con, "pacientes").count("codigo"), 1)
        self.assertEqual(
            [f["codigo"] for f in con.execute("SELECT codigo FROM pacientes ORDER BY id")],
            ["EC-0001", "EC-0002", "EC-0003"],
        )
        self.assertEqual(con.execute("SELECT COUNT(*) FROM recipe_items").fetchone()[0], 2)

    def test_tras_migrar_se_sigue_atendiendo_donde_se_habia_quedado(self):
        """La numeración no se reinicia por migrar, y lo nuevo ya sirve."""
        self._base_v2_con_datos()
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)

        recipe = codigos.crear_recipe(
            con, 2, ITEMS, fecha_emision="2026-08-16",
            indicaciones_generales="Reposo relativo",
        )
        self.assertEqual(recipe["codigo"], "EC-0002")
        self.assertEqual(recipe["indicaciones_generales"], "Reposo relativo")

        nuevo = basedatos.crear_paciente(con, "Ana Díaz", cedula="V-555")
        self.assertEqual(basedatos.obtener_paciente(con, nuevo)["codigo"], "EC-0004")

    def test_una_base_v1_llega_hasta_la_ultima_version(self):
        """Una base que se saltó una actualización recorre todos los scripts."""
        con = basedatos.conectar(self.ruta)
        con.executescript(basedatos.MIGRACIONES[0])
        con.execute("PRAGMA user_version = 1")
        con.execute(
            """
            INSERT INTO pacientes (nombre, nombre_norm, veces_atendido, creado_en, actualizado_en)
            VALUES ('Juan Pérez', 'juan perez', 0, '2026-01-01', '2026-01-01')
            """
        )
        con.close()

        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        self.assertEqual(basedatos.version_actual(con), basedatos.VERSION_ESQUEMA)
        self.assertIn("indicaciones_generales", self._columnas(con, "recipes"))
        self.assertEqual(
            con.execute("SELECT codigo FROM pacientes").fetchone()["codigo"], "EC-0001"
        )

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
        self.assertEqual(int(con.execute("PRAGMA foreign_keys").fetchone()[0]), 1)

    def test_una_base_del_futuro_no_se_toca(self):
        """Si el médico abre una base más nueva, se avisa en vez de romperla."""
        con = basedatos.inicializar(self.ruta)
        self.addCleanup(con.close)
        con.execute(f"PRAGMA user_version = {basedatos.VERSION_ESQUEMA + 1}")
        with self.assertRaises(RuntimeError):
            basedatos.migrar(con)


if __name__ == "__main__":
    unittest.main(verbosity=2)
