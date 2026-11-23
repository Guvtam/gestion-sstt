from decimal import Decimal
from django.test import TestCase
from .models import ODT, Revision
from .consultas.resumen_bandeja import resumen_bandeja

class ResumenBandejaTests(TestCase):
    def crear(self,n,**datos):
        return ODT.objects.create(numero=n,servicio=datos.pop("servicio","MANTENCION CORRECTIVA CON COBRO"),
            valor_pago_tecnico=datos.pop("valor_pago_tecnico",100),**datos)

    def test_cuentas_destacadas_son_detalle_sin_doble_conteo(self):
        self.crear(1,cuenta_completa="FIR-1 - CRUZ VERDE LOCAL",tipo_cliente="B2B")
        self.crear(2,cuenta_completa="FIR-2 - ENEL",tipo_cliente="B2B")
        self.crear(3,cuenta_completa="FIR-3 - TATTERSALL",tipo_cliente="B2C")
        self.crear(4,cuenta_completa="FIR-4 - CLIENTE GENERAL",tipo_cliente="B2C")
        r=resumen_bandeja(ODT.objects.all())
        self.assertEqual(r["total"]["cantidad"],4)
        self.assertEqual(sum(x["cantidad"] for x in r["tipos"]),4)
        self.assertEqual(sum(x["monto"] for x in r["tipos"]),400)
        self.assertEqual(sum(x["cantidad"] for x in r["marcas"]),3)

    def test_ajustes_cero_y_dos_servicios_editados_y_rechazados(self):
        a=self.crear(1,valor_pago_tecnico=230000,valor_pago_editado=2,
            servicio_editado="MANTENIMIENTO RENOVACIÓN",tipo_cliente="B2B")
        b=self.crear(2,valor_pago_editado=0,tipo_cliente="B2C")
        c=self.crear(3,servicio="MANTENIMIENTO PREVENTIVO",tipo_cliente="B2C")
        Revision.objects.create(odt=c,estado="RECHAZADA")
        r=resumen_bandeja(ODT.objects.all());s={x["nombre"]:x for x in r["servicios"]}
        self.assertEqual(r["total"]["monto"],102)
        self.assertEqual(s["Renovaciones"]["monto"],2)
        self.assertEqual(s["Correctiva con cobro"]["monto"],0)
        self.assertEqual(s["Preventivos"]["monto"],100)
        self.assertEqual(r["mantenimiento"]["monto"],2)
        self.assertEqual(r["mantenimiento"]["cantidad"],2)

    def test_instalacion_b2c_no_incluye_cruzverde_b2b_ni_en_revision(self):
        for n,tipo,servicio,estado in (
            (1,"B2C","MANTENIMIENTO NUEVA INSTALACIÓN",None),
            (2,"B2B","MANTENIMIENTO NUEVA INSTALACION",None),
            (3,"B2C","MANTENIMIENTO NUEVA INSTALACION CRUZVERDE",None),
            (4,"B2C","MANTENIMIENTO NUEVA INSTALACION","EN_REVISION")):
            o=self.crear(n,tipo_cliente=tipo,servicio=servicio)
            if estado:Revision.objects.create(odt=o,estado=estado)
        r=resumen_bandeja(ODT.objects.all())
        self.assertEqual(r["instalaciones"]["monto"],100)
        self.assertEqual(r["otros_aprobados"]["monto"],200)
        self.assertEqual(r["mantenimiento"]["monto"],0)

    def test_sin_clasificar_y_servicios_desconocidos_se_conservan(self):
        self.crear(1,tipo_cliente="SIN_CLASIFICAR",servicio="SERVICIO DESCONOCIDO")
        r=resumen_bandeja(ODT.objects.all())
        self.assertEqual(r["tipos"][-1]["cantidad"],1)
        self.assertEqual(r["servicios"][-1]["monto"],100)
        self.assertEqual(r["otros_aprobados"]["monto"],100)

    def test_respeta_queryset_filtrado_y_vacio(self):
        self.crear(1);self.crear(2)
        r=resumen_bandeja(ODT.objects.filter(numero=1))
        self.assertEqual(r["total"]["cantidad"],1)
        self.assertEqual(r["total"]["monto"],100)
        r=resumen_bandeja(ODT.objects.none())
        self.assertEqual(r["total"]["monto"],0)
        self.assertEqual(r["total"]["cantidad"],0)
