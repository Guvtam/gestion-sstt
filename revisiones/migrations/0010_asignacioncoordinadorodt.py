from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("revisiones", "0009_correccionodt_eventocorreccionodt"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="AsignacionCoordinadorODT",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("usuario_coordinador", models.CharField(max_length=50)),
                ("asignado_en", models.DateTimeField(auto_now_add=True)),
                ("asignado_por", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("odt", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="asignacion_coordinador", to="revisiones.odt")),
            ],
        ),
    ]
