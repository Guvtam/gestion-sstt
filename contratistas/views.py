from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Contratista, EquivalenciaSoftGuard
from .forms import ContratistaForm, EquivalenciaForm

@login_required
@permission_required("contratistas.gestionar_contratistas_sstt", raise_exception=True)
def listado(request):
    q = request.GET.get("q", "").strip()
    qs = Contratista.objects.prefetch_related("equivalencias").all()
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(nombre_empresa__icontains=q) | Q(rut__icontains=q) | Q(nombre_softguard__icontains=q) | Q(equivalencias__nombre_softguard__icontains=q)).distinct()
    pagina = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "contratistas/listado.html", {"pagina": pagina, "q": q})

@login_required
@permission_required("contratistas.gestionar_contratistas_sstt", raise_exception=True)
def editar(request, pk=None):
    objeto = get_object_or_404(Contratista, pk=pk) if pk else None
    if request.method == "POST":
        form = ContratistaForm(request.POST, instance=objeto)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.actualizado_por = request.user
            registro.save()
            messages.success(request, "Contratista guardado correctamente")
            return redirect("contratistas:listado")
    else:
        form = ContratistaForm(instance=objeto)
    return render(request, "contratistas/editar.html", {"form": form, "objeto": objeto})


@login_required
@permission_required("contratistas.gestionar_contratistas_sstt", raise_exception=True)
def equivalencias(request, pk):
    from django.db import IntegrityError, transaction
    from .utils import normalizar_nombre
    contratista = get_object_or_404(Contratista, pk=pk)
    # Catálogo real de nombres registrados en las ODT importadas de SoftGuard.
    from revisiones.models import ODT
    nombres_softguard = list(
        ODT.objects.exclude(tecnico__isnull=True)
        .exclude(tecnico="")
        .filter(Q(tecnico__istartswith="T. EXTERNO") | Q(tecnico__istartswith="T EXTERNO"))
        .order_by("tecnico")
        .values_list("tecnico", flat=True)
        .distinct()
    )
    claves_asignadas = set(EquivalenciaSoftGuard.objects.values_list("clave_normalizada", flat=True))
    disponibles = [n for n in nombres_softguard if normalizar_nombre(n) not in claves_asignadas]
    if request.method == "POST":
        form = EquivalenciaForm(request.POST)
        if form.is_valid():
            nombre = form.cleaned_data["nombre_softguard"]
            if nombre not in nombres_softguard:
                form.add_error("nombre_softguard", "Selecciona un técnico válido de la lista SoftGuard.")
                nombre = None
            clave = normalizar_nombre(nombre) if nombre else ""
            existente = EquivalenciaSoftGuard.objects.filter(clave_normalizada=clave).first()
            if existente:
                form.add_error("nombre_softguard", "Este nombre ya está asociado a otro contratista o al mismo registro.")
            elif nombre:
                try:
                    with transaction.atomic():
                        EquivalenciaSoftGuard.objects.create(contratista=contratista, nombre_softguard=nombre)
                except IntegrityError:
                    form.add_error("nombre_softguard", "La equivalencia ya existe.")
                else:
                    messages.success(request, "Equivalencia agregada correctamente")
                    return redirect("contratistas:equivalencias", pk=pk)
    else:
        form = EquivalenciaForm()
    return render(request, "contratistas/equivalencias.html", {
        "contratista": contratista, "form": form,
        "equivalencias": contratista.equivalencias.all(),
        "tecnicos_disponibles": disponibles,
        "total_tecnicos_softguard": len(nombres_softguard),
    })


@login_required
@permission_required("contratistas.gestionar_contratistas_sstt", raise_exception=True)
@require_POST
def eliminar_equivalencia(request, pk, equivalencia_id):
    contratista = get_object_or_404(Contratista, pk=pk)
    get_object_or_404(EquivalenciaSoftGuard, pk=equivalencia_id, contratista=contratista).delete()
    messages.success(request, "Equivalencia eliminada")
    return redirect("contratistas:equivalencias", pk=pk)
