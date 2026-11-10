from datetime import date
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.template import engines
from django.test import TestCase, RequestFactory
from .models import ODT
from .calendario_servicios import calendario_servicios

class CalendarioServiciosTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", password="test")
        for n, estado, visita, servicio in (
            (1,"Asignado",date(2026,11,10),"MANTENIMIENTO PREVENTIVO"),
            (2," ASIGNADO ",date(2026,11,10),"RENOVACION"),
            (3,"Finalizado",date(2026,11,10),"PREVENTIVO"),
            (4,"Cancelado",date(2026,11,10),"PREVENTIVO"),
            (5,"Pendiente",date(2026,11,10),"PREVENTIVO"),
            (6,"Asignado",None,"PREVENTIVO"),
            (7,"Asignado",date(2026,12,1),"PREVENTIVO"),
        ):
            ODT.objects.create(numero=n, estado_softguard=estado, fecha_visita=visita,
                servicio=servicio, cuenta_completa=f"FIR-{n} - Cuenta {n}", tecnico="Técnico")

    def consultar(self, **datos):
        req = RequestFactory().get("/", {"mes":"2026-11", **datos})
        req.user = self.user
        with patch("revisiones.calendario_servicios.render", side_effect=lambda r,t,c:c):
            return calendario_servicios(req)

    def eventos(self, contexto):
        return [e for semana in contexto["semanas"] for dia in semana for e in dia["eventos"]]

    def test_visitas_abiertas_y_finalizadas_con_fecha_del_mes(self):
        c = self.consultar()
        self.assertEqual({e["numero"] for e in self.eventos(c)}, {1,2,3,5})
        self.assertEqual(c["cantidad"],4)
        dia = next(d for s in c["semanas"] for d in s if d["fecha"]==date(2026,11,10))
        self.assertEqual(len(dia["eventos"]),4)

    def test_no_genera_estimaciones(self):
        self.assertTrue(all(e["numero"] for e in self.eventos(self.consultar())))

    def test_servicio_corregido_y_filtros(self):
        ODT.objects.filter(numero=1).update(servicio_editado="CORREGIDO")
        c=self.consultar(servicio="CORREGIDO", q="FIR-1")
        self.assertEqual([e["numero"] for e in self.eventos(c)], [1])
        self.assertIn("q=FIR-1", c["url_mes_siguiente"])
        self.assertIn("servicios=CORREGIDO", c["url_mes_siguiente"])

    def test_mes_siguiente_y_mes_invalido(self):
        self.assertEqual([e["numero"] for e in self.eventos(self.consultar(mes="2026-12"))], [7])
        self.assertTrue(self.consultar(mes="invalido")["errores"])

    def test_plantilla_lista_cuentas_y_enlaces(self):
        with patch("django.urls.reverse", return_value="/test/"):
            html=engines["django"].get_template("revisiones/calendario_servicios.html").render(self.consultar())
        self.assertIn("FIR-1",html)
        self.assertIn("numero_odt=1",html)
        self.assertIn("RENOVACION",html)
        self.assertNotIn("Próximo estimado",html)

    def test_sin_permiso_denegado(self):
        self.user=get_user_model().objects.create_user("sin_permiso")
        with self.assertRaises(PermissionDenied):
            self.consultar()

    def test_colores_fecha_hoy_y_prioridad_finalizada(self):
        with patch("revisiones.calendario_servicios.timezone.localdate", return_value=date(2026,11,10)):
            ODT.objects.filter(numero=1).update(fecha_visita=date(2026,11,9))
            ODT.objects.filter(numero=2).update(fecha_visita=date(2026,11,10))
            ODT.objects.filter(numero=3).update(fecha_visita=date(2026,11,1))
            ODT.objects.create(numero=8,cuenta_completa="FIR-8",estado_softguard="En proceso",fecha_visita=date(2026,11,8))
            c=self.consultar()
        eventos={e["numero"]:e for e in self.eventos(c)}
        self.assertEqual(eventos[1]["categoria"],"atrasadas")
        self.assertEqual(eventos[2]["categoria"],"abiertas")
        self.assertEqual(eventos[3]["categoria"],"realizadas")
        self.assertEqual(eventos[8]["categoria"],"atrasadas")
        self.assertEqual(c["totales"],{"realizadas":1,"abiertas":2,"atrasadas":2})
        self.assertEqual(sum(c["totales"].values()),c["cantidad"])
        self.assertNotIn(4,eventos)
        self.assertNotIn(6,eventos)

    def test_leyenda_y_etiquetas_no_dependen_solo_del_color(self):
        with patch("django.urls.reverse",return_value="/test/"):
            html=engines["django"].get_template("revisiones/calendario_servicios.html").render(self.consultar())
        for etiqueta in ("Azul · Realizadas","Verde · Abiertas","Amarillo · Atrasadas","Realizada · Finalizado"):
            self.assertIn(etiqueta,html)
        self.assertIn("visita-realizadas",html)

    def test_servicios_disponibles_solo_del_mes_y_todos_marcados(self):
        ODT.objects.filter(numero=7).update(servicio="SOLO DICIEMBRE")
        c=self.consultar()
        self.assertNotIn("SOLO DICIEMBRE",c["servicios"])
        self.assertEqual(c["servicios_seleccionados"],c["servicios"])
        self.assertNotIn("servicios_filtrados",c["url_mes_siguiente"])
        self.assertIn("SOLO DICIEMBRE",self.consultar(mes="2026-12")["servicios"])

    def test_multiseleccion_y_deseleccion_total(self):
        c=self.consultar(servicios_filtrados="1",servicios=["RENOVACION","MANTENIMIENTO PREVENTIVO"])
        self.assertEqual({e["numero"] for e in self.eventos(c)},{1,2})
        self.assertIn("servicios=RENOVACION",c["url_mes_siguiente"])
        c=self.consultar(servicios_filtrados="1")
        self.assertEqual(c["cantidad"],0)
        self.assertEqual(c["servicios_seleccionados"],[])
        self.assertIn("servicios_filtrados=1",c["url_mes_siguiente"])

    def test_ajax_servicios_solo_mes_visitas_admitidas(self):
        import json
        ODT.objects.filter(numero=7).update(servicio="SOLO DICIEMBRE")
        ODT.objects.filter(numero=4).update(servicio="CANCELADO NO LISTAR")
        req=RequestFactory().get("/",{"mes":"2026-11","formato":"servicios"})
        req.user=self.user
        respuesta=calendario_servicios(req)
        datos=json.loads(respuesta.content)
        self.assertNotIn("SOLO DICIEMBRE",datos["servicios"])
        self.assertNotIn("CANCELADO NO LISTAR",datos["servicios"])
        self.assertIn("RENOVACION",datos["servicios"])

    def test_sin_servicio_se_puede_seleccionar(self):
        ODT.objects.filter(numero=1).update(servicio="")
        c=self.consultar(servicios_filtrados="1",servicios=["__SIN_SERVICIO__"])
        self.assertEqual([e["numero"] for e in self.eventos(c)],[1])

    def preparar_coordinador(self):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        usuario = get_user_model().objects.create_user("rsilva", password="prueba")
        permiso, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(ODT), codename="ver_bandeja_sstt")
        usuario.user_permissions.add(permiso)
        self.client.force_login(usuario)
        self.user = usuario
        return usuario

    @staticmethod
    def responsables_propios(numeros):
        return {n:{"nombre":"Romina" if n in (1,3) else "Otro", "identificado":n!=5,
                   "usuario":"rsilva" if n in (1,3) else "jtapia" if n!=5 else None}
                for n in numeros}

    def test_coordinador_ve_solo_visitas_propias_y_totales_restringidos(self):
        self.preparar_coordinador()
        with patch("revisiones.acceso_coordinadores.identificar_coordinadores_odt", side_effect=self.responsables_propios):
            contexto = self.consultar(coordinador="jtapia")
        self.assertEqual({e["numero"] for e in self.eventos(contexto)}, {1,3})
        self.assertEqual(contexto["disponibles_mes"], 2)
        self.assertEqual(contexto["cantidad"], 2)
        self.assertEqual(set(contexto["servicios"]), {"MANTENIMIENTO PREVENTIVO", "PREVENTIVO"})
        self.assertTrue(contexto["es_coordinador"])

    def test_coordinador_accede_por_middleware_y_ajax_no_filtra_servicios_ajenos(self):
        from django.urls import reverse
        self.preparar_coordinador()
        with patch("revisiones.acceso_coordinadores.identificar_coordinadores_odt", side_effect=self.responsables_propios):
            respuesta = self.client.get(reverse("calendario_servicios"), {"mes":"2026-11"})
            opciones = self.client.get(reverse("calendario_servicios"), {"mes":"2026-11", "formato":"servicios"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "FIR-1")
        self.assertContains(respuesta, "FIR-3")
        self.assertNotContains(respuesta, "FIR-2")
        self.assertNotContains(respuesta, "FIR-5")
        self.assertNotContains(respuesta, reverse("mantenimientos_preventivos"))
        self.assertEqual(set(opciones.json()["servicios"]), {"MANTENIMIENTO PREVENTIVO", "PREVENTIVO"})

    def test_coordinador_no_obtiene_calendario_si_no_se_puede_verificar_alcance(self):
        from django.urls import reverse
        from .coordinadores_softguard import CoordinadoresNoDisponibles
        self.preparar_coordinador()
        with patch("revisiones.acceso_coordinadores.identificar_coordinadores_odt", side_effect=CoordinadoresNoDisponibles()):
            respuesta = self.client.get(reverse("calendario_servicios"), {"mes":"2026-11"})
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotContains(respuesta, "FIR-2", status_code=503)
