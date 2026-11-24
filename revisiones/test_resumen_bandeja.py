from decimal import Decimal
from django.test import TestCase
from .models import ODT, Revision
from .consultas.resumen_bandeja import resumen_bandeja

class ResumenBandejaTests(TestCase):
    def crear(self,n,**datos):
        return ODT.objects.create(numero=n,servicio=datos.pop("servicio","MANTENCION CORRECTIVA CON COBRO"),
            valor_pago_tecnico=datos.pop("valor_pago_tecnico",100),**datos)

    def test_cuentas_destacadas_se_excluyen_de_b2b_b2c_sin_doble_conteo(self):
        self.crear(1,cuenta_completa="FIR-1 - CRUZ VERDE LOCAL",tipo_cliente="B2B")
        self.crear(2,cuenta_completa="FIR-2 - ENEL",tipo_cliente="B2B")
        self.crear(3,cuenta_completa="FIR-3 - TATTERSALL",tipo_cliente="B2C")
        self.crear(4,cuenta_completa="FIR-4 - CLIENTE GENERAL",tipo_cliente="B2C")
        r=resumen_bandeja(ODT.objects.all())
        self.assertEqual(r["total"]["cantidad"],4)
        self.assertEqual(sum(x["cantidad"] for x in r["tipos"]),2)
        self.assertEqual(sum(x["monto"] for x in r["tipos"]),200)
        self.assertEqual(sum(x["cantidad"] for x in r["marcas"]),2)
        self.assertEqual([x["nombre"] for x in r["marcas"]],["Cruz Verde","Tattersall"])
        self.assertEqual(r["tipos"][0]["monto"],100)

    def test_ajustes_cero_y_dos_servicios_editados_y_rechazados(self):
        a=self.crear(1,valor_pago_tecnico=230000,valor_pago_editado=2,
            servicio_editado="MANTENIMIENTO RENOVACIÓN",tipo_cliente="B2B")
        b=self.crear(2,valor_pago_editado=0,tipo_cliente="B2C")
        c=self.crear(3,servicio="MANTENIMIENTO PREVENTIVO",tipo_cliente="B2C")
        Revision.objects.create(odt=c,estado="RECHAZADA")
        r=resumen_bandeja(ODT.objects.all());s={x["nombre"]:x for x in r["servicios"]}
        self.assertEqual(r["total"]["monto"],2)
        self.assertEqual(s["Renovaciones"]["monto"],2)
        self.assertEqual(s["Correctiva con cobro"]["monto"],0)
        self.assertEqual(s["Preventivos"]["monto"],0)
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

    def test_matriz_por_cuenta_y_servicio_concilia_sin_duplicar_marcas(self):
        self.crear(1,tipo_cliente="B2B",cuenta_completa="FIR-1 CRUZ VERDE",
            valor_pago_tecnico=230000,valor_pago_editado=2,servicio_editado="MANTENIMIENTO RENOVACIÓN")
        self.crear(2,tipo_cliente="B2C",cuenta_completa="FIR-2 TATTERSALL",servicio="MANTENIMIENTO PREVENTIVO")
        self.crear(3,tipo_cliente="B2B",cuenta_completa="FIR-3 GENERAL",valor_pago_editado=0)
        r=resumen_bandeja(ODT.objects.all())
        for fila in [*r["filas_tipos"],*r["marcas"]]:
            self.assertEqual(sum(c["monto"] for c in fila["celdas"]),fila["monto"])
            self.assertEqual(sum(c["cantidad"] for c in fila["celdas"]),fila["cantidad"])
        self.assertEqual(r["total"]["monto"],102)
        self.assertEqual(r["marcas"][0]["desglose"]["renovacion"]["monto"],2)
        self.assertEqual(r["marcas"][0]["desglose"]["correctiva_con_cobro"]["cantidad"],0)
        self.assertEqual(sum(f["monto"] for f in r["filas_tipos"]+r["marcas"]),102)
        from django.template.loader import render_to_string
        html=render_to_string("revisiones/componentes/resumen_bandeja.html",{"resumen_visual":r})
        self.assertIn('class="ejecutivo-matriz"',html)
        self.assertIn('Nueva instalación Cruzverde',html)
        self.assertNotIn('ejecutivo-barra',html)
        self.assertNotIn('Mantenimiento aprobado',html)
        self.assertNotIn('Instalaciones B2C aprobadas',html)
        self.assertNotIn('Enel',html)

    def test_totales_por_columna_y_filas_sin_rechazadas(self):
        self.crear(1,cuenta_completa="FIR-1 CRUZ VERDE",tipo_cliente="B2B",valor_pago_tecnico=100)
        self.crear(2,cuenta_completa="FIR-2 TATTERSALL",tipo_cliente="B2C",valor_pago_tecnico=200,servicio="MANTENIMIENTO PREVENTIVO")
        self.crear(3,cuenta_completa="FIR-3 GENERAL",tipo_cliente="B2B",valor_pago_tecnico=300)
        self.crear(4,cuenta_completa="FIR-4 GENERAL",tipo_cliente="B2C",valor_pago_editado=2)
        rechazado=self.crear(5,cuenta_completa="FIR-5 CRUZ VERDE",tipo_cliente="B2B",valor_pago_tecnico=3946000)
        Revision.objects.create(odt=rechazado,estado="RECHAZADA")
        r=resumen_bandeja(ODT.objects.all());filas=r["filas_tipos"]+r["marcas"]
        self.assertEqual((r["total"]["cantidad"],r["total"]["monto"]),(4,602))
        self.assertEqual(sum(f["monto"] for f in filas),602)
        for i,celda in enumerate(r["total"]["celdas"]):
            self.assertEqual(sum(f["celdas"][i]["monto"] for f in filas),celda["monto"])
            self.assertEqual(sum(f["celdas"][i]["cantidad"] for f in filas),celda["cantidad"])
        self.assertEqual(ODT.objects.get(numero=1).tipo_cliente,"B2B")
        self.assertEqual(ODT.objects.get(numero=2).tipo_cliente,"B2C")
        from django.template.loader import render_to_string
        html=render_to_string("revisiones/componentes/resumen_bandeja.html",{"resumen_visual":r})
        self.assertIn('<tfoot>',html)
        self.assertIn('Total sin rechazados',html)
        self.assertNotIn('ya están incluidos',html)

    def test_solo_rechazados_da_resumen_vacio_y_no_excluye_en_revision(self):
        rechazado=self.crear(1);Revision.objects.create(odt=rechazado,estado="RECHAZADA")
        r=resumen_bandeja(ODT.objects.all())
        self.assertEqual(r["total"]["cantidad"],0)
        self.assertEqual(r["total"]["monto"],0)
        revision=self.crear(2);Revision.objects.create(odt=revision,estado="EN_REVISION")
        observado=self.crear(3);Revision.objects.create(odt=observado,estado="OBSERVADA")
        r=resumen_bandeja(ODT.objects.all())
        self.assertEqual(r["total"]["cantidad"],2)
        self.assertEqual(r["total"]["monto"],200)
