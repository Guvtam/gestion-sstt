from unittest.mock import patch
from django.contrib.auth.models import User, AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.db import transaction
from .casos_uso.gestion_correcciones import gestionar_correccion
from .correcciones import registrar_cambio_manual
from .dominio.errores import DatosODTInvalidos, ODTBloqueada, ODTNoEncontrada, VerificacionCoordinadorFallida
from .models import ODT, CorreccionODT, EventoCorreccionODT


class GestionCorreccionesTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser("admin",password="prueba")
        self.coordinador=User.objects.create_user("jtapia")
        self.odt=ODT.objects.create(numero=78948,servicio="Original",
                                    valor_pago_tecnico=100,valor_pago_editado=200)
        with transaction.atomic():
            self.seguimiento=registrar_cambio_manual(self.odt,self.admin)
        self.eventos=EventoCorreccionODT.objects.count()

    def gestionar(self,usuario=None,**opciones):
        datos=dict(numero=self.odt.numero,estado="EN_PROCESO")
        datos.update(opciones)
        return gestionar_correccion(usuario or self.admin,**datos)

    def test_procesada_guarda_actor_fecha_y_evento(self):
        resultado=self.gestionar()
        self.seguimiento.refresh_from_db()
        evento=EventoCorreccionODT.objects.first()
        self.assertEqual(resultado.estado,"EN_PROCESO")
        self.assertTrue(resultado.cambio)
        self.assertEqual(self.seguimiento.actualizado_por,self.admin)
        self.assertIsNotNone(self.seguimiento.gestionado_en)
        self.assertEqual((evento.estado_anterior,evento.estado_nuevo),("PENDIENTE","EN_PROCESO"))
        self.assertEqual(evento.usuario,self.admin)

    def test_mismo_estado_no_duplica_evento(self):
        resultado=self.gestionar(estado="PENDIENTE")
        self.assertFalse(resultado.cambio)
        self.assertEqual(EventoCorreccionODT.objects.count(),self.eventos)

    def test_admin_puede_volver_a_pendiente(self):
        self.gestionar()
        self.assertEqual(self.gestionar(estado="PENDIENTE").estado,"PENDIENTE")

    def test_coordinador_solo_procesada_y_con_alcance_verificado(self):
        self.assertTrue(self.gestionar(self.coordinador,verificar_alcance=lambda numero:True).cambio)
        with self.assertRaises(DatosODTInvalidos):
            self.gestionar(self.coordinador,estado="PENDIENTE",verificar_alcance=lambda numero:True)

    def test_fuera_de_alcance_o_origen_caido_no_escriben(self):
        with self.assertRaises(PermissionDenied):
            self.gestionar(self.coordinador,verificar_alcance=lambda numero:False)
        def fallar(numero):
            raise RuntimeError("dato privado")
        with self.assertRaises(VerificacionCoordinadorFallida) as error:
            self.gestionar(self.coordinador,verificar_alcance=fallar)
        self.assertNotIn("dato privado",str(error.exception))
        self.assertEqual(EventoCorreccionODT.objects.count(),self.eventos)

    def test_invocacion_directa_verifica_responsable_por_defecto(self):
        with patch("revisiones.casos_uso.autorizacion.identificar_coordinadores_odt",
                   return_value={78948:{"identificado":False,"usuario":None}}) as origen:
            with self.assertRaises(PermissionDenied):
                self.gestionar(self.coordinador)
        origen.assert_called_once_with([78948])

    def test_sin_permiso_anonimo_e_inactivo_no_escriben(self):
        usuarios=[AnonymousUser(),User.objects.create_user("sin_permiso"),
                  User.objects.create_superuser("inactivo",password="prueba",is_active=False)]
        for usuario in usuarios:
            with self.subTest(usuario=str(usuario)), self.assertRaises(PermissionDenied):
                self.gestionar(usuario)
        self.assertEqual(EventoCorreccionODT.objects.count(),self.eventos)

    def test_fallo_evento_revierte_estado_y_fecha(self):
        with patch("revisiones.casos_uso.gestion_correcciones.EventoCorreccionODT.objects.create",
                   side_effect=RuntimeError("fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.gestionar()
        self.seguimiento.refresh_from_db()
        self.assertEqual(self.seguimiento.estado,"PENDIENTE")
        self.assertIsNone(self.seguimiento.gestionado_en)
        self.assertEqual(EventoCorreccionODT.objects.count(),self.eventos)

    def test_fallo_posterior_a_creacion_revierte_seguimiento_y_eventos_nuevos(self):
        self.seguimiento.delete()
        real=EventoCorreccionODT.objects.create
        llamadas=[]
        def guardar(**datos):
            llamadas.append(datos)
            if len(llamadas)==2:
                raise RuntimeError("segundo evento fallido")
            return real(**datos)
        with patch("revisiones.casos_uso.gestion_correcciones.EventoCorreccionODT.objects.create",side_effect=guardar):
            with self.assertRaises(RuntimeError):
                self.gestionar()
        self.assertEqual(len(llamadas),2)
        self.assertFalse(CorreccionODT.objects.filter(odt=self.odt).exists())
        self.assertEqual(EventoCorreccionODT.objects.count(),self.eventos)

    def test_actualizada_y_coincidencia_no_admiten_cambio_manual(self):
        CorreccionODT.objects.filter(pk=self.seguimiento.pk).update(estado="ACTUALIZADA")
        with self.assertRaises(ODTBloqueada):
            self.gestionar()
        self.seguimiento.delete()
        ODT.objects.filter(pk=self.odt.pk).update(valor_pago_tecnico=200)
        with self.assertRaises(ODTBloqueada):
            self.gestionar()
        self.assertFalse(CorreccionODT.objects.filter(odt=self.odt).exists())
        self.assertEqual(EventoCorreccionODT.objects.count(),self.eventos)

    def test_sin_modificaciones_y_no_encontrada(self):
        self.seguimiento.delete()
        ODT.objects.filter(pk=self.odt.pk).update(valor_pago_editado=None)
        with self.assertRaises(ODTBloqueada):
            self.gestionar()
        with self.assertRaises(ODTNoEncontrada):
            self.gestionar(numero=12345)

    def test_formato_admitido_y_entradas_ambiguas_rechazadas(self):
        self.assertEqual(self.gestionar(numero="78 948").estado,"EN_PROCESO")
        for numero in ("ODT78948","-78948","78948xyz","١٢٣",0,"1.2"):
            with self.subTest(numero=numero), self.assertRaises(DatosODTInvalidos):
                self.gestionar(numero=numero)

    def test_actualizada_no_es_un_estado_manual_y_monto_cero_se_conserva(self):
        with self.assertRaises(DatosODTInvalidos):
            self.gestionar(estado="ACTUALIZADA")
        ODT.objects.filter(pk=self.odt.pk).update(valor_pago_editado=0)
        CorreccionODT.objects.filter(pk=self.seguimiento.pk).update(monto_objetivo=0)
        self.gestionar()
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.valor_pago_editado,0)
