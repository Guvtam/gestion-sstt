
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from revisiones.models import ODT, CatalogoCuenta
from revisiones.cuentas_utils import normalizar_codigo_cuenta
from revisiones.servicios_sql import consultar_odts_completas


class Command(BaseCommand):
    help = "Sincroniza todas las ODT desde SQL Server hacia SQLite"

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true", help="No guarda cambios")

    def handle(self, *args, **options):
        simular = options["simular"]

        self.stdout.write(
            "Consultando todas las ODT disponibles en SQL Server..."
        )

        registros = consultar_odts_completas()

        total_registros = len(registros)

        self.stdout.write(
            f"Se encontraron {total_registros} ODT en SQL Server."
        )

        def texto(valor, maximo=None):
            resultado = (
                str(valor).strip()
                if valor is not None
                else ""
            )
            return resultado[:maximo] if maximo else resultado

        def fecha_valida(valor):
            if valor is None:
                return None

            if hasattr(valor, "year") and valor.year <= 1900:
                return None

            if not hasattr(valor, "hour"):
                return valor

            if timezone.is_naive(valor):
                return timezone.make_aware(
                    valor,
                    timezone.get_default_timezone()
                )

            return valor

        def fecha_solo_dia(valor):
            fecha = fecha_valida(valor)

            if fecha is None:
                return None

            return (
                fecha.date()
                if hasattr(fecha, "date")
                else fecha
            )

        def decimal_valido(valor):
            if valor is None:
                return Decimal("0")

            try:
                numero = Decimal(str(valor))
                return (
                    numero
                    if numero.is_finite()
                    else Decimal("0")
                )
            except (InvalidOperation, ValueError):
                return Decimal("0")

        creadas = 0
        actualizadas = 0
        omitidas = 0
        cuentas_nuevas = set()
        existentes_por_numero = set(ODT.objects.values_list("numero", flat=True))

        for indice, registro in enumerate(registros, start=1):

            numero_origen = registro.get("Numero")

            if numero_origen is None:
                omitidas += 1
                continue

            try:
                numero = int(numero_origen)
            except (TypeError, ValueError):
                omitidas += 1
                continue

            codigo = texto(
                registro["CodigoTecnico"], 20
            )

            tecnico = texto(
                registro["Tecnico"], 200
            )

            datos = {
                "codigo_tecnico": codigo,
                "tecnico": tecnico,

                "cuenta_completa": texto(
                    registro["CuentaCompleta"]
                ),

                "direccion": texto(
                    registro["Direccion"], 300
                ),

                "provincia": texto(
                    registro["Provincia"], 150
                ),

                "localidad": texto(
                    registro["Localidad"], 150
                ),

                "tipo_servicio": texto(
                    registro["TipoServicio"], 30
                ),

                "servicio": texto(
                    registro["Servicio"], 150
                ),

                "descripcion_servicio": texto(
                    registro["Servicio"]
                ),

                "observaciones_insumos": texto(
                    registro["ObservacionesInsumos"]
                ),

                "estado_softguard": texto(
                    registro["Estado"], 50
                ),

                "fecha_creacion": fecha_valida(
                    registro["FechaCreacion"]
                ),

                "fecha_modificacion": fecha_valida(
                    registro["FechaModificacion"]
                ),

                "fecha_visita": fecha_solo_dia(
                    registro["FechaVisita"]
                ),

                "fecha_finalizacion": fecha_valida(
                    registro["FechaFinalizacion"]
                ),

                "fecha_pago": fecha_valida(
                    registro["FechaPago"]
                ),

                "usuario_creador": texto(
                    registro["UsuarioCreador"], 200
                ),

                "correo_creador": texto(
                    registro["CorreoCreador"], 254
                ),

                "monto_origen": decimal_valido(
                    registro["Valor"]
                ),

                "costo_mano_obra": decimal_valido(
                    registro["CostoManoObra"]
                ),

                "valor_pago_tecnico": decimal_valido(
                    registro["ValorPagoTecnico"]
                ),

                "tiempo_trabajo_hrs": decimal_valido(
                    registro["TiempoTrabajoHrs"]
                ),
                
            }
            codigo_cuenta = normalizar_codigo_cuenta(
                datos["cuenta_completa"]
            )

            if codigo_cuenta:
                cuentas_nuevas.add(codigo_cuenta)

            if simular:
                if numero in existentes_por_numero:
                    actualizadas += 1
                else:
                    creadas += 1
            else:
                with transaction.atomic():
                    existente = ODT.objects.filter(numero=numero).first()
                    datos["contratista"] = existente.contratista if existente else tecnico[:150]
                    odt_sincronizada, creada = ODT.objects.update_or_create(numero=numero, defaults=datos)
                    verificar_sincronizacion(odt_sincronizada)
                if creada:
                    creadas += 1
                else:
                    actualizadas += 1

            if indice % 500 == 0:
                self.stdout.write(
                    f"Procesadas {indice} de {total_registros} ODT..."
                )

                
        # Registrar cuentas nuevas sin modificar las existentes.
        codigos_existentes = set(
            CatalogoCuenta.objects.filter(
                codigo_cuenta__in=cuentas_nuevas
            ).values_list("codigo_cuenta", flat=True)
        )

        cuentas_para_crear = [
            CatalogoCuenta(
                codigo_cuenta=codigo,
                tipo_cliente="SIN_CLASIFICAR",
                requiere_revision_ceco=True,
            )
            for codigo in cuentas_nuevas
            if codigo not in codigos_existentes
        ]

        if not simular:
            CatalogoCuenta.objects.bulk_create(
                cuentas_para_crear, ignore_conflicts=True, batch_size=500,
            )

        self.stdout.write(
            f"Cuentas nuevas detectadas: {len(cuentas_para_crear)}"
        )


        if simular:
            self.stdout.write(self.style.WARNING("SIMULACIÓN: no se guardaron cambios."))
        self.stdout.write(
            self.style.SUCCESS(
                "\nResumen de sincronización.\n"
                f"ODT consultadas: {total_registros}\n"
                f"ODT creadas: {creadas}\n"
                f"ODT actualizadas: {actualizadas}\n"
                f"ODT omitidas: {omitidas}"
            )
        )
