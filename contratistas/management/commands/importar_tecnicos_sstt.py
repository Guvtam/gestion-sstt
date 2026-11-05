"""Actualización del maestro de contratistas. Simula salvo --aplicar."""
import re
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contratistas.models import Contratista
from contratistas.utils import normalizar_nombre

CAMPOS = ("nombre", "nombre_empresa", "rut", "fono", "correo", "ciudad",
          "banco", "tipo_cuenta", "numero_cuenta", "categoria")
CAMPOS_ACTUALIZABLES = CAMPOS + ("correo_alternativo",)
ALIAS = {
    "hoja de origen": "nombre", "nombre / nombre factura": "nombre_empresa",
    "teléfono": "fono", "cuenta": "numero_cuenta", "tipo de cuenta": "tipo_cuenta",
    "categoría": "categoria",
}


def rut_normalizado(valor):
    entrada = re.sub(r"^\s*RUT\s*:?\s*", "", str(valor or ""), flags=re.I)
    texto = re.sub(r"[.,\s-]", "", entrada).upper()
    if not re.fullmatch(r"[0-9]{1,8}[0-9K]", texto):
        raise ValueError("RUT inválido")
    cuerpo, dv = texto[:-1], texto[-1]
    numero = 11 - sum(int(d) * (i % 6 + 2) for i, d in enumerate(reversed(cuerpo))) % 11
    esperado = "0" if numero == 11 else "K" if numero == 10 else str(numero)
    if dv != esperado:
        raise ValueError("Dígito verificador inválido")
    return f"{int(cuerpo)}-{dv}"


def clave_nombre(valor):
    return re.sub(r"^T\.?\s*EXTERNO\s*-?\s*", "", normalizar_nombre(valor))


def leer_archivo(ruta):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise CommandError("Instala las dependencias: python -m pip install -r requirements.txt") from exc
    try:
        wb = load_workbook(ruta, read_only=True, data_only=False)
    except Exception as exc:
        raise CommandError("No se pudo abrir el archivo XLSX.") from exc
    try:
        filas = wb.worksheets[0].iter_rows(values_only=True)
        cabecera = next(filas, ())
        headers = [ALIAS.get(str(v or "").strip().lower(), str(v or "").strip().lower()) for v in cabecera]
        if any(c not in headers for c in CAMPOS) or len(set(headers)) != len(headers):
            raise CommandError("Faltan columnas requeridas o hay encabezados duplicados.")
        registros, ruts = [], set()
        for numero, fila in enumerate(filas, 2):
            datos = {k: str(v).strip() if v is not None else "" for k, v in zip(headers, fila) if k in CAMPOS}
            if not any(datos.values()):
                continue
            if any(v.startswith("=") for v in datos.values()):
                raise CommandError(f"Fila {numero}: usa valores, no fórmulas.")
            correo = re.sub(r"^correo\s*:\s*", "", datos.get("correo", ""), flags=re.I)
            correos = [c.strip() for c in correo.split(";") if c.strip()]
            if len(correos) > 2:
                raise CommandError(f"Fila {numero}: admite como máximo dos correos.")
            datos["correo"] = correos[0] if correos else ""
            datos["correo_alternativo"] = correos[1] if len(correos) > 1 else ""
            if not datos.get("nombre"):
                raise CommandError(f"Fila {numero}: falta el nombre.")
            try:
                datos["rut"] = rut_normalizado(datos.get("rut"))
            except ValueError as exc:
                raise CommandError(f"Fila {numero}: {exc}.") from exc
            if datos["rut"] in ruts:
                raise CommandError(f"Fila {numero}: RUT duplicado en el archivo.")
            ruts.add(datos["rut"])
            registros.append((numero, datos))
        if not registros:
            raise CommandError("El archivo no contiene contratistas.")
        return registros
    finally:
        wb.close()


class Command(BaseCommand):
    help = "Actualiza contratistas desde XLSX. Sin --aplicar solo muestra una simulación."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **options):
        registros = leer_archivo(Path(options["archivo"]))
        resumen = Counter()
        # El plan se valida por completo antes de escribir cualquier registro.
        with transaction.atomic():
            existentes = list(Contratista.objects.select_for_update().all())
            por_rut, por_nombre = {}, {}
            for obj in existentes:
                if obj.rut:
                    try:
                        clave = rut_normalizado(obj.rut)
                    except ValueError:
                        clave = None
                    if clave:
                        if clave in por_rut:
                            raise CommandError("Hay RUT equivalentes duplicados en el sistema; corrígelos antes de importar.")
                        por_rut[clave] = obj
                for nombre in (obj.nombre, obj.nombre_empresa):
                    clave = clave_nombre(nombre)
                    if clave:
                        por_nombre.setdefault(clave, set()).add(obj.pk)
            por_pk = {o.pk: o for o in existentes}
            plan, usados = [], set()
            for fila, datos in registros:
                obj = por_rut.get(datos["rut"])
                if obj is None:
                    candidatos = set()
                    for nombre in (datos["nombre"], datos["nombre_empresa"]):
                        candidatos.update(por_nombre.get(clave_nombre(nombre), set()))
                    if len(candidatos) > 1:
                        raise CommandError(f"Fila {fila}: nombre ambiguo; revisa las coincidencias en Administrar contratistas.")
                    if candidatos:
                        obj = por_pk[next(iter(candidatos))]
                        if obj.rut:
                            raise CommandError(f"Fila {fila}: coincide el nombre pero difiere el RUT. No se guardó ningún cambio.")
                if obj and obj.pk in usados:
                    raise CommandError(f"Fila {fila}: dos filas apuntan al mismo contratista.")
                if obj:
                    usados.add(obj.pk)
                nuevo = obj is None
                if nuevo:
                    obj = Contratista(nombre=datos["nombre"])
                cambios = []
                for campo in CAMPOS_ACTUALIZABLES:
                    valor = datos.get(campo, "")
                    # Conservar el nombre usado en SSTT y los datos ausentes del Excel.
                    if not valor or (campo == "nombre" and not nuevo):
                        continue
                    if getattr(obj, campo) != valor:
                        setattr(obj, campo, valor)
                        cambios.append(campo)
                try:
                    obj.full_clean()
                except ValidationError as exc:
                    # No imprimir datos bancarios, correos ni RUT en los logs.
                    raise CommandError(f"Fila {fila}: campos inválidos: {', '.join(exc.message_dict)}.") from exc
                accion = "crear" if nuevo else "actualizar" if cambios else "sin cambios"
                resumen[accion] += 1
                self.stdout.write(f"Fila {fila}: {accion} — {obj.nombre}" +
                                  (f" (campos: {', '.join(cambios)})" if cambios else ""))
                plan.append((obj, nuevo, cambios))
            if options["aplicar"]:
                for obj, nuevo, cambios in plan:
                    if nuevo:
                        obj.save()
                    elif cambios:
                        obj.save(update_fields=cambios + ["actualizado_en"])
        self.stdout.write("APLICADO" if options["aplicar"] else "SIMULACIÓN: no se guardaron cambios")
        self.stdout.write(f"Crear: {resumen['crear']} | Actualizar: {resumen['actualizar']} | Sin cambios: {resumen['sin cambios']}")
