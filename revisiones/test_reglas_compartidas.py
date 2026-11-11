from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from .consultas.preventivos import asignar_ultimos_preventivos, ultimos_preventivos
from .consultas.resumen_facturacion import resumir_items
from .dominio.cuentas import normalizar_codigo_cuenta, tipo_cliente_cuenta
from .dominio.indicadores import estado_sla
from .dominio.servicios import (
    SERVICIOS_PRINCIPALES, NOMBRES_POR_CATEGORIA, categoria_servicio, servicio_efectivo,
)
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .indicadores_odt import con_indicadores_odt
from .metricas_analisis import cargar_metricas
from .models import ODT, Revision


class ReglasDominioTests(SimpleTestCase):
    def test_efectivo_preserva_cadena_vacia_y_cero(self):
        self.assertEqual(servicio_efectivo("Original", None), "Original")
        self.assertEqual(servicio_efectivo("Original", ""), "")
        self.assertEqual(servicio_efectivo("Original", "Corregido"), "Corregido")

    def test_aliases_comparten_categoria(self):
        for categoria, nombres in NOMBRES_POR_CATEGORIA.items():
            for nombre in nombres:
                with self.subTest(nombre=nombre):
                    self.assertEqual(categoria_servicio(nombre.lower()), categoria)
        self.assertEqual(categoria_servicio("  Mantención   preventiva  "), "preventivo")
        self.assertEqual(categoria_servicio(None), "otros")
        self.assertEqual(categoria_servicio("MARCHA BLANCA"), "otros")

    def test_identidad_y_b2c_sin_catalogo_no_infiere_ceco(self):
        self.assertEqual(normalizar_codigo_cuenta(" fir - c193 - Nombre nuevo"), "FIR-C193")
        self.assertEqual(tipo_cliente_cuenta("FIR-C193 - Nombre", {}), "B2C")
        self.assertEqual(tipo_cliente_cuenta("Sin código", {}), "SIN_CLASIFICAR")
        self.assertEqual(tipo_cliente_cuenta("FIR-C193", {
            "FIR-C193": SimpleNamespace(tipo_cliente="B2B")
        }), "B2B")

    def test_sla_limites_y_fechas_no_evaluables(self):
        inicio = datetime(2026, 11, 1)
        for fin, esperado in (
            (None, "PENDIENTE"), (inicio - timedelta(seconds=1), "ERROR_FECHAS"),
            (inicio, "CUMPLE"), (inicio + timedelta(hours=48), "CUMPLE"),
            (inicio + timedelta(hours=48, seconds=1), "NO_CUMPLE"),
        ):
            with self.subTest(fin=fin):
                self.assertEqual(estado_sla(inicio, fin), esperado)
        self.assertEqual(estado_sla(None, inicio), "SIN_DATOS")


class PreventivosConsistentesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="test")
        self.fecha = timezone.make_aware(datetime(2026, 10, 1, 12))
        self.actual = ODT.objects.create(
            numero=10, cuenta_completa="FIR-100 - Nombre actual - Dirección nueva",
            servicio=SERVICIOS_PRINCIPALES[0], estado_softguard="Finalizado",
            fecha_creacion=self.fecha, fecha_finalizacion=self.fecha + timedelta(days=30),
            contratista="Contratista",
        )
        self.anterior = ODT.objects.create(
            numero=11, cuenta_completa=" fir - 100 - Nombre anterior",
            servicio="Correctiva", servicio_editado=" preventivo ",
            estado_softguard=" Finalizado ", fecha_finalizacion=self.fecha,
        )
        # Una corrección que deja de ser preventiva no acredita mantenimiento.
        ODT.objects.create(numero=12, cuenta_completa="FIR-100 - Otra dirección",
            servicio="MANTENIMIENTO PREVENTIVO", servicio_editado=SERVICIOS_PRINCIPALES[0],
            estado_softguard="Finalizado", fecha_finalizacion=self.fecha + timedelta(days=1))
        ODT.objects.create(numero=13, cuenta_completa="FIR-100", servicio="PREVENTIVO",
            estado_softguard="Pendiente", fecha_finalizacion=self.fecha + timedelta(days=2))
        ODT.objects.create(numero=14, cuenta_completa="FIR-100", servicio="PREVENTIVO",
            estado_softguard="Finalizado", fecha_finalizacion=None)
        ODT.objects.create(numero=15, cuenta_completa="FIR-200", servicio="PREVENTIVO",
            estado_softguard="Finalizado", fecha_finalizacion=self.fecha + timedelta(days=3))

    def test_nombre_direccion_corregido_alias_y_estado_normalizado(self):
        with self.assertNumQueries(1):
            resultado = ultimos_preventivos([self.actual.cuenta_completa])
        self.assertEqual(resultado, {"FIR-100": self.fecha})

    def test_lista_no_cambia_alcance_y_vacias_no_consultan(self):
        with self.assertNumQueries(0):
            self.assertEqual(asignar_ultimos_preventivos([]), [])
            self.assertEqual(ultimos_preventivos(["Cuenta sin código"]), {})
        filas = asignar_ultimos_preventivos([self.actual])
        self.assertEqual([o.numero for o in filas], [10])
        self.assertEqual(filas[0].fecha_ultimo_preventivo, self.fecha)

    def test_analisis_y_bandeja_y_preventivos_misma_fecha(self):
        from . import views
        from .mantenimientos_preventivos import mantenimientos_preventivos
        req = RequestFactory().get("/", {
            "q": "10", "estado": "", "fecha_desde": "", "fecha_hasta": "",
        })
        req.user = self.user
        with patch('revisiones.acceso_coordinadores.identificar_coordinadores_odt', side_effect=lambda numeros: {n: {} for n in numeros}), \
             patch("revisiones.vistas.bandeja.render", side_effect=lambda r, t, c: c):
            bandeja = views.bandeja(req)
        self.assertEqual([o.numero for o in bandeja["registros"]], [10])
        self.assertEqual(bandeja["registros"][0].fecha_ultimo_preventivo, self.fecha)
        analisis = cargar_metricas(ODT.objects.filter(numero=10))[0]
        self.assertEqual(analisis.fecha_ultimo_preventivo, self.fecha)
        req = RequestFactory().get("/", {"cuenta": "FIR-100"})
        req.user = self.user
        with patch("revisiones.mantenimientos_preventivos.render", side_effect=lambda r, t, c: c):
            preventivos = mantenimientos_preventivos(req)
        self.assertEqual(preventivos["cuenta_seleccionada"]["ultimo"].fecha_finalizacion, self.fecha)

    def test_presupuesto_consultas_independiente_de_cantidad_de_odt(self):
        for n in range(30):
            ODT.objects.create(numero=100+n, cuenta_completa=self.actual.cuenta_completa)
        with self.assertNumQueries(3):
            filas = cargar_metricas(ODT.objects.filter(numero__gte=100))
        self.assertEqual(len(filas), 30)
        self.assertTrue(all(o.fecha_ultimo_preventivo == self.fecha for o in filas))

    def test_sql_y_python_comparten_sla(self):
        for delta in (-1, 0, 48*3600, 48*3600+1):
            ODT.objects.filter(pk=self.actual.pk).update(
                fecha_creacion=self.fecha, fecha_finalizacion=self.fecha+timedelta(seconds=delta))
            o = con_indicadores_odt(ODT.objects.filter(pk=self.actual.pk)).get()
            self.assertEqual(o.estado_sla, estado_sla(o.fecha_creacion, o.fecha_finalizacion))


