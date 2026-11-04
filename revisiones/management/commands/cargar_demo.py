from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from revisiones.models import ODT
class Command(BaseCommand):
    help = 'Carga ODT completamente ficticias para probar la bandeja'
    def handle(self,*args,**kwargs):
        ejemplos = [
            (900001,'Contratista de prueba A','M01','B2B','Finalizado',45000),
            (900002,'Contratista de prueba A','W21','B2C','Asignado',32000),
            (900003,'Contratista de prueba B','M02','B2B','Finalizado',55000),
            (900004,'Contratista de prueba B','W15','B2C','Pendiente',38000),
            (900005,'Contratista de prueba C','W22','B2B','Finalizado',42000),
        ]
        for n,c,s,t,e,m in ejemplos:
            ODT.objects.get_or_create(numero=n,defaults={'contratista':c,'servicio':s,'tipo_cliente':t,'estado_softguard':e,'fecha_visita':date(2026,10,20),'monto_origen':Decimal(m)})
        self.stdout.write(self.style.SUCCESS('5 ODT de prueba disponibles.'))
