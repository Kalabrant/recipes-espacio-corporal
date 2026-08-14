"""Tests de `respaldo.py` — las copias de seguridad de §10.

Cubre lo que pide el documento: el ZIP del día repetido pasa a `-2` y `-3`,
`conservar_ultimos` borra el noveno más viejo y **no toca archivos ajenos**,
y un respaldo tomado con el WAL activo se restaura y abre con los récipes
adentro (que es la única prueba que importa: un respaldo que no restaura no
es un respaldo).

Solo `unittest` y `zipfile` de la stdlib (§3).
Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import basedatos  # noqa: E402
import codigos  # noqa: E402
import respaldo  # noqa: E402


ITEMS = [{"medicamento": "Amoxicilina", "presentacion": "500 mg",
          "cantidad": "20 tabletas", "dosis": "1 cada 8 horas",
          "indicaciones": "Con las comidas"}]


class CarpetaDeDatos(unittest.TestCase):
    """Carpeta de datos completa, como la del médico (§4)."""

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_respaldo_"))
        self.dir_datos = self.carpeta / "Recipes"
        for sub in ("datos", "pdf", "registro", "respaldos", "recursos"):
            (self.dir_datos / sub).mkdir(parents=True)
        self.ruta_db = self.dir_datos / "datos" / "recipes.db"
        self.con = basedatos.inicializar(self.ruta_db)
        (self.dir_datos / "registro" / "registro_recipes.xlsx").write_bytes(b"PK\x03\x04 falso")

    def tearDown(self) -> None:
        self.con.close()
        shutil.rmtree(self.carpeta, ignore_errors=True)

    # -- ayudas ------------------------------------------------------------

    def emitir(self, nombre="Juan Pérez", cedula="V-12345678") -> dict:
        paciente_id = basedatos.obtener_o_crear_paciente(
            self.con, nombre, cedula=cedula, edad=40
        )
        return codigos.crear_recipe(self.con, int(paciente_id), ITEMS,
                                    fecha_emision="2026-08-14")

    def falso(self, nombre: str) -> Path:
        """Crea un archivo en `respaldos\\` con el nombre dado."""
        ruta = self.dir_datos / "respaldos" / nombre
        ruta.write_bytes(b"contenido")
        return ruta

    def nombres_respaldos(self) -> list[str]:
        return sorted(r.name for r in (self.dir_datos / "respaldos").iterdir())


# --------------------------------------------------------------------------
# Crear el ZIP
# --------------------------------------------------------------------------

class TestRespaldarAhora(CarpetaDeDatos):

    def test_crea_el_zip_del_dia_con_datos_y_registro(self):
        self.emitir()
        archivo = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))

        self.assertEqual(archivo.name, "respaldo-2026-08-14.zip")
        self.assertEqual(archivo.parent, self.dir_datos / "respaldos")
        self.assertTrue(zipfile.is_zipfile(archivo))

        with zipfile.ZipFile(archivo) as zip_:
            nombres = set(zip_.namelist())
        self.assertIn("datos/recipes.db", nombres)
        self.assertIn("registro/registro_recipes.xlsx", nombres)
        # Los auxiliares del WAL no van: la copia ya es consistente.
        self.assertFalse([n for n in nombres if n.endswith(("-wal", "-shm"))], nombres)
        # Los PDF no entran al respaldo.
        self.assertFalse([n for n in nombres if n.startswith("pdf/")], nombres)

    def test_no_deja_temporales(self):
        respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))
        sobrantes = [r.name for r in (self.dir_datos / "respaldos").iterdir()
                     if r.suffix == ".tmp"]
        self.assertEqual(sobrantes, [])

    def test_repetir_el_mismo_dia_agrega_2_y_3(self):
        primero = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))
        segundo = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))
        tercero = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))

        self.assertEqual(primero.name, "respaldo-2026-08-14.zip")
        self.assertEqual(segundo.name, "respaldo-2026-08-14-2.zip")
        self.assertEqual(tercero.name, "respaldo-2026-08-14-3.zip")
        # Ninguno se pisó: los tres están y son ZIP válidos.
        for ruta in (primero, segundo, tercero):
            self.assertTrue(zipfile.is_zipfile(ruta), ruta.name)

    def test_el_numero_no_vuelve_atras_cuando_la_poda_libera_un_nombre(self):
        """Respaldar nueve veces el mismo día no puede borrar el noveno.

        Regresión: el nombre se elegía buscando el primer hueco libre. Con ocho
        respaldos (``-2`` a ``-9``), `conservar_ultimos` ya había borrado
        ``respaldo-2026-08-14.zip``, así que el noveno volvía a llamarse igual
        que el original, quedaba ordenado como el MÁS VIEJO del día y la poda de
        esa misma corrida lo borraba recién creado: el médico pedía un respaldo
        y el respaldo desaparecía (y la respuesta reventaba al medir su tamaño).
        """
        hechos = []
        for _ in range(9):
            archivo = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))
            respaldo.conservar_ultimos(self.dir_datos, 8)
            hechos.append(archivo)
            self.assertTrue(archivo.is_file(),
                            f"{archivo.name} desapareció apenas creado")

        self.assertEqual(hechos[-1].name, "respaldo-2026-08-14-9.zip")
        self.assertEqual(len(self.nombres_respaldos()), 8)
        # El más nuevo siempre sobrevive a la poda; el que cae es el más viejo.
        self.assertIn("respaldo-2026-08-14-9.zip", self.nombres_respaldos())
        self.assertNotIn("respaldo-2026-08-14.zip", self.nombres_respaldos())

    def test_la_numeracion_sigue_al_mas_alto_del_dia(self):
        # Un hueco en el medio (no está el -2) no hace retroceder la cuenta.
        self.falso("respaldo-2026-08-14.zip")
        self.falso("respaldo-2026-08-14-5.zip")
        ruta = respaldo.ruta_respaldo_nueva(self.dir_datos, date(2026, 8, 14))
        self.assertEqual(ruta.name, "respaldo-2026-08-14-6.zip")

    def test_el_primero_del_dia_no_lleva_numero(self):
        self.falso("respaldo-2026-08-13-4.zip")   # de otro día: no cuenta
        ruta = respaldo.ruta_respaldo_nueva(self.dir_datos, date(2026, 8, 14))
        self.assertEqual(ruta.name, "respaldo-2026-08-14.zip")

    def test_crea_la_carpeta_de_respaldos_si_no_esta(self):
        shutil.rmtree(self.dir_datos / "respaldos")
        archivo = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))
        self.assertTrue(archivo.is_file())

    def test_carpeta_de_datos_inexistente_avisa_con_mensaje_util(self):
        with self.assertRaises(respaldo.RespaldoError) as caja:
            respaldo.respaldar_ahora(self.carpeta / "no-existe")
        self.assertIn("Configuración", str(caja.exception))

    def test_registro_abierto_en_excel_no_impide_respaldar(self):
        """Leer se puede aunque Excel lo tenga abierto; escribirlo es lo que no (§9)."""
        ruta_xlsx = self.dir_datos / "registro" / "registro_recipes.xlsx"
        tenedor = open(ruta_xlsx, "rb")  # noqa: SIM115 - se cierra abajo
        try:
            archivo = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))
        finally:
            tenedor.close()
        with zipfile.ZipFile(archivo) as zip_:
            self.assertIn("registro/registro_recipes.xlsx", zip_.namelist())


# --------------------------------------------------------------------------
# WAL activo
# --------------------------------------------------------------------------

class TestRespaldoConWAL(CarpetaDeDatos):

    def test_el_respaldo_con_wal_activo_se_restaura_y_abre(self):
        # Conexión viva, sin checkpoint: lo recién escrito vive en el -wal.
        primero = self.emitir()
        segundo = self.emitir(nombre="María Gómez", cedula="V-777")
        self.assertEqual(
            self.con.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal"
        )
        self.assertTrue(self.ruta_db.with_name(self.ruta_db.name + "-wal").exists(),
                        "el test necesita un -wal activo para tener sentido")

        archivo = respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))

        # Restaurar = descomprimir encima de una carpeta de datos.
        restaurada = self.carpeta / "restaurada"
        with zipfile.ZipFile(archivo) as zip_:
            zip_.extractall(restaurada)

        copia = basedatos.conectar(restaurada / "datos" / "recipes.db")
        try:
            self.assertEqual(copia.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            codigos_guardados = [f["codigo"] for f in
                                 copia.execute("SELECT codigo FROM recipes ORDER BY id")]
            self.assertEqual(codigos_guardados, [primero["codigo"], segundo["codigo"]])
            self.assertEqual(
                copia.execute("SELECT COUNT(*) FROM recipe_items").fetchone()[0], 2
            )
            self.assertEqual(basedatos.version_actual(copia), basedatos.VERSION_ESQUEMA)
        finally:
            copia.close()

    def test_la_base_original_sigue_usable_despues_del_respaldo(self):
        self.emitir()
        respaldo.respaldar_ahora(self.dir_datos, date(2026, 8, 14))
        tercero = self.emitir(nombre="Pedro Ruiz", cedula="V-999")
        self.assertTrue(tercero["codigo"].endswith("-0002"))


# --------------------------------------------------------------------------
# Poda
# --------------------------------------------------------------------------

class TestConservarUltimos(CarpetaDeDatos):

    def test_borra_los_mas_viejos_y_deja_ocho(self):
        # Se crean en desorden a propósito: la antigüedad la da el nombre,
        # no la fecha de modificación del archivo.
        for dia in (5, 1, 9, 3, 10, 2, 7, 4, 8, 6):
            self.falso(f"respaldo-2026-08-{dia:02d}.zip")
        self.assertEqual(len(self.nombres_respaldos()), 10)

        borrados = respaldo.conservar_ultimos(self.dir_datos, 8)

        self.assertEqual([r.name for r in borrados],
                         ["respaldo-2026-08-01.zip", "respaldo-2026-08-02.zip"])
        quedaron = self.nombres_respaldos()
        self.assertEqual(len(quedaron), 8)
        self.assertNotIn("respaldo-2026-08-01.zip", quedaron)
        self.assertIn("respaldo-2026-08-10.zip", quedaron)

    def test_el_noveno_mas_viejo_es_el_que_cae(self):
        for dia in range(1, 10):  # nueve respaldos
            self.falso(f"respaldo-2026-08-{dia:02d}.zip")
        borrados = respaldo.conservar_ultimos(self.dir_datos, 8)
        self.assertEqual([r.name for r in borrados], ["respaldo-2026-08-01.zip"])
        self.assertEqual(len(self.nombres_respaldos()), 8)

    def test_no_toca_archivos_ajenos(self):
        ajenos = [
            "notas del medico.txt",
            "respaldo-manual.rar",
            "respaldo-2026-08-01.zip.bak",
            "Respaldo viejo 2025.zip",
            "recipes.db",
        ]
        for nombre in ajenos:
            self.falso(nombre)
        for dia in range(1, 11):
            self.falso(f"respaldo-2026-08-{dia:02d}.zip")

        respaldo.conservar_ultimos(self.dir_datos, 8)

        quedaron = self.nombres_respaldos()
        for nombre in ajenos:
            self.assertIn(nombre, quedaron, f"borró un archivo ajeno: {nombre}")

    def test_las_repeticiones_del_dia_ordenan_despues_del_original(self):
        self.falso("respaldo-2026-08-01.zip")
        self.falso("respaldo-2026-08-01-2.zip")
        self.falso("respaldo-2026-08-02.zip")
        borrados = respaldo.conservar_ultimos(self.dir_datos, 1)
        self.assertEqual([r.name for r in borrados],
                         ["respaldo-2026-08-01.zip", "respaldo-2026-08-01-2.zip"])
        self.assertEqual(self.nombres_respaldos(), ["respaldo-2026-08-02.zip"])

    def test_con_menos_de_ocho_no_borra_nada(self):
        for dia in range(1, 4):
            self.falso(f"respaldo-2026-08-{dia:02d}.zip")
        self.assertEqual(respaldo.conservar_ultimos(self.dir_datos, 8), [])
        self.assertEqual(len(self.nombres_respaldos()), 3)

    def test_nunca_toca_nada_fuera_de_la_carpeta_de_respaldos(self):
        for dia in range(1, 11):
            self.falso(f"respaldo-2026-08-{dia:02d}.zip")
        # Un archivo con nombre de respaldo, pero en `datos\`: no es asunto suyo.
        intruso = self.dir_datos / "datos" / "respaldo-2026-08-01.zip"
        intruso.write_bytes(b"x")

        respaldo.conservar_ultimos(self.dir_datos, 8)

        self.assertTrue(intruso.is_file())
        self.assertTrue(self.ruta_db.is_file())

    def test_listar_respaldos_devuelve_del_mas_viejo_al_mas_nuevo(self):
        self.falso("respaldo-2026-08-03.zip")
        self.falso("respaldo-2026-08-01.zip")
        self.falso("notas.txt")
        self.assertEqual([r.name for r in respaldo.listar_respaldos(self.dir_datos)],
                         ["respaldo-2026-08-01.zip", "respaldo-2026-08-03.zip"])


# --------------------------------------------------------------------------
# Respaldo semanal
# --------------------------------------------------------------------------

class TestRespaldoSemanal(CarpetaDeDatos):

    def test_la_primera_vez_respalda_y_deja_la_marca(self):
        resultado = respaldo.toca_respaldo_semanal(self.con, self.dir_datos,
                                                   hoy=date(2026, 8, 14))
        self.assertTrue(resultado["hecho"])
        self.assertEqual(resultado["archivo"].name, "respaldo-2026-08-14.zip")
        self.assertEqual(resultado["semana"], "2026-W33")
        self.assertTrue(resultado["archivo"].is_file())
        self.assertEqual(
            basedatos.obtener_config(self.con, respaldo.CLAVE_ULTIMO_RESPALDO),
            "2026-08-14",
        )

    def test_el_segundo_arranque_de_la_misma_semana_no_respalda(self):
        respaldo.toca_respaldo_semanal(self.con, self.dir_datos, hoy=date(2026, 8, 14))
        # Domingo de la misma semana ISO.
        resultado = respaldo.toca_respaldo_semanal(self.con, self.dir_datos,
                                                   hoy=date(2026, 8, 16))
        self.assertFalse(resultado["hecho"])
        self.assertIsNone(resultado["archivo"])
        self.assertEqual(len(respaldo.listar_respaldos(self.dir_datos)), 1)
        self.assertEqual(resultado["ultimo_respaldo"], "2026-08-14")

    def test_el_lunes_siguiente_arranca_semana_nueva_y_respalda(self):
        respaldo.toca_respaldo_semanal(self.con, self.dir_datos, hoy=date(2026, 8, 14))
        resultado = respaldo.toca_respaldo_semanal(self.con, self.dir_datos,
                                                   hoy=date(2026, 8, 17))
        self.assertTrue(resultado["hecho"])
        self.assertEqual(resultado["semana"], "2026-W34")
        self.assertEqual(len(respaldo.listar_respaldos(self.dir_datos)), 2)

    def test_la_semana_se_mide_en_iso_no_por_siete_dias(self):
        # Domingo 2026-08-16 y lunes 2026-08-17 están a un día, pero son
        # semanas ISO distintas: el lunes toca respaldo igual.
        respaldo.toca_respaldo_semanal(self.con, self.dir_datos, hoy=date(2026, 8, 16))
        resultado = respaldo.toca_respaldo_semanal(self.con, self.dir_datos,
                                                   hoy=date(2026, 8, 17))
        self.assertTrue(resultado["hecho"])

    def test_marca_ilegible_en_config_se_trata_como_sin_respaldo(self):
        basedatos.guardar_config(self.con, respaldo.CLAVE_ULTIMO_RESPALDO, "cualquier cosa")
        resultado = respaldo.toca_respaldo_semanal(self.con, self.dir_datos,
                                                   hoy=date(2026, 8, 14))
        self.assertTrue(resultado["hecho"])

    def test_marca_con_hora_iso_completa_se_entiende(self):
        basedatos.guardar_config(self.con, respaldo.CLAVE_ULTIMO_RESPALDO,
                                 "2026-08-14T09:30:00")
        resultado = respaldo.toca_respaldo_semanal(self.con, self.dir_datos,
                                                   hoy=date(2026, 8, 15))
        self.assertFalse(resultado["hecho"])

    def test_el_semanal_poda_los_viejos(self):
        for dia in range(1, 11):
            self.falso(f"respaldo-2026-07-{dia:02d}.zip")
        resultado = respaldo.toca_respaldo_semanal(self.con, self.dir_datos,
                                                   hoy=date(2026, 8, 14))
        self.assertTrue(resultado["hecho"])
        self.assertEqual(len(respaldo.listar_respaldos(self.dir_datos)), 8)
        self.assertEqual([r.name for r in resultado["eliminados"]],
                         ["respaldo-2026-07-01.zip", "respaldo-2026-07-02.zip",
                          "respaldo-2026-07-03.zip"])

    def test_si_el_respaldo_falla_la_semana_queda_pendiente(self):
        """La marca se guarda recién con el ZIP escrito: si no, se reintenta."""
        perdida = self.carpeta / "carpeta-que-el-medico-movio"
        with self.assertRaises(respaldo.RespaldoError):
            respaldo.toca_respaldo_semanal(self.con, perdida, hoy=date(2026, 8, 14))
        self.assertIsNone(basedatos.obtener_config(self.con, respaldo.CLAVE_ULTIMO_RESPALDO))


if __name__ == "__main__":
    unittest.main()
