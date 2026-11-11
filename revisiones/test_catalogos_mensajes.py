from datetime import datetime
from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, RequestFactory
from django.utils import timezone
from .consultas.catalogos_bandeja import servicios_disponibles, estados_disponibles, filtrar_opciones_ajax
from .models import ODT
from .dominio.servicios import SERVICIOS_PRINCIPALES


class CatalogosBandejaTests(TestCase):
    def setUp(self):
        self.fecha=timezone.make_aware(datetime(2026,11,5,12))
        ODT.objects.create(numero=1,contratista="Uno",servicio="Original",servicio_editado="Corregido",
                           estado_softguard="Finalizado",fecha_creacion=self.fecha,fecha_finalizacion=self.fecha)
        ODT.objects.create(numero=2,contratista="Dos",servicio="Original",
                           estado_softguard="Asignado",fecha_creacion=self.fecha)
        ODT.objects.create(numero=3,servicio="",estado_softguard="")

    def test_union_ordenada_sin_vacios_ni_duplicados_en_dos_consultas(self):
        with self.assertNumQueries(2):
            self.assertEqual(servicios_disponibles(),sorted(set(SERVICIOS_PRINCIPALES) | {"Corregido","Original"}))

    def test_estados_conservan_orden_y_consulta_diferida(self):
        with self.assertNumQueries(0):
            estados=estados_disponibles()
        with self.assertNumQueries(1):
            self.assertEqual(list(estados),["Asignado","Finalizado"])

    def test_opciones_usan_servicio_efectivo_y_fecha_seleccionada(self):
        base=ODT.objects.all()
        self.assertEqual(list(filtrar_opciones_ajax(base,campo_fecha="fecha_finalizacion",
            fecha_desde="2026-11-01",fecha_hasta="2026-11-30",servicios=["Corregido"])
            .values_list("numero",flat=True)),[1])
        self.assertEqual(list(filtrar_opciones_ajax(base,campo_fecha="fecha_creacion",
            fecha_desde="2026-11-01",servicios=["Original"]).values_list("numero",flat=True)),[2])

    def test_helper_no_amplia_queryset_recibido(self):
        self.assertFalse(filtrar_opciones_ajax(ODT.objects.filter(numero=2),
            campo_fecha="fecha_creacion",servicios=["Corregido"]).exists())


class MensajesCompartidosTests(SimpleTestCase):
    def almacenamiento(self):
        request=RequestFactory().get("/")
        request.session={}
        request._messages=FallbackStorage(request)
        messages.success(request,"Guardado")
        messages.error(request,"<script>no ejecutar</script>",extra_tags="urgente")
        return request._messages

    def test_estandar_conserva_clases_escapa_texto_y_distingue_roles(self):
        html=render_to_string("revisiones/componentes/mensajes.html",
                              {"messages":self.almacenamiento(),"estilo":"estandar"})
        self.assertIn('class="message error" role="alert"',html)
        self.assertIn('role="status"',html)
        self.assertIn("&lt;script&gt;",html)
        self.assertNotIn("<script>",html)
        self.assertEqual(html.count("Guardado"),1)
        self.assertEqual(html.count("no ejecutar"),1)

    def test_variante_historial_conserva_parrafos(self):
        html=render_to_string("revisiones/componentes/mensajes.html",
                              {"messages":self.almacenamiento(),"estilo":"historial"})
        self.assertEqual(html.count("<p "),2)
        self.assertNotIn("<div",html)
        self.assertIn('role="alert"',html)
        self.assertIn('role="status"',html)

    def test_sin_mensajes_no_genera_elementos(self):
        html=render_to_string("revisiones/componentes/mensajes.html",{"messages":[]})
        self.assertEqual(html.strip(),"")
