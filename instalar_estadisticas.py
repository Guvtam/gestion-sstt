from pathlib import Path
import shutil, sys
base = Path.cwd()
app = base / 'revisiones'
source = Path(__file__).resolve().parent
if not (base/'manage.py').is_file():
    sys.exit('ERROR: ejecuta desde la carpeta de manage.py')
url = app/'urls.py'
html = app/'templates'/'revisiones'/'odt_modificadas.html'
if not url.is_file() or not html.is_file():
    sys.exit('ERROR: faltan urls.py u odt_modificadas.html')
u = url.read_text(encoding='utf-8-sig')
h = html.read_text(encoding='utf-8-sig')
if 'estadisticas_correcciones' in u or 'estadisticas_correcciones' in h:
    sys.exit('ERROR: parece que ya instalaste estadísticas; no se repetirá la instalación')
if 'urlpatterns = [' not in u:
    sys.exit('ERROR: no se encuentra urlpatterns en urls.py')
if 'Facturación' not in h:
    sys.exit('ERROR: no se encuentra botón Facturación en HTML; no se modificó nada')
# Insertar junto a la referencia Facturación, no en otros botones.
import re
m = re.search(r'<a\b[^>]*>\s*Facturación\s*</a>', h, flags=re.I|re.S)
if not m:
    sys.exit('ERROR: botón Facturación no es un enlace <a> esperado; no se modificó nada')
newbutton = ' <a href="{% url \'estadisticas_correcciones\' %}" style="display:inline-block;margin-left:8px;padding:9px 13px;background:#1765b1;color:white;border-radius:5px;text-decoration:none;font-size:12px;font-weight:600">Estadísticas de correcciones</a>'
h = h[:m.end()] + newbutton + h[m.end():]
u = 'from .estadisticas_correcciones import estadisticas_correcciones\n' + u if not u.startswith('from __future__') else u.replace('from __future__ import annotations','from __future__ import annotations\nfrom .estadisticas_correcciones import estadisticas_correcciones',1)
u = u.replace('urlpatterns = [','urlpatterns = [\n    path("odt-modificadas/estadisticas/", estadisticas_correcciones, name="estadisticas_correcciones"),',1)
for p in (url,html):
    shutil.copy2(p, str(p)+'.bak_estadisticas')
for src,dst in [(source/'revisiones'/'estadisticas_correcciones.py',app/'estadisticas_correcciones.py'),(source/'revisiones'/'templates'/'revisiones'/'estadisticas_correcciones.html',app/'templates'/'revisiones'/'estadisticas_correcciones.html')]:
    if dst.exists():
        sys.exit('ERROR: ya existe '+str(dst)+'; no se reemplazará')
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
url.write_text(u,encoding='utf-8')
html.write_text(h,encoding='utf-8')
print('OK: estadísticas instaladas. Respaldos .bak_estadisticas creados.')
print('SIGUIENTE: python manage.py check')
