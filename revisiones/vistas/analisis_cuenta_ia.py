"""Piloto: antecedentes locales y envío externo confirmado por POST con CSRF."""
import json
import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..acceso_coordinadores import es_coordinador_sstt
from ..casos_uso.analisis_cuenta_ia import preparar
from ..dominio.analisis_cuenta_ia import AnalisisNoDisponible, huella, validar_resultado
from ..integraciones.ia_cuentas import solicitar_analisis

SALT = 'sstt.ia.cuenta.v1'


def puede_analizar(user):
    return (user.is_authenticated and user.is_active and not es_coordinador_sstt(user)
            and user.has_perms(('revisiones.ver_bandeja_sstt', 'revisiones.revisar_pago_sstt',
                                'revisiones.ver_historial_sstt'))
            and (user.is_superuser or user.groups.filter(name='Supervisor').exists()))


def configuracion():
    habilitada = str(getattr(settings,'SSTT_IA_HABILITADA',os.getenv('SSTT_IA_HABILITADA','0'))).lower() in ('1','true')
    clave = getattr(settings,'SSTT_OPENAI_API_KEY',os.getenv('SSTT_OPENAI_API_KEY',''))
    modelo = getattr(settings,'SSTT_OPENAI_MODEL',os.getenv('SSTT_OPENAI_MODEL',''))
    segura = len(settings.SECRET_KEY) >= 40 and not settings.DEBUG
    return habilitada and bool(clave) and bool(modelo) and segura, clave, modelo


@login_required
@require_http_methods(['GET','POST'])
def analisis_cuenta_ia(request):
    if not puede_analizar(request.user):
        raise PermissionDenied('La prueba de IA está habilitada solo para administrador y supervisor autorizados.')
    hoy = timezone.localdate()
    entrada = request.POST if request.method == 'POST' else request.GET
    contexto = {'codigo':entrada.get('codigo','').strip().upper(),
                'desde':entrada.get('desde') or hoy.replace(month=1,day=1).isoformat(),
                'hasta':entrada.get('hasta') or hoy.isoformat(), 'titulo':'Análisis de atenciones de una cuenta'}
    lista, clave, modelo = configuracion()
    contexto['ia_disponible'] = lista
    if request.method == 'POST':
        try:
            accion = entrada.get('accion','')
            if accion not in ('preparar','analizar'):
                raise AnalisisNoDisponible('Selecciona una acción válida.')
            if accion == 'analizar':
                if not lista:
                    raise AnalisisNoDisponible('El envío a IA está desactivado o la configuración no está completa. Puedes preparar los antecedentes sin API.')
                if entrada.get('confirmar_envio') != 'SI':
                    raise AnalisisNoDisponible('Revisa los antecedentes y confirma que están autorizados para enviarse al proveedor.')
                try:
                    token = signing.loads(entrada.get('confirmacion',''),salt=SALT,max_age=900)
                except (signing.BadSignature,TypeError,ValueError):
                    raise AnalisisNoDisponible('La revisión venció o no es válida. Prepara nuevamente los antecedentes.') from None
                if (not isinstance(token,dict) or token.get('usuario') != str(request.user.pk)
                    or any(token.get(k) != contexto[k] for k in ('codigo','desde','hasta'))):
                    raise AnalisisNoDisponible('La selección cambió. Prepara nuevamente los antecedentes.')
            preparada = preparar(contexto['codigo'],contexto['desde'],contexto['hasta'])
            contexto.update(preparada)
            datos = preparada['datos']
            if accion == 'analizar' and token.get('huella') != huella(datos):
                raise AnalisisNoDisponible('Los antecedentes cambiaron desde la revisión. Prepara y revisa nuevamente antes de enviar.')
            contexto['vista_previa'] = json.dumps(datos,ensure_ascii=False,indent=2)
            contexto['confirmacion'] = signing.dumps({'usuario':str(request.user.pk),
                **{k:contexto[k] for k in ('codigo','desde','hasta')},'huella':huella(datos)}, salt=SALT,compress=True)
            if accion == 'analizar':
                contexto['hallazgos'] = validar_resultado(solicitar_analisis(datos,clave=clave,modelo=modelo),datos)
                contexto['generado_en'] = timezone.now()
        except AnalisisNoDisponible as error:
            contexto['error'] = str(error)
    return render(request,'revisiones/analisis_cuenta_ia.html',contexto)
