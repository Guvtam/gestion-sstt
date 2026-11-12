"""Preparación y validación del piloto IA; no autoriza ni modifica ODT."""
import hashlib
import json
import re
from html import unescape
from html.parser import HTMLParser


class AnalisisNoDisponible(ValueError):
    pass


class TextoVisible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.oculto = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'):
            self.oculto += 1
        if tag in ('br','p','div','li'):
            self.partes.append(' ')
    def handle_endtag(self, tag):
        if tag in ('script','style') and self.oculto:
            self.oculto -= 1
    def handle_data(self, data):
        if not self.oculto:
            self.partes.append(data)


def depurar_texto(valor):
    parser = TextoVisible()
    parser.feed(str(valor or ''))
    texto = unescape(' '.join(parser.partes))
    texto = re.sub(r'(?is)firma\s+en\s+conformidad\s*:.*', '[firma omitida]', texto)
    texto = re.sub(r'https?://\S+|www\.\S+', '[enlace omitido]', texto, flags=re.I)
    texto = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[correo omitido]', texto)
    texto = re.sub(r'\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b', '[identificador omitido]', texto)
    texto = re.sub(r'(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)', '[número omitido]', texto)
    texto = ' '.join(texto.split())
    if len(texto) > 3000:
        return texto[:3000] + ' [texto recortado]'
    return texto


def huella(datos):
    return hashlib.sha256(json.dumps(datos, ensure_ascii=True, sort_keys=True).encode()).hexdigest()


TIPOS = ['problema','solucion','hipotesis','recomendacion','limitacion']
ESQUEMA = {
    'type':'object', 'additionalProperties':False, 'required':['hallazgos'],
    'properties':{'hallazgos':{'type':'array','items':{
        'type':'object','additionalProperties':False,
        'required':['tipo','descripcion','referencias'],
        'properties':{'tipo':{'type':'string','enum':TIPOS},
                      'descripcion':{'type':'string'},
                      'referencias':{'type':'array','items':{'type':'string'}}}}}}
}


def validar_resultado(resultado, datos):
    fuentes = {f['id']: {'numero':o['numero'], **f} for o in datos['odts'] for f in o['fuentes']}
    if not isinstance(resultado, dict) or set(resultado) != {'hallazgos'}:
        raise AnalisisNoDisponible('La respuesta de IA no tiene el formato esperado.')
    hallazgos = resultado['hallazgos']
    if not isinstance(hallazgos, list) or not 1 <= len(hallazgos) <= 30:
        raise AnalisisNoDisponible('La IA no entregó hallazgos verificables.')
    salida = []
    for h in hallazgos:
        if (not isinstance(h,dict) or set(h) != {'tipo','descripcion','referencias'}
            or h['tipo'] not in TIPOS or not isinstance(h['descripcion'], str)
            or not h['descripcion'].strip() or len(h['descripcion']) > 3000
            or not isinstance(h['referencias'],list) or not 1 <= len(h['referencias']) <= 100
            or any(not isinstance(ref,str) or ref not in fuentes for ref in h['referencias'])):
            raise AnalisisNoDisponible('La IA entregó referencias inválidas o incompletas. No se muestra el análisis.')
        salida.append({**h,'evidencias':[fuentes[r] for r in dict.fromkeys(h['referencias'])]})
    return salida
