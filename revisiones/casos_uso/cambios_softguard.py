"""Captura de valores de origen antes de reemplazarlos; no compara ajustes SSTT."""
from ..models import CambioSoftGuard


def preparar_cambios(odt, datos, detectado_en, ejecucion):
    cambios = []
    for campo, _ in CambioSoftGuard.CAMPOS:
        anterior, nuevo = getattr(odt, campo), datos[campo]
        if anterior == nuevo:
            continue
        def texto(valor):
            return format(valor, '.2f') if campo == 'valor_pago_tecnico' else valor
        cambios.append(CambioSoftGuard(odt=odt, ejecucion=ejecucion, campo=campo,
            valor_anterior=texto(anterior), valor_nuevo=texto(nuevo), detectado_en=detectado_en))
    return cambios
