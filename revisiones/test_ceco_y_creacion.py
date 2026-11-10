from unittest.mock import patch

from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .dominio.servicios import SERVICIOS_PRINCIPALES
from .models import CatalogoCuenta, ODT
from .presentacion.filas_bandeja import preparar_filas


class FiltroCECOTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="prueba")
        self.client.force_login(self.admin)
        for numero, ceco, revisar in ((1,"",False),(2,"",True),(3,"   ",False),(4,"50-01-01",False),(5,"50-02-02",True)):
            CatalogoCuenta.objects.create(codigo_cuenta=f"FIR-{numero}", nombre_cuenta=f"Cliente {numero}",
                tipo_cliente="B2C", ceco=ceco, requiere_revision_ceco=revisar)

    def consultar(self, **filtros):
        return self.client.get(reverse("administrar_cuentas"), filtros)

    def codigos(self, respuesta):
        return {c.codigo_cuenta for c in respuesta.context["cuentas"]}

    def test_sin_ceco_incluye_vacios_y_espacios_sin_exigir_marca(self):
        respuesta = self.consultar(estado_ceco="sin")
        self.assertEqual(self.codigos(respuesta), {"FIR-1","FIR-2","FIR-3"})
        self.assertContains(respuesta, 'value="sin" selected')
        self.assertEqual(respuesta.context["revisar_ceco"], 4)
        self.assertEqual(CatalogoCuenta.objects.count(), 5)
        self.assertFalse(CatalogoCuenta.objects.get(codigo_cuenta="FIR-1").requiere_revision_ceco)

    def test_con_ceco_y_por_revisar_son_filtros_distintos(self):
        self.assertEqual(self.codigos(self.consultar(estado_ceco="con")), {"FIR-4","FIR-5"})
        self.assertEqual(self.codigos(self.consultar(estado_ceco="revisar")), {"FIR-1","FIR-2","FIR-3","FIR-5"})

    def test_combina_busqueda_clasificacion_y_pendientes(self):
        respuesta = self.consultar(estado_ceco="sin", q="Cliente 3", tipo="B2C", pendientes="1")
        self.assertEqual(self.codigos(respuesta), {"FIR-3"})
        self.assertEqual(self.codigos(self.consultar(estado_ceco="con", q="50-02")), {"FIR-5"})
        self.assertEqual(self.codigos(self.consultar(estado_ceco="sin", tipo="B2B")), set())

    def test_paginacion_conserva_filtro_y_valor_invalido_no_restringe(self):
        CatalogoCuenta.objects.bulk_create([CatalogoCuenta(codigo_cuenta=f"FIR-X{n}",tipo_cliente="B2C") for n in range(51)])
        respuesta = self.consultar(estado_ceco="sin", tipo="B2C", page="2")
        self.assertEqual(respuesta.context["pagina"].number, 2)
        self.assertEqual(respuesta.context["pagina"].paginator.count, 54)
        self.assertIn("estado_ceco=sin", respuesta.context["querystring"])
        self.assertIn("tipo=B2C", respuesta.context["querystring"])
        self.assertEqual(self.consultar(estado_ceco="inventado").context["pagina"].paginator.count, 56)

    def test_no_otorga_permiso_de_administracion(self):
        usuario = User.objects.create_user("lectura")
        self.client.force_login(usuario)
        self.assertEqual(self.consultar(estado_ceco="sin").status_code, 403)

    def test_aviso_unificado_para_catalogo_ausente_vacio_o_por_revisar(self):
        filas = [ODT(numero=n, cuenta_completa=f"FIR-{n} - Cuenta", valor_pago_tecnico=100) for n in range(1,7)]
        catalogo = {c.codigo_cuenta:c for c in CatalogoCuenta.objects.all()}
        responsables = {n:{"nombre":"Responsable","identificado":True} for n in range(1,7)}
        with self.assertNumQueries(0):
            preparar_filas(filas, coordinadores_pagina=responsables, facturadas=set(), catalogo=catalogo,
                puede_procesar=False, puede_asignar=False)
        self.assertEqual({o.numero for o in filas if o.ceco_requiere_revision}, {1,2,3,5,6})
        self.assertEqual(filas[5].ceco_catalogo, "")
        self.assertFalse(filas[5].cuenta_en_catalogo)
        html = render_to_string("revisiones/bandeja.html", {"registros":filas,"bandeja_url":"bandeja","filtros":{}})
        self.assertEqual(html.count("Asignar / revisar CECO"), 5)
        self.assertNotIn('>Sin CECO</span>', html)
        self.assertIn("50-01-01", html)


class PosicionCreacionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin",password="prueba")
        self.client.force_login(self.admin)
        ODT.objects.bulk_create([ODT(numero=n,cuenta_completa="FIR-1 - Cuenta",contratista="Proveedor",
            servicio=SERVICIOS_PRINCIPALES[0],valor_pago_tecnico=100,fecha_creacion=timezone.now()) for n in range(1,113)])
        self.responsables = patch("revisiones.vistas.bandeja.coordinadores_para_mostrar",
            side_effect=lambda request,numeros:{n:{"nombre":"Responsable","identificado":True} for n in numeros})
        self.responsables.start()
        self.addCleanup(self.responsables.stop)

    def consultar(self, pagina, ancla=None, vista="bandeja_creacion"):
        filtros = {"page":pagina,"estado":"","fecha_desde":"","fecha_hasta":""}
        if ancla is not None:
            filtros["ubicar_odt"] = ancla
        return self.client.get(reverse(vista), filtros)

    def test_servicio_monto_y_estado_conservan_fila_y_paginas_dos_y_tres(self):
        for pagina in (2,3):
            antes = self.consultar(pagina)
            numeros = [o.numero for o in antes.context["registros"]]
            numero = numeros[4]
            cambios = (
                ("guardar_fila", {"servicio":SERVICIOS_PRINCIPALES[1],"monto":"100"}),
                ("guardar_fila", {"servicio":SERVICIOS_PRINCIPALES[1],"monto":"200","confirmar_monto":"SI"}),
                ("actualizar_revision", {"estado":"EN_REVISION","comentario":"Verificar antecedentes"}),
            )
            for endpoint, datos in cambios:
                respuesta = self.client.post(reverse(endpoint), {"numero":numero, **datos})
                self.assertEqual(respuesta.status_code, 200, respuesta.content)
                despues = self.consultar(pagina, numero)
                self.assertEqual(despues.context["pagina"].number, pagina)
                self.assertEqual([o.numero for o in despues.context["registros"]], numeros)
                self.assertNotIn("ubicar_odt", despues.context["querystring"])
            # La prioridad de correcciones permanece en Gestión de pagos.
            self.assertEqual(self.consultar(pagina, numero, "bandeja").context["pagina"].number, 1)

    def test_ancla_ajena_no_amplia_el_alcance_filtrado(self):
        respuesta = self.client.get(reverse("bandeja_creacion"), {"page":"1","numero_odt":"112",
            "ubicar_odt":"1","estado":"","fecha_desde":"","fecha_hasta":""})
        self.assertEqual([o.numero for o in respuesta.context["registros"]], [112])
