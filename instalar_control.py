
from pathlib import Path
import shutil, re, sys
BASE=Path.cwd(); APP=BASE/'revisiones'
if not (BASE/'manage.py').exists() or not (APP/'models.py').exists():
    sys.exit('ERROR: Ejecuta este script desde la carpeta que contiene manage.py')
SOURCE=Path(__file__).resolve().parent
changes={}
def stage(path, old, new, label, count=1):
    if old not in changes: changes[old]=None
    data=path.read_text(encoding='utf-8-sig')
    if data.count(old)!=count: raise RuntimeError(f'{label}: se esperaban {count} coincidencias y hay {data.count(old)}; no se cambió nada')
    return data.replace(old,new,count)
def replace_file(path, content):
    if path.exists(): shutil.copy2(path,str(path)+'.bak_control')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content,encoding='utf-8')
try:
    models=APP/'models.py'; s=models.read_text(encoding='utf-8-sig')
    if 'class CorreccionODT(' in s: raise RuntimeError('Ya existe CorreccionODT en models.py; no se instalará de nuevo')
    s+='''\n\nclass CorreccionODT(models.Model):
    ESTADOS = [("PENDIENTE", "Pendiente"), ("EN_PROCESO", "En proceso"), ("ACTUALIZADA", "Actualizada")]
    odt = models.OneToOneField(ODT, on_delete=models.PROTECT, related_name="seguimiento_correccion")
    estado = models.CharField(max_length=20, choices=ESTADOS, default="PENDIENTE", db_index=True)
    servicio_objetivo = models.CharField(max_length=150, blank=True)
    monto_objetivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    corrige_servicio = models.BooleanField(default=False)
    corrige_monto = models.BooleanField(default=False)
    actualizada_en = models.DateTimeField(null=True, blank=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="correcciones_odt_actualizadas")
    gestionado_en = models.DateTimeField(null=True, blank=True)

class EventoCorreccionODT(models.Model):
    odt = models.ForeignKey(ODT, on_delete=models.PROTECT, related_name="eventos_correccion")
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    detalle = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    fecha = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-fecha", "-pk"]
'''
    sync=APP/'management'/'commands'/'sincronizar_odts.py'; t=sync.read_text(encoding='utf-8-sig')
    t=stage(sync,'from revisiones.servicios_sql import consultar_odts_completas','from revisiones.servicios_sql import consultar_odts_completas\nfrom revisiones.correcciones import verificar_sincronizacion','import sincronización')
    t=stage(sync,'_, creada = ODT.objects.update_or_create(numero=numero, defaults=datos)','odt_sincronizada, creada = ODT.objects.update_or_create(numero=numero, defaults=datos)\n                    verificar_sincronizacion(odt_sincronizada)','verificar sincronización')
    views=APP/'views.py'; v=views.read_text(encoding='utf-8-sig')
    v=stage(views,'from .models import ODT, Revision, EventoRevision, CatalogoCuenta','from .models import ODT, Revision, EventoRevision, CatalogoCuenta, CorreccionODT, EventoCorreccionODT\nfrom .correcciones import registrar_cambio_manual','imports vistas')
    anchor='''        # Solo crear/actualizar revisión cuando cambia'''
    if v.count(anchor)!=1: raise RuntimeError('No se encuentra bloque de guardar_fila esperado')
    v=v.replace(anchor,'        registrar_cambio_manual(odt, request.user)\n\n'+anchor,1)
    start=v.find('def odt_modificadas(request):')
    if start<0: raise RuntimeError('No existe odt_modificadas')
    # Respeta decoradores existentes y reemplaza solo cuerpo de la función.
    end=v.find('\n@login_required',start+1)
    if end<0: end=len(v)
    new_func=(SOURCE/'vista_modificadas.py.txt').read_text(encoding='utf-8')
    v=v[:start]+new_func+v[end:]
    urls=APP/'urls.py'; u=urls.read_text(encoding='utf-8-sig')
    needle='    path(\n        "odt-modificadas/",'
    if u.count(needle)!=1: raise RuntimeError('No se encontró ruta odt-modificadas en urls.py')
    u=u.replace(needle,'    path("odt-modificadas/estado-correccion/", views.cambiar_estado_correccion, name="cambiar_estado_correccion"),\n'+needle,1)
    html=APP/'templates'/'revisiones'/'odt_modificadas.html'
    h=html.read_text(encoding='utf-8-sig')
    if 'estado_correccion' not in h or 'historial_odt' not in h: raise RuntimeError('Instala primero la versión ODT modificadas con estado e historial del paso anterior')
    h=h.replace('''<option value="ACTUALIZADA"''','''<option value="EN_PROCESO" {% if correccion_seleccionada == 'EN_PROCESO' %}selected{% endif %}>En proceso</option>\n            <option value="ACTUALIZADA"''',1)
    old='''<td>{% if r.estado_correccion == 'ACTUALIZADA' %}<span class="estado-correccion estado-actualizada">Actualizada</span>{% else %}<span class="estado-correccion estado-pendiente">Pendiente</span>{% endif %}</td>'''
    new='''<td>
                {% if r.estado_correccion == 'ACTUALIZADA' %}
                  <span class="estado-correccion estado-actualizada">Actualizada</span>
                {% elif perms.revisiones.editar_odt_sstt %}
                  <select class="selector-correccion" data-numero="{{ r.numero }}" aria-label="Estado de corrección ODT {{ r.numero }}">
                    <option value="PENDIENTE" {% if r.estado_correccion == 'PENDIENTE' %}selected{% endif %}>Pendiente</option>
                    <option value="EN_PROCESO" {% if r.estado_correccion == 'EN_PROCESO' %}selected{% endif %}>En proceso</option>
                  </select>
                {% else %}
                  <span class="estado-correccion">{{ r.estado_correccion }}</span>
                {% endif %}
              </td>'''
    if h.count(old)!=1: raise RuntimeError('No se encuentra celda estado de corrección esperada en HTML')
    h=h.replace(old,new,1)
    h=h.replace('</style>','''.selector-correccion{min-width:120px;padding:6px;border:1px solid #cbd5e1;border-radius:6px;background:#fff}
    </style>''',1)
    h=h.replace('</body>','''<script>
  document.querySelectorAll('.selector-correccion').forEach(el => {
    el.dataset.anterior = el.value;
    el.addEventListener('change', async () => {
      const anterior = el.dataset.anterior;
      el.disabled = true;
      const body = new URLSearchParams({numero: el.dataset.numero, estado: el.value});
      try {
        const response = await fetch("{% url 'cambiar_estado_correccion' %}", {
          method: 'POST', credentials: 'same-origin',
          headers: {'X-CSRFToken': '{{ csrf_token }}', 'Content-Type': 'application/x-www-form-urlencoded'},
          body: body.toString()
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw Error(data.error || 'No se pudo guardar');
        el.dataset.anterior = data.estado;
        if (data.estado === 'ACTUALIZADA') location.reload();
      } catch(err) {el.value = anterior; alert(err.message);}
      finally {el.disabled = false;}
    });
  });
</script>
</body>''',1)
    # Check before any write
    for path, content in [(models,s),(sync,t),(views,v),(urls,u),(html,h)]: replace_file(path,content)
    if (SOURCE/'revisiones'/'correcciones.py').resolve() != (APP/'correcciones.py').resolve():
        shutil.copy2(SOURCE/'revisiones'/'correcciones.py',APP/'correcciones.py')
    if (SOURCE/'revisiones'/'management'/'commands'/'inicializar_correcciones.py').resolve() != (APP/'management'/'commands'/'inicializar_correcciones.py').resolve():
        shutil.copy2(SOURCE/'revisiones'/'management'/'commands'/'inicializar_correcciones.py',APP/'management'/'commands'/'inicializar_correcciones.py')
    print('OK: archivos actualizados. Respaldo .bak_control para cada archivo modificado.')
    print('SIGUIENTE: python manage.py makemigrations revisiones && python manage.py migrate')
except Exception as exc:
    sys.exit(f'NO SE INSTALÓ: {exc}')
