from datetime import datetime
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .acceso_coordinadores import (
    coordinadores_en_peticion, coordinadores_para_mostrar, coordinador_visible,
    limitar_odts_coordinador,
)
from .coordinadores_softguard import (
    COORDINADORES_SOFTGUARD, CoordinadoresNoDisponibles,
    identificar_coordinador_odt, identificar_coordinadores_odt,
)
from .dominio.coordinadores import inferir_coordinador
from .models import AsignacionCoordinadorODT, CorreccionODT, ODT
from .servicios_sql import consultar_eventos_coordinadores


class InferenciaResponsableTests(SimpleTestCase):
    catalogo = {1: {"nombre": "Coordinador A", "usuario": "coord_a"},
                2: {"nombre": "Coordinador B", "usuario": "coord_b"}}

    def test_ultima_accion_autorizada_y_fecha_alta(self):
        movimientos = [
            {"IDUsuario": 1, "FechaHora": datetime(2026, 1, 1), "Accion": "ALTA"},
            {"IDUsuario": 2, "FechaHora": datetime(2026, 1, 2), "Accion": "ALTA"},
            {"IDUsuario": 1, "FechaHora": datetime(2026, 1, 3), "Accion": "MODIFICACION"},
            {"IDUsuario": 999, "FechaHora": datetime(2026, 1, 4), "Accion": "CIERRE"},
        ]
        r = inferir_coordinador(movimientos, self.catalogo)
        self.assertEqual(r["usuario"], "coord_a")
        self.assertEqual(r["fecha_alta"], datetime(2026, 1, 1))

    def test_empate_entre_usuarios_no_atribuye_arbitrariamente(self):
        eventos = [{"IDUsuario": n, "FechaHora": datetime(2026, 1, 1)} for n in (1, 2)]
        self.assertFalse(inferir_coordinador(eventos, self.catalogo)["identificado"])

    def test_sin_fechas_solo_identifica_un_usuario_inequivoco(self):
        self.assertEqual(inferir_coordinador([{"IDUsuario": 1}], self.catalogo)["usuario"], "coord_a")
        self.assertFalse(inferir_coordinador([{"IDUsuario": 1}, {"IDUsuario": 2}], self.catalogo)["identificado"])

    def test_sin_eventos_e_ids_invalidos_no_atribuye(self):
        for eventos in ([], [{"IDUsuario": "mal"}], [{"IDUsuario": 999}]):
            self.assertFalse(inferir_coordinador(eventos, self.catalogo)["identificado"])

    def test_fechas_iso_y_mismo_usuario_en_empate(self):
        eventos = [{"IDUsuario": "1", "FechaHora": "2026-01-01T12:00:00", "Accion": accion}
                   for accion in ("ALTA", "MODIFICACION")]
        self.assertTrue(inferir_coordinador(eventos, self.catalogo)["identificado"])


class ConsultaEventosTests(SimpleTestCase):
    def test_parametriza_numeros_y_usuarios_y_solo_pide_datos_de_atribucion(self):
        with patch("revisiones.servicios_sql._consultar", return_value=[]) as consultar:
            consultar_eventos_coordinadores([10, 20, 10], [1, 2])
        sql, parametros = consultar.call_args.args
        self.assertEqual(parametros, (10, 20, 1, 2))
        self.assertEqual(sql.count("?"), 4)
        self.assertNotIn("Observacion", sql)
        self.assertNotIn("Correo", sql)

    def test_vacio_no_abre_conexion(self):
        with patch("revisiones.servicios_sql._consultar") as consultar:
            self.assertEqual(consultar_eventos_coordinadores([], [1]), [])
        consultar.assert_not_called()

    def test_lote_demasiado_grande_no_consulta(self):
        with patch("revisiones.servicios_sql._consultar") as consultar:
            with self.assertRaises(ValueError):
                consultar_eventos_coordinadores(range(1, 252), [1])
        consultar.assert_not_called()


class CoordinadoresPorLotesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ids = list(COORDINADORES_SOFTGUARD)
        self.datos = [COORDINADORES_SOFTGUARD[i] for i in self.ids]
        self.fecha = timezone.make_aware(datetime(2026, 11, 1, 12))
        self.user = User.objects.create_user(self.datos[0]["usuario"])
        self.admin = User.objects.create_superuser("admin", password="prueba")
        ct = ContentType.objects.get_for_model(ODT)
        permiso, _ = Permission.objects.get_or_create(content_type=ct, codename="ver_bandeja_sstt")
        self.user.user_permissions.add(permiso)
        for numero in (1, 2, 3):
            ODT.objects.create(numero=numero, contratista=f"Prueba {numero}", fecha_creacion=self.fecha,
                servicio="Servicio de prueba", valor_pago_editado=100)

    def request(self, usuario=None, **params):
        r = self.factory.get("/", params)
        r.user = usuario or self.user
        return r

    def eventos(self, numeros, usuarios):
        return [{"NumeroODT": n, "IDUsuario": self.ids[0 if n % 2 else 1],
                 "FechaHora": self.fecha, "Accion": "ALTA"} for n in numeros]

    def test_lote_250_usa_una_consulta_local_y_una_de_origen(self):
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos) as origen:
            with self.assertNumQueries(2):
                r = identificar_coordinadores_odt(range(1, 251))
        origen.assert_called_once()
        self.assertEqual(len(r), 250)
        self.assertEqual(r[1]["usuario"], self.datos[0]["usuario"])
        self.assertEqual(r[2]["usuario"], self.datos[1]["usuario"])

    def test_mas_de_un_lote_y_cache_solo_en_misma_peticion(self):
        req = self.request()
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos) as origen:
            with self.assertNumQueries(6):
                primero = coordinadores_en_peticion(req, range(1, 502))
            with self.assertNumQueries(0):
                segundo = coordinadores_en_peticion(req, [1, 2])
        self.assertEqual(origen.call_count, 3)
        self.assertEqual(segundo[1], primero[1])

    def test_peticiones_distintas_no_comparten_cache(self):
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos) as origen:
            coordinadores_en_peticion(self.request(), [1])
            coordinadores_en_peticion(self.request(), [1])
        self.assertEqual(origen.call_count, 2)

    def test_asignacion_local_prevalece_y_no_se_consulta_al_origen(self):
        AsignacionCoordinadorODT.objects.create(odt=ODT.objects.get(numero=1), usuario_coordinador=self.datos[1]["usuario"])
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores") as origen:
            r = identificar_coordinadores_odt([1])
        origen.assert_not_called()
        self.assertEqual(r[1]["usuario"], self.datos[1]["usuario"])
        self.assertTrue(r[1]["asignacion_manual"])
        self.assertEqual(identificar_coordinador_odt(1)["usuario"], r[1]["usuario"])

    def test_lote_mixto_consulta_solo_las_no_asignadas(self):
        AsignacionCoordinadorODT.objects.create(odt=ODT.objects.get(numero=1), usuario_coordinador=self.datos[1]["usuario"])
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos) as origen:
            r = identificar_coordinadores_odt([1, 2])
        self.assertEqual(origen.call_args.args[0], [2])
        self.assertEqual(r[1]["usuario"], self.datos[1]["usuario"])

    def test_sin_eventos_es_sin_identificar_solo_tras_consulta_exitosa(self):
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", return_value=[]):
            r = identificar_coordinadores_odt([1])
        self.assertFalse(r[1]["identificado"])

    def test_fallo_no_se_cachea_como_sin_identificar_y_no_expone_detalles(self):
        req = self.request()
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError("secreto-inventado")):
            with self.assertRaises(CoordinadoresNoDisponibles) as error:
                coordinadores_en_peticion(req, [1])
        self.assertNotIn("secreto-inventado", str(error.exception))
        self.assertNotIn(1, req._coordinadores_sstt)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos):
            self.assertTrue(coordinador_visible(req, 1))

    def test_presentacion_offline_conserva_manuales_y_distingue_no_disponible(self):
        AsignacionCoordinadorODT.objects.create(odt=ODT.objects.get(numero=1), usuario_coordinador=self.datos[0]["usuario"])
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError):
            r = coordinadores_para_mostrar(self.request(self.admin), [1, 2])
        self.assertTrue(r[1]["identificado"])
        self.assertEqual(r[2]["nombre"], "No disponible")
        self.assertFalse(r[2]["disponible"])

    def test_limiter_no_usa_fallback_de_presentacion(self):
        req = self.request()
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError):
            with self.assertRaises(CoordinadoresNoDisponibles):
                limitar_odts_coordinador(req, ODT.objects.all())

    def test_fallo_segundo_lote_no_devuelve_seleccion_parcial(self):
        ODT.objects.bulk_create([ODT(numero=n) for n in range(4, 252)])
        def fuente(numeros, usuarios):
            if 251 in numeros:
                raise RuntimeError("Fallo simulado del segundo lote")
            return self.eventos(numeros, usuarios)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=fuente) as origen:
            with self.assertRaises(CoordinadoresNoDisponibles):
                limitar_odts_coordinador(self.request(), ODT.objects.all())
        self.assertEqual(origen.call_count, 2)

    def test_lectura_exitosa_sin_identificar_no_da_acceso_a_coordinador(self):
        req = self.request()
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", return_value=[]):
            self.assertEqual(limitar_odts_coordinador(req, ODT.objects.all()).count(), 0)
            self.assertFalse(coordinador_visible(req, 1))

    def test_manual_corrupta_no_se_atribuye_al_origen(self):
        AsignacionCoordinadorODT.objects.create(odt=ODT.objects.get(numero=1), usuario_coordinador="no_configurado")
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores") as origen:
            with self.assertRaises(CoordinadoresNoDisponibles):
                identificar_coordinadores_odt([1])
        origen.assert_not_called()

    def test_bandeja_filtra_solo_propias_reutilizando_mismo_lote(self):
        from .views import bandeja
        req = self.request(coordinador=self.datos[1]["usuario"], estado="", fecha_desde="", fecha_hasta="")
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos) as origen, \
             patch("revisiones.vistas.bandeja.render", side_effect=lambda r,t,c:c):
            contexto = bandeja(req)
        self.assertEqual({o.numero for o in contexto["registros"]}, {1, 3})
        self.assertEqual(contexto["filtros"]["coordinador"], self.datos[0]["usuario"])
        self.assertEqual(origen.call_count, 1)

    def test_ajax_acota_fecha_antes_de_resolver_responsables(self):
        from .views import contratistas_disponibles_ajax
        req = self.request(fecha_desde="2026-11-01", fecha_hasta="2026-11-01", campo_fecha="creacion")
        ODT.objects.filter(numero=2).update(fecha_creacion=self.fecha.replace(month=10))
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos) as origen:
            r = contratistas_disponibles_ajax(req)
        self.assertEqual(set(origen.call_args.args[0]), {1, 3})
        self.assertNotIn("Prueba 2", r.content.decode())

    def test_http_coordinador_no_ve_datos_si_falla_origen(self):
        self.client.force_login(self.user)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError):
            r = self.client.get(reverse("bandeja"), {"estado": "", "fecha_desde": "", "fecha_hasta": ""})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("Prueba 1", r.content.decode())

    def test_http_sin_identificar_no_incluye_fallos_de_origen(self):
        self.client.force_login(self.admin)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError):
            r = self.client.get(reverse("bandeja"), {
                "coordinador": "SIN_IDENTIFICAR", "estado": "", "fecha_desde": "", "fecha_hasta": "",
            })
        self.assertEqual(r.status_code, 503)

    def test_admin_sin_filtro_puede_ver_odt_pero_no_asignar_si_no_hay_verificacion(self):
        from .views import bandeja
        req = self.request(self.admin, estado="", fecha_desde="", fecha_hasta="")
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError), \
             patch("revisiones.vistas.bandeja.render", side_effect=lambda r,t,c:c):
            contexto = bandeja(req)
        self.assertEqual({o.numero for o in contexto["registros"]}, {1, 2, 3})
        self.assertTrue(all(o.coordinador_nombre == "No disponible" for o in contexto["registros"]))
        self.assertFalse(any(o.permite_asignar_coordinador for o in contexto["registros"]))

    def test_estadisticas_no_agrupan_fallo_como_sin_identificar(self):
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=1), corrige_monto=True, monto_objetivo=100)
        self.client.force_login(self.admin)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError):
            r = self.client.get(reverse("estadisticas_correcciones"))
        self.assertEqual(r.status_code, 503)
