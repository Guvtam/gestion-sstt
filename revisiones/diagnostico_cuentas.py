
from collections import Counter

from revisiones.models import ODT, CatalogoCuenta
from revisiones.cuentas_utils import normalizar_codigo_cuenta


catalogo = set(
    CatalogoCuenta.objects.values_list(
        "codigo_cuenta", flat=True
    )
)

resultados = Counter()
ejemplos_sin_codigo = []
ejemplos_fuera_catalogo = []

for cuenta in ODT.objects.values_list(
    "cuenta_completa", flat=True
).iterator():

    codigo = normalizar_codigo_cuenta(cuenta)

    resultados["total"] += 1

    if not codigo:
        resultados["sin_codigo"] += 1

        if len(ejemplos_sin_codigo) < 10:
            ejemplos_sin_codigo.append(cuenta)

    elif codigo in catalogo:
        resultados["en_catalogo"] += 1

    else:
        resultados["fuera_catalogo"] += 1

        if len(ejemplos_fuera_catalogo) < 10:
            ejemplos_fuera_catalogo.append(cuenta)


print("\n=== DIAGNÓSTICO DE CUENTAS SSTT ===")

print("ODT totales:", resultados["total"])
print(
    "Códigos reconocidos:",
    resultados["en_catalogo"] + resultados["fuera_catalogo"]
)
print("En catálogo:", resultados["en_catalogo"])
print("Fuera del catálogo:", resultados["fuera_catalogo"])
print("Sin código reconocible:", resultados["sin_codigo"])

print("\n=== EJEMPLOS SIN CÓDIGO ===")
for cuenta in ejemplos_sin_codigo:
    print(repr(cuenta))

print("\n=== EJEMPLOS FUERA DEL CATÁLOGO ===")
for cuenta in ejemplos_fuera_catalogo:
    print(repr(cuenta))
