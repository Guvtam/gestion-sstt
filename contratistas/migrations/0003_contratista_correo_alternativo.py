from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("contratistas", "0002_equivalenciasoftguard")]
    operations = [
        migrations.AddField(
            model_name="contratista",
            name="correo_alternativo",
            field=models.EmailField(blank=True, max_length=254),
        ),
    ]
