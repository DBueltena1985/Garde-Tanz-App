import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def zusagen_leeren(apps, schema_editor):
    """Alte Zusagen (nur Testdaten) loeschen, da sie noch am User statt am Kind haengen."""
    Zusage = apps.get_model("mitglieder", "Zusage")
    Zusage.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mitglieder", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Taenzerin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vorname", models.CharField(max_length=100, verbose_name="Vorname")),
                ("nachname", models.CharField(max_length=100, verbose_name="Nachname")),
                ("notfallkontakt_name", models.CharField(blank=True, max_length=200, verbose_name="Notfallkontakt Name")),
                ("notfallkontakt_telefon", models.CharField(blank=True, max_length=50, verbose_name="Notfallkontakt Telefon")),
                ("notfallkontakt_beziehung", models.CharField(blank=True, help_text="z.B. Mutter, Vater, Partner:in", max_length=100, verbose_name="Beziehung zum Notfallkontakt")),
                ("schuhgroesse", models.CharField(blank=True, max_length=10, verbose_name="Schuhgröße")),
                ("allergien", models.TextField(blank=True, verbose_name="Allergien")),
                ("medikamente", models.TextField(blank=True, verbose_name="Medikamente")),
                ("sonstige_hinweise", models.TextField(blank=True, help_text="z.B. Vorerkrankungen, Besonderheiten", verbose_name="Sonstige Hinweise")),
                ("stammdaten_bestaetigt_am", models.DateTimeField(blank=True, null=True, verbose_name="Stammdaten zuletzt bestätigt am")),
                ("eltern", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kinder", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Tänzerin",
                "verbose_name_plural": "Tänzerinnen",
                "ordering": ["vorname", "nachname"],
            },
        ),
        migrations.RunPython(zusagen_leeren, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="zusage",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="zusage",
            name="mitglied",
        ),
        migrations.AddField(
            model_name="zusage",
            name="taenzerin",
            field=models.ForeignKey(default=None, on_delete=django.db.models.deletion.CASCADE, related_name="zusagen", to="mitglieder.taenzerin"),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name="zusage",
            unique_together={("taenzerin", "termin")},
        ),
        migrations.RemoveField(
            model_name="profil",
            name="user",
        ),
        migrations.DeleteModel(
            name="Profil",
        ),
    ]
