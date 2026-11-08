from unittest.mock import patch
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from .casos_uso.cuentas import actualizar_cuenta
from .dominio.administracion_cuentas import CuentaInvalida, CuentaNoEncontrada
from .models import CatalogoCuenta, ODT


class ActualizarCuentaTests(TestCase):
    def setUp(self):
        self.usuario=User.objects.create_superuser("admin",password="prueba")
        self.cuenta=CatalogoCuenta.objects.create(codigo_cuenta="FIR-1",tipo_cliente="SIN_CLASIFICAR",
                                                 ceco="",requiere_revision_ceco=True)
        self.odt=ODT.objects.create(numero=1,cuenta_completa="fir - 1 - Cuenta renombrada",
            tipo_cliente="SIN_CLASIFICAR",servicio_editado="Servicio manual",valor_pago_editado=0)
        ODT.objects.create(numero=2,cuenta_completa="FIR-2",tipo_cliente="B2C")

    def actualizar(self,**opciones):
        datos=dict(cuenta_id=self.cuenta.pk,tipo="B2B",ceco="50-01-01",observaciones=" Validado ")
        datos.update(opciones)
        return actualizar_cuenta(self.usuario,**datos)

    def test_actualiza_catalogo_y_solo_odt_de_la_cuenta(self):
        resultado=self.actualizar()
        self.cuenta.refresh_from_db()
        self.odt.refresh_from_db()
        self.assertEqual(resultado.odts_actualizadas,1)
        self.assertEqual(self.cuenta.actualizado_por,self.usuario)
        self.assertEqual(self.cuenta.observaciones,"Validado")
        self.assertFalse(self.cuenta.requiere_revision_ceco)
        self.assertEqual(self.odt.tipo_cliente,"B2B")
        self.assertEqual(self.odt.servicio_editado,"Servicio manual")
        self.assertEqual(self.odt.valor_pago_editado,0)
        self.assertEqual(ODT.objects.get(numero=2).tipo_cliente,"B2C")

    def test_ceco_vacio_queda_pendiente_de_revision(self):
        self.actualizar(ceco=" ")
        self.cuenta.refresh_from_db()
        self.assertEqual(self.cuenta.ceco,"")
        self.assertTrue(self.cuenta.requiere_revision_ceco)

    def test_repetir_no_reescribe_odt_sin_cambios(self):
        self.actualizar()
        with patch("revisiones.casos_uso.cuentas.ODT.objects.bulk_update") as guardar:
            resultado=self.actualizar()
        guardar.assert_not_called()
        self.assertEqual(resultado.odts_actualizadas,0)

    def test_validacion_no_guarda(self):
        for opciones in ({"tipo":"INVALIDO"},{"ceco":"x"*51}):
            with self.subTest(opciones=opciones), self.assertRaises(CuentaInvalida):
                self.actualizar(**opciones)
        self.cuenta.refresh_from_db()
        self.assertEqual(self.cuenta.tipo_cliente,"SIN_CLASIFICAR")

    def test_cuenta_ausente(self):
        with self.assertRaises(CuentaNoEncontrada):
            self.actualizar(cuenta_id=99999)

    def test_sin_permiso_e_inactivo_no_pueden_invocar_caso_directamente(self):
        for usuario in (User.objects.create_user("sin_permiso"),
                        User.objects.create_superuser("inactivo",password="prueba",is_active=False)):
            with self.subTest(usuario=usuario.username), self.assertRaises(PermissionDenied):
                actualizar_cuenta(usuario,cuenta_id=self.cuenta.pk,tipo="B2B",ceco="",observaciones="")

    def test_coordinador_no_administra_cuentas_aunque_tenga_permiso(self):
        usuario=User.objects.create_user("jtapia")
        permiso,_=Permission.objects.get_or_create(codename="administrar_cuentas_sstt",
            content_type=ContentType.objects.get_for_model(ODT),defaults={"name":"Administrar cuentas"})
        usuario.user_permissions.add(permiso)
        with self.assertRaises(PermissionDenied):
            actualizar_cuenta(usuario,cuenta_id=self.cuenta.pk,tipo="B2B",ceco="",observaciones="")

    def test_fallo_en_segundo_lote_revierte_catalogo_y_primer_lote(self):
        ODT.objects.bulk_create([ODT(numero=n,cuenta_completa="FIR-1",tipo_cliente="SIN_CLASIFICAR")
                                 for n in range(10,511)])
        real=ODT.objects.bulk_update
        tamanos=[]
        def guardar(lote,*args,**kwargs):
            tamanos.append(len(lote))
            if len(tamanos)==2:
                raise RuntimeError("fallo simulado")
            return real(lote,*args,**kwargs)
        with patch("revisiones.casos_uso.cuentas.ODT.objects.bulk_update",side_effect=guardar):
            with self.assertRaises(RuntimeError):
                self.actualizar()
        self.assertEqual(tamanos,[500,2])
        self.cuenta.refresh_from_db()
        self.assertEqual(self.cuenta.tipo_cliente,"SIN_CLASIFICAR")
        self.assertFalse(ODT.objects.filter(cuenta_completa__in=["FIR-1",self.odt.cuenta_completa],
                                          tipo_cliente="B2B").exists())


    def test_adaptador_conserva_metodo_mensaje_y_404(self):
        self.client.force_login(self.usuario)
        url=reverse("guardar_cuenta",args=[self.cuenta.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        respuesta=self.client.post(url,{"tipo_cliente":"INVALIDO"},follow=True)
        self.assertContains(respuesta,"La clasificación seleccionada no es válida.")
        self.assertContains(respuesta,'role="alert"')
        self.assertEqual(self.client.post(reverse("guardar_cuenta",args=[99999]),
            {"tipo_cliente":"B2B","ceco":"","observaciones":""}).status_code,404)
