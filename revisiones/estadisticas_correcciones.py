from collections import defaultdict
from decimal import Decimal
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from django.core.paginator import Paginator
from django.utils import timezone
from .models import CorreccionODT, ODT
from .consultas.carga_coordinadores import resumir_carga, filtrar_periodo_finalizacion
from .dominio.conciliacion_correcciones import monto_seguimiento
from .acceso_coordinadores import coordinadores_en_peticion


@login_required
@permission_required('revisiones.ver_bandeja_sstt', raise_exception=True)
def estadisticas_correcciones(request):
    """Estadísticas por ODT, no por evento histórico; incluye estados actualizados."""
    hoy = timezone.localdate()
    odts_periodo, periodo = filtrar_periodo_finalizacion(ODT.objects.all(), request.GET, hoy=hoy)
    carga = resumir_carga(odts_periodo, request.GET,
        lambda numeros: coordinadores_en_peticion(request, numeros), hoy=hoy, periodo=periodo)
    qs = CorreccionODT.objects.filter(odt__in=odts_periodo).select_related('odt').order_by('odt__numero')
    coordinador_filtro = request.GET.get('coordinador', '').strip()
    estado_filtro = request.GET.get('estado', '').strip()
    tipo_filtro = request.GET.get('tipo', '').strip()
    if estado_filtro in ('PENDIENTE', 'EN_PROCESO', 'ACTUALIZADA'):
        qs = qs.filter(estado=estado_filtro)
    if tipo_filtro == 'MONTO':
        qs = qs.filter(corrige_monto=True, corrige_servicio=False)
    elif tipo_filtro == 'SERVICIO':
        qs = qs.filter(corrige_monto=False, corrige_servicio=True)
    elif tipo_filtro == 'AMBOS':
        qs = qs.filter(corrige_monto=True, corrige_servicio=True)

    def nuevo():
        return {'cantidad': 0, 'solo_monto': 0, 'solo_servicio': 0,
                'ambos': 0, 'monto': 0, 'servicio': 0,
                'pendiente': 0, 'en_proceso': 0, 'actualizada': 0,
                'original': Decimal('0'), 'corregido': Decimal('0'), 'diferencia': Decimal('0')}

    total = nuevo()
    grupos = defaultdict(nuevo)
    nombres = {}
    detalle = []
    responsables = coordinadores_en_peticion(request, qs.values_list("odt__numero", flat=True).iterator())
    for seguimiento in qs.iterator(chunk_size=200):
        odt = seguimiento.odt
        info = responsables[odt.numero]
        usuario = str(info.get('usuario') or 'SIN_IDENTIFICAR')
        nombre = info.get('nombre') or 'Sin identificar'
        nombres[usuario] = nombre
        if coordinador_filtro and coordinador_filtro != usuario:
            continue
        monto_original = odt.valor_pago_tecnico if odt.valor_pago_tecnico is not None else Decimal('0')
        monto_corregido = monto_seguimiento(odt, seguimiento)
        detalle.append({
            "numero": odt.numero,
            "coordinador": nombre,
            "contratista": odt.contratista or odt.tecnico,
            "cuenta": odt.cuenta_completa,
            "tipo": ("Monto y servicio" if seguimiento.corrige_monto and seguimiento.corrige_servicio
                     else "Solo monto" if seguimiento.corrige_monto
                     else "Solo servicio" if seguimiento.corrige_servicio else "Sin cambios pendientes"),
            "estado": {"PENDIENTE": "Pendiente", "EN_PROCESO": "Procesado",
                       "ACTUALIZADA": "Actualizado"}.get(seguimiento.estado, seguimiento.estado),
            "servicio_softguard": odt.servicio,
            "servicio_corregido": seguimiento.servicio_objetivo if seguimiento.corrige_servicio else odt.servicio,
            "monto_softguard": monto_original,
            "monto_corregido": monto_corregido,
            "diferencia": monto_corregido - monto_original,
        })
        # Si la ODT solo corrige servicio, no se cuenta como corrección de monto.
        for destino in (total, grupos[usuario]):
            destino['cantidad'] += 1
            if seguimiento.corrige_monto:
                destino['monto'] += 1
            if seguimiento.corrige_servicio:
                destino['servicio'] += 1
            if seguimiento.corrige_monto and seguimiento.corrige_servicio:
                destino['ambos'] += 1
            elif seguimiento.corrige_monto:
                destino['solo_monto'] += 1
            elif seguimiento.corrige_servicio:
                destino['solo_servicio'] += 1
            destino[seguimiento.estado.lower()] = destino.get(seguimiento.estado.lower(), 0) + 1
            destino['original'] += monto_original
            destino['corregido'] += monto_corregido
            destino['diferencia'] += monto_corregido - monto_original

    filas = [{'usuario': k, 'nombre': nombres.get(k, k), **v} for k, v in grupos.items()]
    filas.sort(key=lambda x: (-x['cantidad'], x['nombre']))
    opciones = sorted([{'usuario': k, 'nombre': v} for k, v in {**carga['opciones'], **nombres}.items()], key=lambda x: x['nombre'])
    pagina_detalle = Paginator(detalle, 50).get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    parametros["carga_desde"] = periodo["desde"]
    parametros["carga_hasta"] = periodo["hasta"]
    if request.GET.get("formato") == "pdf":
        from django.http import HttpResponse, HttpResponseBadRequest
        from .pdf.reportes import pdf_reporte, filtros_texto
        from .vistas.reportes_consulta import moneda
        if periodo['errores']:return HttpResponseBadRequest(" ".join(periodo['errores']))
        if not carga['disponible']:return HttpResponse('No se pudo verificar la carga por coordinador.',status=503)
        if len(detalle)>10000:return HttpResponseBadRequest('Reduce el período: máximo 10.000 ODT por informe.')
        return pdf_reporte('Análisis por coordinador',[
            ('Carga por período de finalización',['Coordinador','Total ODT','Con correcciones'],
             [[f['nombre'],f['cantidad'],f['con_correcciones']] for f in carga['filas']]),
            ('Resumen de correcciones',['Coordinador','ODT','Solo monto','Solo servicio','Ambos','Monto SG','Monto corregido','Diferencia'],
             [[f['nombre'],f['cantidad'],f['solo_monto'],f['solo_servicio'],f['ambos'],moneda(f['original']),moneda(f['corregido']),moneda(f['diferencia'])] for f in filas]),
            ('Detalle completo de correcciones',['ODT','Coordinador','Cuenta','Modificación','Estado','Monto SG','Monto corregido'],
             [[f['numero'],f['coordinador'],f['cuenta'],f['tipo'],f['estado'],moneda(f['monto_softguard']),moneda(f['monto_corregido'])] for f in detalle]),
            ('Servicios del detalle',['ODT','Servicio SoftGuard','Servicio corregido'],
             [[f['numero'],f['servicio_softguard'],f['servicio_corregido']] for f in detalle])],
            filtros_texto(request.GET),'Analisis_coordinadores.pdf')
    return render(request, 'revisiones/estadisticas_correcciones.html', {
        'carga': carga,
        'total': total, 'filas': filas, 'coordinadores': opciones,
        'coordinador_filtro': coordinador_filtro, 'estado_filtro': estado_filtro,
        'tipo_filtro': tipo_filtro,
        'pagina_detalle': pagina_detalle,
        'query_detalle': parametros.urlencode(),
    })
