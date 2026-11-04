import re
from django import forms
from .models import Contratista

class ContratistaForm(forms.ModelForm):
    class Meta:
        model = Contratista
        fields = ["nombre", "nombre_empresa", "rut", "fono", "correo", "ciudad", "banco", "tipo_cuenta", "numero_cuenta", "categoria", "nombre_softguard", "activo"]
        widgets = {"numero_cuenta": forms.PasswordInput(render_value=True, attrs={"autocomplete": "off"})}

    def clean_rut(self):
        rut = re.sub(r"[^0-9Kk]", "", self.cleaned_data.get("rut") or "").upper()
        if not rut:
            return None
        if len(rut) < 2:
            raise forms.ValidationError("RUT inválido")
        cuerpo, dv = rut[:-1], rut[-1]
        suma = sum(int(d)*((i%6)+2) for i,d in enumerate(reversed(cuerpo)))
        calculado = "0123456789K"[11-(suma%11)] if 11-(suma%11)<11 else "0"
        if calculado != dv:
            raise forms.ValidationError("Dígito verificador del RUT inválido")
        return f"{cuerpo}-{dv}"


class EquivalenciaForm(forms.Form):
    nombre_softguard = forms.CharField(max_length=180, label="Nombre exacto en SoftGuard")

    def clean_nombre_softguard(self):
        from .utils import normalizar_nombre
        valor = self.cleaned_data["nombre_softguard"].strip()
        if not normalizar_nombre(valor):
            raise forms.ValidationError("Ingrese un nombre válido")
        return valor
