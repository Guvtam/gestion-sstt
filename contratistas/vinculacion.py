"""Propuestas sobre nombres sincronizados, sin modificar ODT ni pagos."""
import re
from difflib import SequenceMatcher
from django.db import transaction
from django.db.models import Q
from revisiones.models import ODT
from .models import Contratista, EquivalenciaSoftGuard
from .utils import normalizar_nombre


def clave_identidad(nombre):
    return re.sub(r"^T\.?\s*EXTERNO\s*-?\s*", "", normalizar_nombre(nombre)).strip()


def propuestas_vinculacion():
    contratistas = list(Contratista.objects.filter(activo=True))
    equivalencias = set(EquivalenciaSoftGuard.objects.values_list("clave_normalizada", flat=True))
    # Nombres manuales antiguos también reservan su propietario, incluso inactivo.
    reservas = {}
    for pk, nombre in Contratista.objects.exclude(nombre_softguard="").values_list("pk", "nombre_softguard"):
        reservas.setdefault(normalizar_nombre(nombre), set()).add(pk)
    nombres = ODT.objects.filter(
        Q(tecnico__istartswith="T. EXTERNO") | Q(tecnico__istartswith="T EXTERNO")
    ).exclude(tecnico="").order_by("tecnico").values_list("tecnico", flat=True).distinct()
    resultado, vistos = [], set()
    for nombre in nombres:
        clave = normalizar_nombre(nombre)
        if clave in equivalencias or clave in vistos:
            continue
        vistos.add(clave)
        identidad = clave_identidad(nombre)
        exactos, sugeridos = [], []
        for c in contratistas:
            identidades = {clave_identidad(n) for n in (c.nombre, c.nombre_empresa, c.nombre_softguard) if n}
            if identidad and identidad in identidades:
                exactos.append(c)
            elif identidad:
                tokens = set(identidad.split())
                puntuacion = max((SequenceMatcher(None, identidad, n).ratio() for n in identidades), default=0)
                parcial = any(len(tokens) >= 2 and tokens <= set(n.split()) for n in identidades)
                if parcial or puntuacion >= .65:
                    sugeridos.append((puntuacion, c))
        reservados = reservas.get(clave, set())
        conflicto = bool(reservados and (len(exactos) != 1 or reservados != {exactos[0].pk}))
        automatico = len(exactos) == 1 and not conflicto
        candidatos = exactos or [c for _, c in sorted(sugeridos, key=lambda x: (-x[0], x[1].pk))[:5]]
        resultado.append({
            "nombre": nombre, "clave": clave, "automatico": automatico,
            "estado": "Exacta" if automatico else "Ambigua" if len(exactos) > 1 or conflicto else "Sugerencia" if candidatos else "Sin coincidencia",
            "candidatos": candidatos, "reservado": conflicto,
        })
    return resultado


def guardar_propuesta(nombre, contratista_id, solo_exacta=False):
    """Revalidar en cada POST; nunca reemplazar una equivalencia."""
    with transaction.atomic():
        # Serializar acciones de este flujo sobre el catálogo.
        list(Contratista.objects.select_for_update().values_list("pk", flat=True))
        clave = normalizar_nombre(nombre)
        existente = EquivalenciaSoftGuard.objects.filter(clave_normalizada=clave).first()
        if existente:
            return False
        propuesta = next((p for p in propuestas_vinculacion() if p["nombre"] == nombre), None)
        if not propuesta or propuesta["reservado"]:
            raise ValueError("El técnico cambió o tiene una asociación previa. Actualiza la página.")
        permitidos = {c.pk for c in propuesta["candidatos"]}
        if contratista_id not in permitidos or (solo_exacta and not propuesta["automatico"]):
            raise ValueError("La asociación ya no coincide con la propuesta. Actualiza la página.")
        EquivalenciaSoftGuard.objects.create(contratista_id=contratista_id, nombre_softguard=nombre)
        return True


def aplicar_exactas():
    cantidad = 0
    for propuesta in propuestas_vinculacion():
        if propuesta["automatico"]:
            cantidad += guardar_propuesta(propuesta["nombre"], propuesta["candidatos"][0].pk, solo_exacta=True)
    return cantidad
