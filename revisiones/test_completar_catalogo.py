from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .cuentas_utils import cargar_catalogo_cuentas, tipo_cliente_cuenta
from .models import CatalogoCuenta, ODT


class CompletarCatalogoTests(TestCase):
    def ejecutar(self, **opciones):
        salida = StringIO()
        call_command("completar_catalogo_cuentas", stdout=salida, **opciones)
        return salida.getvalue()

    def test_nueva_cuenta_b2c_sin_inferir_ceco(self):
        ODT.objects.create(numero=1, cuenta_completa="FIR-100 - Cuenta nueva")
        self.ejecutar()
        cuenta = CatalogoCuenta.objects.get()
        self.assertEqual(cuenta.tipo_cliente, "B2C")
        self.assertEqual(cuenta.ceco, "")
        self.assertTrue(cuenta.requiere_revision_ceco)
        self.assertEqual(cuenta.nombre_cuenta, "Cuenta nueva")
        self.assertEqual(tipo_cliente_cuenta("FIR-100", cargar_catalogo_cuentas(["FIR-100"])), cuenta.tipo_cliente)

    def test_conserva_datos_manual_y_clasificacion_existente(self):
        for n, tipo in enumerate(("B2B", "B2C", "SIN_CLASIFICAR"), 1):
            CatalogoCuenta.objects.create(codigo_cuenta=f"FIR-{n}", tipo_cliente=tipo,
                ceco="50-01-01", nombre_cuenta="Nombre manual", observaciones="Validado",
                requiere_revision_ceco=False)
            ODT.objects.create(numero=n, cuenta_completa=f"FIR-{n} - Nombre origen")
        anteriores = list(CatalogoCuenta.objects.order_by("pk").values())
        self.ejecutar()
        self.assertEqual(list(CatalogoCuenta.objects.order_by("pk").values()), anteriores)

    def test_simular_no_guarda_ni_modifica_odt(self):
        odt = ODT.objects.create(numero=1, cuenta_completa="FIR-100 - Cuenta", tipo_cliente="SIN_CLASIFICAR")
        salida = self.ejecutar(simular=True)
        self.assertIn("Cuentas nuevas detectadas: 1", salida)
        self.assertFalse(CatalogoCuenta.objects.exists())
        odt.refresh_from_db()
        self.assertEqual(odt.tipo_cliente, "SIN_CLASIFICAR")

    def test_normaliza_deduplica_y_es_idempotente(self):
        for n, texto in enumerate(("fir - 100 - Cuenta", "FIR-100 - Otro nombre", "Sin cuenta"), 1):
            ODT.objects.create(numero=n, cuenta_completa=texto)
        salida = self.ejecutar()
        self.assertIn("ODT sin código reconocible: 1", salida)
        self.assertEqual(CatalogoCuenta.objects.count(), 1)
        self.assertEqual(CatalogoCuenta.objects.get().codigo_cuenta, "FIR-100")
        self.assertIn("Cuentas nuevas detectadas: 0", self.ejecutar())
        self.assertEqual(CatalogoCuenta.objects.count(), 1)

    def test_no_reescribe_proyeccion_odt_al_completar_catalogo(self):
        odt = ODT.objects.create(numero=1, cuenta_completa="FIR-100 - Cuenta", tipo_cliente="SIN_CLASIFICAR",
                                 valor_pago_editado=0, servicio_editado="Servicio manual")
        self.ejecutar()
        odt.refresh_from_db()
        self.assertEqual((odt.tipo_cliente, odt.valor_pago_editado, odt.servicio_editado),
                         ("SIN_CLASIFICAR", 0, "Servicio manual"))
        call_command("actualizar_tipo_cliente_odts", stdout=StringIO())
        odt.refresh_from_db()
        self.assertEqual(odt.tipo_cliente, "B2C")
        self.assertEqual(odt.valor_pago_editado, 0)
