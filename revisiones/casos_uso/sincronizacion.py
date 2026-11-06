"""Sincronización por lotes: campos de origen separados de decisiones SSTT."""
from dataclasses import dataclass, fields, replace

from django.db import DatabaseError, transaction
from django.utils import timezone

from ..correcciones import verificar_sincronizacion
from ..dominio.cuentas import TIPO_CLIENTE_PREDETERMINADO
from ..cuentas_utils import cargar_catalogo_cuentas, normalizar_codigo_cuenta, tipo_cliente_cuenta
from ..integraciones.bloqueo_sync import bloquear_sincronizacion
from ..integraciones.transformacion_odt import RegistroOrigenInvalido, fecha_hora, transformar_registro
from ..models import CatalogoCuenta, CorreccionODT, EjecucionSincronizacion, ODT


@dataclass
class Conteos:
    creadas: int = 0
    actualizadas: int = 0
    sin_cambios: int = 0
    omitidas: int = 0
    cuentas_incorporadas: int = 0


@dataclass
class Resultado(Conteos):
    consultadas: int = 0
    equivalencias_creadas: int = 0
    fecha_carga_origen: object = None
    ejecucion_id: object = None


def _datos_historial(resultado, extra=None):
    datos = {f.name: getattr(resultado, f.name) for f in fields(resultado) if f.name != "ejecucion_id"}
    if extra:
        for campo in fields(Conteos):
            datos[campo.name] += getattr(extra, campo.name)
    return datos


def _aplicar_lote(lote, simular):
    conteos = Conteos()
    validos = {}
    for registro in lote:
        try:
            numero, datos = transformar_registro(registro)
        except RegistroOrigenInvalido:
            conteos.omitidas += 1
            continue
        if numero in validos:
            conteos.omitidas += 1
            continue
        validos[numero] = datos
    if not validos:
        return conteos

    catalogo = cargar_catalogo_cuentas(datos["cuenta_completa"] for datos in validos.values())
    existentes_qs = ODT.objects.all()
    if not simular:
        existentes_qs = existentes_qs.select_for_update()
    existentes = existentes_qs.in_bulk(validos, field_name="numero")
    nuevos, cambios = [], []
    codigos_nuevos = set()
    for numero, datos in validos.items():
        datos["tipo_cliente"] = tipo_cliente_cuenta(datos["cuenta_completa"], catalogo)
        codigo = normalizar_codigo_cuenta(datos["cuenta_completa"])
        if codigo and codigo not in catalogo:
            codigos_nuevos.add(codigo)
        odt = existentes.get(numero)
        if odt is None:
            nuevos.append(ODT(numero=numero, contratista=datos["tecnico"][:150], **datos))
        elif any(getattr(odt, campo) != valor for campo, valor in datos.items()):
            for campo, valor in datos.items():
                setattr(odt, campo, valor)
            cambios.append(odt)
        else:
            conteos.sin_cambios += 1
    conteos.creadas = len(nuevos)
    conteos.actualizadas = len(cambios)
    if simular:
        conteos.cuentas_incorporadas = len(codigos_nuevos)
        return conteos

    ODT.objects.bulk_create(nuevos, batch_size=250)
    if cambios:
        # Solo campos originales y clasificación proyectada; ningún campo manual.
        campos = list(next(iter(validos.values())))
        ODT.objects.bulk_update(cambios, campos, batch_size=250)
    for codigo in sorted(codigos_nuevos):
        _, creada = CatalogoCuenta.objects.get_or_create(codigo_cuenta=codigo, defaults={
            "tipo_cliente": TIPO_CLIENTE_PREDETERMINADO, "requiere_revision_ceco": True,
        })
        conteos.cuentas_incorporadas += int(creada)

    seguimientos = CorreccionODT.objects.select_for_update().in_bulk(
        [o.pk for o in existentes.values()], field_name="odt_id"
    )
    for odt in existentes.values():
        verificar_sincronizacion(odt, seguimiento=seguimientos.get(odt.pk))
    return conteos


def _guardar_lote(lote, resultado, ejecucion, simular):
    if simular:
        delta = _aplicar_lote(lote, True)
    else:
        with transaction.atomic():
            delta = _aplicar_lote(lote, False)
            EjecucionSincronizacion.objects.filter(pk=ejecucion.pk).update(**_datos_historial(resultado, delta))
    for campo in fields(Conteos):
        setattr(resultado, campo.name, getattr(resultado, campo.name) + getattr(delta, campo.name))


def _finalizar(ejecucion, resultado, estado, codigo_error=""):
    ahora = timezone.now()
    EjecucionSincronizacion.objects.filter(pk=ejecucion.pk).update(
        **_datos_historial(resultado), estado=estado, finalizada_en=ahora,
        duracion=ahora-ejecucion.iniciada_en, codigo_error=codigo_error,
    )


def _recuperar_interrumpidas():
    # Solo se llama después de adquirir el bloqueo: no hay otro sync local activo.
    for anterior in EjecucionSincronizacion.objects.filter(estado="EN_CURSO").iterator():
        ahora = timezone.now()
        anterior.estado = "INTERRUMPIDA"
        anterior.finalizada_en = ahora
        anterior.duracion = ahora - anterior.iniciada_en
        anterior.codigo_error = "PROCESO_ANTERIOR_FINALIZADO"
        anterior.save(update_fields=["estado", "finalizada_en", "duracion", "codigo_error"])


def ejecutar_sincronizacion(obtener_registros, *, simular=False, tamano_lote=250, progreso=None):
    if not isinstance(tamano_lote, int) or not 1 <= tamano_lote <= 1000:
        raise ValueError("El tamaño del lote debe estar entre 1 y 1000.")
    with bloquear_sincronizacion():
        resultado = Resultado()
        ejecucion = None
        if not simular:
            _recuperar_interrumpidas()
            ejecucion = EjecucionSincronizacion.objects.create()
            resultado.ejecucion_id = ejecucion.pk
        try:
            registros = obtener_registros()
            try:
                lote = []
                for registro in registros:
                    resultado.consultadas += 1
                    try:
                        carga = fecha_hora(registro.get("FechaCarga"))
                    except (RegistroOrigenInvalido, AttributeError):
                        carga = None
                    if carga and (resultado.fecha_carga_origen is None or carga > resultado.fecha_carga_origen):
                        resultado.fecha_carga_origen = carga
                    lote.append(registro)
                    if len(lote) >= tamano_lote:
                        _guardar_lote(lote, resultado, ejecucion, simular)
                        lote.clear()
                        if progreso:
                            progreso(resultado)
                if lote:
                    _guardar_lote(lote, resultado, ejecucion, simular)
            finally:
                cerrar = getattr(registros, "close", None)
                if cerrar:
                    cerrar()
            if not simular:
                from contratistas.vinculacion import aplicar_exactas
                estado = "CON_OMISIONES" if resultado.omitidas else "COMPLETADA"
                with transaction.atomic():
                    final = replace(resultado, equivalencias_creadas=aplicar_exactas())
                    _finalizar(ejecucion, final, estado)
                resultado = final
            return resultado
        except BaseException as exc:
            if ejecucion is not None:
                estado = "INTERRUMPIDA" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FALLIDA"
                try:
                    _finalizar(ejecucion, resultado, estado, type(exc).__name__[:80])
                except DatabaseError:
                    # Si la base no permite registrar el fallo, queda EN_CURSO y
                    # se recupera como interrumpida al siguiente intento con bloqueo.
                    pass
            raise
