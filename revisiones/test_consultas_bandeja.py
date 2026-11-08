from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase, RequestFactory
from django.utils import timezone
from .dominio.filtros_bandeja import leer_seleccion, SIN_TECNICO_FILTRO
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .consultas.filtros_bandeja import filtrar_tabla
from .consultas.indicadores_bandeja import indicadores_financieros, indicadores_operativos
from .models import ODT, ResponsableSoftGuard
from .vistas.bandeja import bandeja


class SeleccionBandejaTests(SimpleTestCase):
    def test_periodo_predeterminado_cruza_anio(self):
        seleccion=leer_seleccion(QueryDict(),por_creacion=False,hoy=date(2027,1,1))
        self.assertEqual(seleccion.filtros()["fecha_desde"],"2026-12-21")
        self.assertEqual(seleccion.filtros()["fecha_hasta"],"2027-01-01")
        self.assertEqual(seleccion.filtros()["estado"],"Finalizado")
        self.assertEqual(seleccion.servicios,tuple(SERVICIOS_PRINCIPALES))
        self.assertFalse(seleccion.contratistas_explicitos)

    def test_creacion_no_impone_estado_ni_servicios(self):
        seleccion=leer_seleccion(QueryDict(),por_creacion=True,hoy=date(2026,11,8))
        self.assertEqual(seleccion.filtros()["estado"],"")
        self.assertEqual(seleccion.servicios,())

    def test_valores_vacios_no_se_sustituyen_por_predeterminados(self):
        datos=QueryDict("estado=&fecha_desde=&fecha_hasta=&contratistas_filtrados=1")
        seleccion=leer_seleccion(datos,por_creacion=False,hoy=date(2026,11,8))
        self.assertEqual(seleccion.contratistas,())
        self.assertTrue(seleccion.contratistas_explicitos)
        self.assertEqual(seleccion.filtros()["fecha_desde"],"")
        self.assertEqual(seleccion.filtros()["estado"],"")
        self.assertEqual(seleccion.servicios,())

    def test_listas_y_numero_exacto_conservan_valores(self):
        seleccion=leer_seleccion(QueryDict("servicios=A&servicios=B&contratista=X&numero_odt=0007"),
                                por_creacion=False,hoy=date(2026,11,8))
        self.assertEqual(seleccion.servicios,("A","B"))
        self.assertEqual(seleccion.numero_exacto,"0007")
        self.assertEqual(seleccion.contratistas,("X",))


