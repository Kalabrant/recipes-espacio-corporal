"""Tests de `excel.py` — el registro que se regenera desde SQLite (§9).

Cubre lo que pide el documento: contenido real de las celdas leído con
openpyxl (no "no reventó"), récipes emitidos y anulados, el archivo abierto
en Excel levantando `RegistroBloqueadoError` sin dejar el registro anterior
tocado, y la escritura atómica (ningún `.tmp` sobreviviente).

Solo `unittest` de la stdlib más openpyxl, que ya es dependencia (§3).
Se corre con:  py -3 -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import basedatos  # noqa: E402
import codigos  # noqa: E402
import excel  # noqa: E402

try:
    import msvcrt
except ImportError:  # pragma: no cover - la app corre en Windows
    msvcrt = None


ITEMS_UNO = [
    {"medicamento": "Amoxicilina", "presentacion": "500 mg",
     "cantidad": "20 tabletas", "dosis": "1 cada 8 horas",
     "indicaciones": "Con las comidas"},
    {"medicamento": "Ibuprofeno", "presentacion": "400 mg",
     "cantidad": "10 tabletas", "dosis": "1 cada 12 horas",
     "indicaciones": "Si hay dolor"},
]

ITEMS_DOS = [
    {"medicamento": "Losartán", "presentacion": "50 mg",
     "cantidad": "30 tabletas", "dosis": "1 diaria",
     "indicaciones": "En ayunas"},
]


class BaseConDatos(unittest.TestCase):
    """Carpeta de datos temporal con una base real en disco."""

    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="recipes_excel_"))
        self.dir_datos = self.carpeta / "Recipes"
        (self.dir_datos / "datos").mkdir(parents=True)
        (self.dir_datos / "registro").mkdir(parents=True)
        self.ruta_xlsx = excel.ruta_registro(self.dir_datos)
        self.con = basedatos.inicializar(self.dir_datos / "datos" / "recipes.db")

    def tearDown(self) -> None:
        self.con.close()
        shutil.rmtree(self.carpeta, ignore_errors=True)

    # -- ayudas ------------------------------------------------------------

    def emitir(self, nombre="Juan Pérez", cedula="V-12345678", edad=40,
               items=None, diagnostico="Faringitis aguda", fecha="2026-08-14") -> dict:
        paciente_id = basedatos.obtener_o_crear_paciente(
            self.con, nombre, cedula=cedula, edad=edad
        )
        return codigos.crear_recipe(
            self.con, int(paciente_id), items or ITEMS_UNO,
            fecha_emision=fecha, diagnostico=diagnostico,
        )

    def leer(self, ruta=None):
        return load_workbook(ruta or self.ruta_xlsx)

    def temporales(self) -> list[Path]:
        return [r for r in self.ruta_xlsx.parent.iterdir() if r.suffix == ".tmp"]


# --------------------------------------------------------------------------
# Estructura del libro
# --------------------------------------------------------------------------

class TestEstructura(BaseConDatos):

    def test_base_vacia_deja_las_dos_hojas_con_encabezados(self):
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        self.assertEqual(libro.sheetnames, [excel.HOJA_RECIPES, excel.HOJA_MEDICAMENTOS])

        hoja = libro[excel.HOJA_RECIPES]
        self.assertEqual(hoja.max_row, 1)
        self.assertEqual(
            [c.value for c in hoja[1]],
            [nombre for nombre, _ in excel.COLUMNAS_RECIPES],
        )
        hoja_m = libro[excel.HOJA_MEDICAMENTOS]
        self.assertEqual(hoja_m.max_row, 1)
        self.assertEqual(
            [c.value for c in hoja_m[1]],
            [nombre for nombre, _ in excel.COLUMNAS_MEDICAMENTOS],
        )
        libro.close()

    def test_encabezados_en_negrita_anchos_y_filtro(self):
        self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()

        for hoja, columnas in ((libro[excel.HOJA_RECIPES], excel.COLUMNAS_RECIPES),
                               (libro[excel.HOJA_MEDICAMENTOS], excel.COLUMNAS_MEDICAMENTOS)):
            for celda in hoja[1]:
                self.assertTrue(celda.font.bold, f"encabezado sin negrita: {celda.value}")
            self.assertIsNotNone(hoja.auto_filter.ref, "falta el filtro automático")
            self.assertTrue(hoja.auto_filter.ref.startswith("A1:"), hoja.auto_filter.ref)
            self.assertEqual(hoja.freeze_panes, "A2")
            for indice, (_, ancho) in enumerate(columnas, start=1):
                from openpyxl.utils import get_column_letter
                letra = get_column_letter(indice)
                self.assertEqual(hoja.column_dimensions[letra].width, ancho)
        libro.close()

    def test_el_filtro_cubre_todas_las_filas_escritas(self):
        self.emitir()
        self.emitir(nombre="María Gómez", cedula="V-777", edad=31, items=ITEMS_DOS)
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        # 2 récipes + encabezado; 3 renglones de medicamentos + encabezado.
        self.assertEqual(libro[excel.HOJA_RECIPES].auto_filter.ref, "A1:J3")
        self.assertEqual(libro[excel.HOJA_MEDICAMENTOS].auto_filter.ref, "A1:H4")
        libro.close()


# --------------------------------------------------------------------------
# Contenido
# --------------------------------------------------------------------------

class TestContenido(BaseConDatos):

    def test_hoja_recipes_celda_por_celda(self):
        recipe = self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        hoja = libro[excel.HOJA_RECIPES]
        self.assertEqual(hoja.max_row, 2)

        fila = [c.value for c in hoja[2]]
        self.assertEqual(fila[0], recipe["codigo"])
        self.assertEqual(fila[1], "2026-08-14")
        self.assertEqual(fila[2], "Juan Pérez")
        self.assertEqual(fila[3], "V-12345678")
        self.assertEqual(fila[4], 40)
        self.assertEqual(fila[5], "Faringitis aguda")
        self.assertEqual(fila[6], 2)                      # cantidad de renglones
        self.assertEqual(fila[7], excel.ESTADO_EMITIDO)
        self.assertIn(fila[8], (None, ""))                # sin motivo: no está anulado
        self.assertIn(fila[9], (None, ""))                # todavía sin PDF guardado
        libro.close()

    def test_ruta_del_pdf_va_al_registro(self):
        recipe = self.emitir()
        ruta_pdf = str(self.dir_datos / "pdf" / "2026" / f"{recipe['codigo']}_PEREZ-Juan_2026-08-14.pdf")
        basedatos.guardar_ruta_pdf(self.con, int(recipe["id"]), ruta_pdf)
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        self.assertEqual(libro[excel.HOJA_RECIPES]["J2"].value, ruta_pdf)
        libro.close()

    def test_hoja_medicamentos_una_fila_por_renglon(self):
        recipe = self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        hoja = libro[excel.HOJA_MEDICAMENTOS]
        self.assertEqual(hoja.max_row, 3)  # encabezado + 2 renglones

        primera = [c.value for c in hoja[2]]
        self.assertEqual(primera, [
            recipe["codigo"], "2026-08-14", "Juan Pérez",
            "Amoxicilina", "500 mg", "20 tabletas", "1 cada 8 horas", "Con las comidas",
        ])
        segunda = [c.value for c in hoja[3]]
        self.assertEqual(segunda[3], "Ibuprofeno")
        self.assertEqual(segunda[6], "1 cada 12 horas")
        libro.close()

    def test_orden_por_fecha_descendente(self):
        viejo = self.emitir(fecha="2026-01-05")
        nuevo = self.emitir(nombre="María Gómez", cedula="V-777", edad=31,
                            items=ITEMS_DOS, fecha="2026-08-14")
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        hoja = libro[excel.HOJA_RECIPES]
        self.assertEqual(hoja["A2"].value, nuevo["codigo"])
        self.assertEqual(hoja["A3"].value, viejo["codigo"])
        libro.close()

    def test_anulado_queda_en_gris_tachado_con_motivo(self):
        emitido = self.emitir()
        anulado = self.emitir(nombre="María Gómez", cedula="V-777", edad=31,
                              items=ITEMS_DOS, fecha="2026-08-13")
        basedatos.anular_recipe(self.con, int(anulado["id"]), "Error en la dosis")
        excel.regenerar_registro(self.con, self.ruta_xlsx)

        libro = self.leer()
        hoja = libro[excel.HOJA_RECIPES]
        # Orden por fecha DESC: primero el emitido (14), después el anulado (13).
        self.assertEqual(hoja["A2"].value, emitido["codigo"])
        self.assertEqual(hoja["H2"].value, excel.ESTADO_EMITIDO)
        self.assertFalse(hoja["A2"].font.strike)

        self.assertEqual(hoja["A3"].value, anulado["codigo"])
        self.assertEqual(hoja["H3"].value, excel.ESTADO_ANULADO)
        self.assertEqual(hoja["I3"].value, "Error en la dosis")
        for celda in hoja[3]:
            self.assertTrue(celda.font.strike, f"celda sin tachar: {celda.coordinate}")
            self.assertEqual(celda.font.color.rgb, "FF808080")

        # La hoja de medicamentos también refleja la anulación.
        hoja_m = libro[excel.HOJA_MEDICAMENTOS]
        fila_anulada = [f for f in hoja_m.iter_rows(min_row=2)
                        if f[0].value == anulado["codigo"]]
        self.assertEqual(len(fila_anulada), 1)
        for celda in fila_anulada[0]:
            self.assertTrue(celda.font.strike)
        libro.close()

    def test_anular_despues_de_regenerar_actualiza_el_registro(self):
        recipe = self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        self.assertEqual(libro[excel.HOJA_RECIPES]["H2"].value, excel.ESTADO_EMITIDO)
        libro.close()

        basedatos.anular_recipe(self.con, int(recipe["id"]), "Paciente equivocado")
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        hoja = libro[excel.HOJA_RECIPES]
        self.assertEqual(hoja["H2"].value, excel.ESTADO_ANULADO)
        self.assertEqual(hoja["I2"].value, "Paciente equivocado")
        # El récipe sigue estando: se anula, no se borra (§2.4).
        self.assertEqual(hoja["A2"].value, recipe["codigo"])
        self.assertEqual(hoja.max_row, 2)
        libro.close()

    def test_se_reconstruye_completo_pisando_lo_que_hubiera(self):
        """El Excel es salida, nunca fuente (§13): lo que haya adentro se pierde."""
        libro_falso = Workbook()
        libro_falso.active.title = "Basura"
        libro_falso.active["A1"] = "esto no debería sobrevivir"
        self.ruta_xlsx.parent.mkdir(parents=True, exist_ok=True)
        libro_falso.save(self.ruta_xlsx)
        libro_falso.close()

        self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)

        libro = self.leer()
        self.assertEqual(libro.sheetnames, [excel.HOJA_RECIPES, excel.HOJA_MEDICAMENTOS])
        libro.close()

    def test_cedula_vacia_y_sin_diagnostico_no_rompen(self):
        paciente_id = basedatos.crear_paciente(self.con, "Sin Cédula", cedula="", edad=None)
        codigos.crear_recipe(self.con, int(paciente_id), ITEMS_DOS,
                             fecha_emision="2026-08-14")
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        hoja = libro[excel.HOJA_RECIPES]
        self.assertEqual(hoja["C2"].value, "Sin Cédula")
        self.assertIn(hoja["D2"].value, (None, ""))
        self.assertIn(hoja["E2"].value, (None, ""))
        self.assertIn(hoja["F2"].value, (None, ""))
        self.assertEqual(hoja["H2"].value, excel.ESTADO_EMITIDO)
        libro.close()


# --------------------------------------------------------------------------
# Escritura atómica y archivo bloqueado
# --------------------------------------------------------------------------

class TestEscritura(BaseConDatos):

    def test_no_queda_ningun_temporal(self):
        self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        self.assertEqual(self.temporales(), [])
        self.assertTrue(self.ruta_xlsx.is_file())

    def test_crea_la_carpeta_registro_si_no_esta(self):
        shutil.rmtree(self.ruta_xlsx.parent)
        self.emitir()
        devuelta = excel.regenerar_registro(self.con, self.ruta_xlsx)
        self.assertEqual(devuelta, self.ruta_xlsx)
        self.assertTrue(self.ruta_xlsx.is_file())

    def test_ruta_registro_arma_la_ruta_de_la_seccion_4(self):
        self.assertEqual(
            excel.ruta_registro(self.dir_datos),
            self.dir_datos / "registro" / "registro_recipes.xlsx",
        )

    def test_regenerar_en_usa_la_carpeta_de_datos(self):
        self.emitir()
        devuelta = excel.regenerar_en(self.con, self.dir_datos)
        self.assertEqual(devuelta, self.ruta_xlsx)
        self.assertTrue(self.ruta_xlsx.is_file())

    def _archivo_intacto(self, contenido: bytes, codigo_esperado: str) -> None:
        self.assertEqual(self.ruta_xlsx.read_bytes(), contenido)
        libro = self.leer()
        self.assertEqual(libro[excel.HOJA_RECIPES]["A2"].value, codigo_esperado)
        libro.close()

    def test_abierto_en_excel_levanta_registro_bloqueado(self):
        """Simula el handle que deja Excel: el renombrado final no puede pisar."""
        primero = self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        antes = self.ruta_xlsx.read_bytes()

        self.emitir(nombre="María Gómez", cedula="V-777", edad=31, items=ITEMS_DOS)

        tenedor = open(self.ruta_xlsx, "rb")  # noqa: SIM115 - se cierra abajo
        try:
            with self.assertRaises(excel.RegistroBloqueadoError) as caja:
                excel.regenerar_registro(self.con, self.ruta_xlsx)
        finally:
            tenedor.close()

        self.assertEqual(str(caja.exception), excel.MENSAJE_BLOQUEADO)
        self.assertEqual(caja.exception.ruta, self.ruta_xlsx)
        # El registro anterior quedó entero y sin temporales alrededor.
        self._archivo_intacto(antes, primero["codigo"])
        self.assertEqual(self.temporales(), [])

    @unittest.skipIf(msvcrt is None, "el bloqueo por rango de bytes es de Windows")
    def test_bloqueo_por_rango_de_bytes_tambien_se_detecta(self):
        primero = self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)
        antes = self.ruta_xlsx.read_bytes()

        descriptor = os.open(self.ruta_xlsx, os.O_RDWR | os.O_BINARY)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        try:
            with self.assertRaises(excel.RegistroBloqueadoError):
                excel.regenerar_registro(self.con, self.ruta_xlsx)
        finally:
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            os.close(descriptor)

        self._archivo_intacto(antes, primero["codigo"])
        self.assertEqual(self.temporales(), [])

    def test_despues_de_cerrar_excel_el_siguiente_intento_funciona(self):
        """El récipe se guardó igual; el registro se pone al día al próximo (§9)."""
        self.emitir()
        excel.regenerar_registro(self.con, self.ruta_xlsx)

        segundo = self.emitir(nombre="María Gómez", cedula="V-777", edad=31,
                              items=ITEMS_DOS, fecha="2026-08-15")
        tenedor = open(self.ruta_xlsx, "rb")  # noqa: SIM115
        try:
            with self.assertRaises(excel.RegistroBloqueadoError):
                excel.regenerar_registro(self.con, self.ruta_xlsx)
        finally:
            tenedor.close()

        excel.regenerar_registro(self.con, self.ruta_xlsx)
        libro = self.leer()
        hoja = libro[excel.HOJA_RECIPES]
        self.assertEqual(hoja.max_row, 3)
        self.assertEqual(hoja["A2"].value, segundo["codigo"])
        libro.close()
        self.assertEqual(self.temporales(), [])

    def test_el_error_es_un_oserror(self):
        """Quien llama puede atraparlo como OSError sin conocer el módulo."""
        self.assertTrue(issubclass(excel.RegistroBloqueadoError, OSError))


if __name__ == "__main__":
    unittest.main()
