from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from revisiones.models import ODT, CorreccionODT

class Command(BaseCommand):
    help = "Inicializa el seguimiento de ODT previamente modificadas"
    def handle(self, *args, **kwargs):
        qs = ODT.objects.filter(Q(servicio_editado__isnull=False) | Q(valor_pago_editado__isnull=False))
        creados = 0
        for odt in qs.iterator():
            servicio_objetivo = odt.servicio_editado if odt.servicio_editado is not None else odt.servicio
            monto_objetivo = odt.valor_pago_editado if odt.valor_pago_editado is not None else odt.valor_pago_tecnico
            coincide_servicio = (odt.servicio_editado is None or (odt.servicio or "").strip().casefold() == (servicio_objetivo or "").strip().casefold())
            coincide_monto = (odt.valor_pago_editado is None or odt.valor_pago_tecnico == monto_objetivo)
            actualizada = coincide_servicio and coincide_monto
            _, creado = CorreccionODT.objects.get_or_create(odt=odt, defaults={
                "servicio_objetivo": servicio_objetivo or "", "monto_objetivo": monto_objetivo,
                "corrige_servicio": odt.servicio_editado is not None,
                "corrige_monto": odt.valor_pago_editado is not None,
                "estado": "ACTUALIZADA" if actualizada else "PENDIENTE",
                "actualizada_en": timezone.now() if actualizada else None,
            })
            creados += int(creado)
        self.stdout.write(self.style.SUCCESS(f"Seguimientos nuevos: {creados}"))