class ConsultasBandejaTests(TestCase):
    def setUp(self):
        self.fecha=timezone.make_aware(datetime(2026,11,5,12))
        self.odt=ODT.objects.create(numero=1,contratista="Prueba",cuenta_completa="FIR-1",
            estado_softguard="Finalizado",fecha_finalizacion=self.fecha,fecha_creacion=self.fecha,
            servicio=SERVICIOS_PRINCIPALES[0],valor_pago_tecnico=100,valor_pago_editado=0)
        ODT.objects.create(numero=2,contratista="Prueba",cuenta_completa="FIR-2",
            estado_softguard="Finalizado",fecha_finalizacion=self.fecha,fecha_creacion=self.fecha,
            servicio=SERVICIOS_PRINCIPALES[1],valor_pago_tecnico=50)
        self.filtros=dict(estado="Finalizado",revision="",q="",fecha_desde="2026-10-21",fecha_hasta="2026-11-06")

    def filtrar(self,**opciones):
        parametros=dict(filtros=self.filtros,servicios_seleccionados=[],
                        contratistas_seleccionados=["Prueba"],campo_fecha="fecha_finalizacion",
                        por_creacion=False,numero_exacto=None,avisar_fecha=lambda valor:None)
        parametros.update(opciones)
        return filtrar_tabla(ODT.objects.all(),**parametros)

    def test_fechas_invalidas_avisan_sin_eliminar_filas(self):
        avisos=[]
        resultado=self.filtrar(filtros={**self.filtros,"fecha_desde":"incorrecta"},avisar_fecha=avisos.append)
        self.assertEqual(resultado.count(),2)
        self.assertEqual(avisos,["incorrecta"])

    def test_seleccion_vacia_no_amplia_resultados(self):
        self.assertFalse(self.filtrar(contratistas_seleccionados=[]).exists())

    def test_servicio_corregido_prevalece_y_cero_se_conserva(self):
        ODT.objects.filter(pk=self.odt.pk).update(servicio_editado=SERVICIOS_PRINCIPALES[1])
        resultado=self.filtrar(servicios_seleccionados=[SERVICIOS_PRINCIPALES[0]])
        self.assertFalse(resultado.exists())
        resultado=self.filtrar(servicios_seleccionados=[SERVICIOS_PRINCIPALES[1]])
        with self.assertNumQueries(1):
            indicadores=indicadores_financieros(resultado)
        self.assertEqual(indicadores["total"],{"cantidad":2,"monto":Decimal("150")})
        self.assertEqual(indicadores["aprobadas"]["monto"],Decimal("50"))
        with self.assertNumQueries(1):
            operativos=indicadores_operativos(resultado)
        self.assertEqual(operativos["kpi_odt_modificadas"],1)

    def test_numero_exacto_invalido_no_se_convierte_en_busqueda_amplia(self):
        for numero in ("", "١", "000000000001"):
            with self.subTest(numero=numero):
                self.assertFalse(self.filtrar(numero_exacto=numero).exists())
        self.assertEqual(list(self.filtrar(numero_exacto="0001").values_list("numero",flat=True)),[1])

    def test_sin_tecnico_solo_se_admite_en_creacion(self):
        ODT.objects.filter(numero=2).update(contratista="")
        self.assertFalse(self.filtrar(contratistas_seleccionados=[SIN_TECNICO_FILTRO]).exists())
        self.assertEqual(list(self.filtrar(contratistas_seleccionados=[SIN_TECNICO_FILTRO],
            por_creacion=True,campo_fecha="fecha_creacion").values_list("numero",flat=True)),[2])

    def test_indicadores_vacios_conservan_cantidades_y_montos_cero(self):
        resultado=indicadores_financieros(ODT.objects.none())
        self.assertTrue(all(v=={"cantidad":0,"monto":Decimal("0")} for v in resultado.values()))

    def test_catalogo_nuevo_se_puede_seleccionar_sin_cambiar_codigo(self):
        ResponsableSoftGuard.objects.create(id_softguard=9000,nombre="Nuevo responsable",
                                            usuario_softguard="nuevo_responsable")
        usuario=User.objects.create_superuser("admin",password="prueba")
        request=RequestFactory().get("/",{"coordinador":"nuevo_responsable",
                                          "fecha_desde":"2026-10-21","fecha_hasta":"2026-11-06"})
        request.user=usuario
        datos={1:{"nombre":"Nuevo responsable","usuario":"nuevo_responsable","identificado":True},
               2:{"nombre":"Otro","usuario":"jtapia","identificado":True}}
        with patch("revisiones.vistas.bandeja.coordinadores_en_peticion",return_value=datos), \
             patch("revisiones.vistas.bandeja.coordinadores_para_mostrar",return_value=datos), \
             patch("revisiones.vistas.bandeja.render",side_effect=lambda r,t,c:c):
            contexto=bandeja(request)
        self.assertEqual([o.numero for o in contexto["registros"]],[1])
        self.assertIn({"usuario":"nuevo_responsable","nombre":"Nuevo responsable"},contexto["coordinadores_asignables"])
        from django.template.loader import render_to_string
        html=render_to_string("revisiones/bandeja.html",contexto,request=request)
        selector=html.split('<select name="coordinador">',1)[1].split("</select>",1)[0]
        self.assertIn('value="nuevo_responsable"',selector)
