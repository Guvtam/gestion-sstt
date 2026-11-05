from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from .models import Contratista, EquivalenciaSoftGuard
from .management.commands.importar_tecnicos_sstt import rut_normalizado


class ImportacionContratistasTests(TestCase):
    def ejecutar(self, datos, aplicar=False):
        salida = StringIO()
        with patch("contratistas.management.commands.importar_tecnicos_sstt.leer_archivo",
                   return_value=[(i, d) for i, d in enumerate(datos, 2)]):
            call_command("importar_tecnicos_sstt", "prueba.xlsx", aplicar=aplicar, stdout=salida)
        return salida.getvalue()

    def datos(self, **cambios):
        return {"nombre": "Proveedor prueba", "nombre_empresa": "Empresa Prueba",
                "rut": "11111111-1", "numero_cuenta": "00012345", **cambios}

    def test_simulacion_y_reimportacion_idempotente(self):
        self.ejecutar([self.datos()])
        self.assertEqual(Contratista.objects.count(), 0)
        self.ejecutar([self.datos()], True)
        self.ejecutar([self.datos()], True)
        self.assertEqual(Contratista.objects.count(), 1)
        self.assertEqual(Contratista.objects.get().numero_cuenta, "00012345")

    def test_actualiza_rut_y_conserva_nombre_equivalencias_vacios_activo(self):
        obj = Contratista.objects.create(nombre="Nombre histórico", rut="11.111.111-1", fono="123", activo=False)
        eq = EquivalenciaSoftGuard.objects.create(contratista=obj, nombre_softguard="T. EXTERNO - Prueba")
        self.ejecutar([self.datos(fono="")], True)
        obj.refresh_from_db()
        self.assertEqual(obj.rut, "11111111-1")
        self.assertEqual(obj.nombre, "Nombre histórico")
        self.assertEqual(obj.fono, "123")
        self.assertFalse(obj.activo)
        self.assertEqual(obj.equivalencias.get().pk, eq.pk)

    def test_identifica_nombre_exacto_sin_rut(self):
        obj = Contratista.objects.create(nombre="T. EXTERNO - Proveedor prueba")
        self.ejecutar([self.datos()], True)
        self.assertEqual(Contratista.objects.count(), 1)
        obj.refresh_from_db()
        self.assertEqual(obj.rut, "11111111-1")

    def test_conflicto_rut_y_nombre_no_escribe(self):
        Contratista.objects.create(nombre="Proveedor prueba", rut="22222222-2")
        with self.assertRaises(CommandError):
            self.ejecutar([self.datos(nombre="Nuevo"), self.datos()], True)
        self.assertEqual(Contratista.objects.count(), 1)

    def test_ambiguedad_no_se_resuelve_aproximadamente(self):
        Contratista.objects.create(nombre="Proveedor prueba")
        Contratista.objects.create(nombre="Proveedor prueba")
        with self.assertRaises(CommandError):
            self.ejecutar([self.datos()], True)

    def test_datos_invalidos_no_se_guardan(self):
        with self.assertRaises(CommandError):
            self.ejecutar([self.datos(correo="incorrecto")], True)
        self.assertEqual(Contratista.objects.count(), 0)

    def test_rut_normalizado_valida_dv(self):
        self.assertEqual(rut_normalizado("11.111.111-1"), "11111111-1")
        with self.assertRaises(ValueError):
            rut_normalizado("11.111.111-2")

    def test_correo_alternativo_se_guarda(self):
        self.ejecutar([self.datos(correo="principal@example.com", correo_alternativo="alternativo@example.com")], True)
        obj = Contratista.objects.get()
        self.assertEqual(obj.correo_alternativo, "alternativo@example.com")

    def test_lector_admite_encabezados_y_formatos_del_archivo(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from .management.commands.importar_tecnicos_sstt import leer_archivo
        encabezados = ("Hoja de origen", "Nombre / Nombre factura", "RUT", "Teléfono",
                       "Correo", "Ciudad", "Banco", "Tipo de cuenta", "Cuenta", "Categoría")
        datos = ("Proveedor", "Empresa", "Rut 11,111,111-1", "", "Correo: uno@example.com; dos@example.com",
                 "Ciudad", "Banco", "Vista", "00012345", "")
        wb = Mock()
        wb.worksheets = [SimpleNamespace(iter_rows=lambda **kw: iter((encabezados, datos)))]
        with patch("openpyxl.load_workbook", return_value=wb):
            registros = leer_archivo("archivo.xlsx")
        self.assertEqual(registros[0][1]["rut"], "11111111-1")
        self.assertEqual(registros[0][1]["correo"], "uno@example.com")
        self.assertEqual(registros[0][1]["correo_alternativo"], "dos@example.com")
        self.assertEqual(registros[0][1]["numero_cuenta"], "00012345")
        wb.close.assert_called_once()
