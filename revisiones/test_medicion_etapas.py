from contextlib import ExitStack
from types import ModuleType
from unittest.mock import patch
import sys

from django.test import SimpleTestCase
from .integraciones.medicion_etapas import instrumentar_etapas


class MedicionEtapasTests(SimpleTestCase):
    def test_anidacion_conserva_resultado_y_tiempos_inclusivos(self):
        modulo=ModuleType("prueba_medicion")
        modulo.interior=lambda x:x+1
        modulo.exterior=lambda x:modulo.interior(x)*2
        original=modulo.exterior
        objetivos={"Exterior":"prueba_medicion.exterior","Interior":"prueba_medicion.interior"}
        with patch.dict(sys.modules,{"prueba_medicion":modulo}):
            with patch("revisiones.integraciones.medicion_etapas.perf_counter",side_effect=[0,1,3,5]):
                with ExitStack() as stack:
                    resultados=instrumentar_etapas(stack,objetivos)
                    self.assertEqual(modulo.exterior(4),10)
            self.assertIs(modulo.exterior,original)
        self.assertEqual(resultados["Exterior"],{"llamadas":1,"segundos":5.0,"fallos":0})
        self.assertEqual(resultados["Interior"],{"llamadas":1,"segundos":2.0,"fallos":0})

    def test_fallo_se_propaga_sin_guardar_mensaje_y_restaura_funcion(self):
        modulo=ModuleType("prueba_medicion")
        def fallar():
            raise RuntimeError("password=secreto")
        modulo.funcion=fallar
        with patch.dict(sys.modules,{"prueba_medicion":modulo}):
            with self.assertRaises(RuntimeError):
                with ExitStack() as stack:
                    resultados=instrumentar_etapas(stack,{"Prueba":"prueba_medicion.funcion"})
                    modulo.funcion()
            self.assertIs(modulo.funcion,fallar)
        self.assertEqual(resultados["Prueba"]["fallos"],1)
        self.assertNotIn("secreto",str(resultados))

    def test_objetivo_ausente_restaura_parches_anteriores(self):
        modulo=ModuleType("prueba_medicion")
        original=lambda:1
        modulo.funcion=original
        with patch.dict(sys.modules,{"prueba_medicion":modulo}):
            with self.assertRaises(AttributeError):
                with ExitStack() as stack:
                    instrumentar_etapas(stack,{"Uno":"prueba_medicion.funcion","Dos":"prueba_medicion.ausente"})
            self.assertIs(modulo.funcion,original)
