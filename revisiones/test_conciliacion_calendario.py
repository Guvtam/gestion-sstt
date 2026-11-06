from datetime import date, datetime
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, RequestFactory
from django.utils import timezone
from .models import ODT
from .calendario_servicios import calendario_servicios
from .casos_uso.sincronizacion import ejecutar_sincronizacion
from .integraciones.transformacion_odt import transformar_registro, RegistroOrigenInvalido


class ConciliacionCalendarioTests(TestCase):
    def registro(self, n, estado="Finalizado"):
        return {"Numero":n, "CuentaCompleta":f"FIR-{n}", "Estado":estado,
                "Servicio":("PREVENTIVO","RENOVACION","CON COBRO","SIN COBRO")[n%4],
                "FechaCreacion":timezone.make_aware(datetime(2026,11,1,10)),
                "FechaFinalizacion":timezone.make_aware(datetime(2026,11,5,10)) if estado=="Finalizado" else None,
                "FechaPago":date(2026,11,5) if estado=="Finalizado" else None,
                "FechaVisita":date(2026,11,2 if estado=="Finalizado" else 10)}

    def contexto(self, **params):
        request=RequestFactory().get("/",{"mes":"2026-11",**params})
        request.user=User.objects.create_superuser(f"admin{User.objects.count()}",password="prueba")
        with patch("revisiones.calendario_servicios.render",side_effect=lambda r,t,c:c):
            return calendario_servicios(request)

    def test_pago_sql_date_no_descarta_odt_finalizada(self):
        numero, datos=transformar_registro(self.registro(1))
        self.assertEqual(numero,1)
        self.assertEqual(datos["fecha_pago"].date(),date(2026,11,5))
        self.assertTrue(timezone.is_aware(datos["fecha_pago"]))
        self.assertEqual(datos["fecha_visita"],date(2026,11,2))

    def test_validacion_de_creacion_y_finalizacion_sigue_estricta(self):
        for campo in ("FechaCreacion","FechaFinalizacion"):
            datos=self.registro(1)
            datos[campo]=date(2026,11,1)
            with self.assertRaises(RegistroOrigenInvalido):
                transformar_registro(datos)

    def test_sincronizar_76_visitas_con_47_finalizadas_no_pierde_filas_por_pago(self):
        datos=[self.registro(n,"Finalizado" if n<=47 else "Asignado") for n in range(1,77)]
        for n in range(48,58):
            datos[n-1]["FechaVisita"]=date(2026,11,4)
        resultado=ejecutar_sincronizacion(lambda:iter(datos),tamano_lote=25)
        self.assertEqual((resultado.creadas,resultado.omitidas),(76,0))
        with patch("revisiones.calendario_servicios.timezone.localdate",return_value=date(2026,11,6)):
            contexto=self.contexto()
        self.assertEqual(contexto["disponibles_mes"],76)
        self.assertEqual(contexto["cantidad"],76)
        self.assertEqual(contexto["totales"],{"realizadas":47,"abiertas":19,"atrasadas":10})
        self.assertEqual(len(contexto["servicios"]),4)

    def test_diferencia_por_filtros_se_muestra_sin_perder_datos(self):
        ejecutar_sincronizacion(lambda:iter([self.registro(1),self.registro(2)]))
        contexto=self.contexto(servicios_filtrados="1",servicios=["RENOVACION"])
        self.assertEqual(contexto["disponibles_mes"],2)
        self.assertEqual(contexto["cantidad"],1)
        self.assertEqual(ODT.objects.count(),2)

    def test_diagnostico_compara_origen_sin_escribir(self):
        ODT.objects.create(numero=1,fecha_visita=date(2026,11,2),estado_softguard="Finalizado")
        salida=StringIO()
        with patch("revisiones.servicios_sql.iterar_odts_completas",return_value=iter([self.registro(2),self.registro(3)])):
            call_command("diagnosticar_calendario",mes="2026-11",comparar_origen=True,stdout=salida)
        self.assertIn("Visitas locales del mes (sin filtros): 1",salida.getvalue())
        self.assertIn("2 visitas del mes",salida.getvalue())
        self.assertEqual(list(ODT.objects.values_list("numero",flat=True)),[1])

    def test_invalido_no_se_oculta_en_diagnostico(self):
        salida=StringIO()
        with patch("revisiones.servicios_sql.iterar_odts_completas",return_value=iter([{"Numero":"invalido"}])):
            call_command("diagnosticar_calendario",mes="2026-11",comparar_origen=True,stdout=salida)
        self.assertIn("1 filas inválidas",salida.getvalue())

    def test_diagnostico_local_no_consulta_origen(self):
        with patch("revisiones.servicios_sql.iterar_odts_completas") as origen:
            call_command("diagnosticar_calendario",mes="2026-11",stdout=StringIO())
        origen.assert_not_called()