class ResumenFacturacionCompartidoTests(TestCase):
    def setUp(self):
        self.periodo = PeriodoFacturacion.objects.create(
            fecha_desde=date(2026, 9, 21), fecha_hasta=date(2026, 10, 20))
        self.factura = FacturacionContratista.objects.create(periodo=self.periodo, contratista="Prueba")
        for n, servicio, monto in (
            (1, "Mantención preventiva", "0"), (2, "PREVENTIVO", "17.50"),
            (3, "RENOVACIÓN", "12.50"), (4, SERVICIOS_PRINCIPALES[0], "20"),
            (5, "OTRO", "5"),
        ):
            odt = ODT.objects.create(numero=n, cuenta_completa=f"FIR-{n}", contratista="Prueba",
                servicio="Original distinto", servicio_editado="Corregido distinto", valor_pago_tecnico=999)
            FacturacionODT.objects.create(facturacion=self.factura, odt=odt,
                servicio_facturado=servicio, monto_facturado=Decimal(monto))

    def test_resumenes_conservan_contratos_y_valores_facturados(self):
        from .facturacion import resumen_costos_periodo as operativo
        from .historial_facturacion import resumen_costos_periodo as historico
        a, b = operativo(self.periodo), historico(self.periodo)
        self.assertEqual(a["categorias"], b["categorias"])
        self.assertEqual(a["total"], Decimal("55"))
        self.assertEqual(a["cantidad"], 5)
        self.assertEqual(b["categorias"]["preventivo"]["cantidad"], 2)
        self.assertEqual(b["categorias"]["preventivo"]["monto"], Decimal("17.50"))
        self.assertEqual(a["clientes"]["B2C"], b["clientes"]["B2C"]["monto"])

    def test_detalle_usa_la_misma_clasificacion(self):
        from .detalle_facturacion import detalle_facturacion
        req = RequestFactory().get("/")
        req.user = User.objects.create_superuser("admin", password="test")
        with patch("revisiones.detalle_facturacion.render", side_effect=lambda r,t,c:c):
            c = detalle_facturacion(req, self.factura.pk)
        self.assertEqual(c["cantidad_preventivo"], 2)
        self.assertEqual(c["monto_preventivo"], Decimal("17.50"))
        self.assertEqual(c["monto_total"], Decimal("55"))

    def test_vacio_y_ceros_sin_eliminar_categorias(self):
        with self.assertNumQueries(0):
            resumen = resumir_items([])
        self.assertEqual(resumen["cantidad"], 0)
        self.assertEqual(resumen["total"], 0)
        self.assertEqual(set(resumen["categorias"]), {
            "correctiva_con_cobro", "correctiva_sin_cobro", "renovacion", "preventivo", "acuerdo_comercial", "presupuesto", "nueva_instalacion_cruzverde", "otros"})

    def test_tarjetas_bandeja_reconocen_aliases_y_servicio_editado(self):
        from . import views
        ODT.objects.filter(numero=1).update(servicio="PREVENTIVO", servicio_editado=None)
        ODT.objects.filter(numero=2).update(servicio_editado="PREVENTIVO")
        req = RequestFactory().get("/", {"estado": "", "fecha_desde": "", "fecha_hasta": ""})
        req.user = User.objects.create_superuser("admin", password="test")
        with patch('revisiones.acceso_coordinadores.identificar_coordinadores_odt', side_effect=lambda numeros: {n: {} for n in numeros}), \
             patch("revisiones.vistas.bandeja.render", side_effect=lambda r,t,c:c):
            c = views.bandeja(req)
        # La tarjeta usa valores operativos; el resumen histórico conserva 17.50.
        self.assertEqual(c["mantenimiento_preventivo"]["cantidad"], 2)

    def test_sql_reconoce_tildes_minusculas_y_edicion_vacia(self):
        from .consultas.servicios import servicio_normalizado
        from .dominio.servicios import nombres_canonicos
        ODT.objects.filter(numero=1).update(servicio_editado=" mantención renovación ")
        ODT.objects.filter(numero=2).update(servicio="PREVENTIVO", servicio_editado="")
        filas = ODT.objects.annotate(normalizado=servicio_normalizado())
        self.assertIn(filas.get(numero=1).normalizado, nombres_canonicos("renovacion"))
        self.assertEqual(filas.get(numero=2).normalizado, "")


class ReglasPagoCompartidasTests(TestCase):
    def test_aprobacion_preserva_estados_heredados_y_excluye_rechazos(self):
        from .consultas.pagos import condicion_aprobada
        for n, estado in enumerate((None, "POR_REVISAR", "APROBADA", "EN_REVISION", "RECHAZADA"), 1):
            odt = ODT.objects.create(numero=n)
            if estado:
                Revision.objects.create(odt=odt, estado=estado)
        self.assertEqual(set(ODT.objects.filter(condicion_aprobada()).values_list("numero", flat=True)), {1, 2, 3})

    def test_monto_cero_editado_no_retorna_monto_original(self):
        from .consultas.pagos import importe_efectivo
        ODT.objects.create(numero=1, valor_pago_tecnico=100, valor_pago_editado=0)
        ODT.objects.create(numero=2, valor_pago_tecnico=100, valor_pago_editado=None)
        valores = dict(ODT.objects.annotate(efectivo=importe_efectivo()).values_list("numero", "efectivo"))
        self.assertEqual(valores, {1: Decimal("0"), 2: Decimal("100")})
