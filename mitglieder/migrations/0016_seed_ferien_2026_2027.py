from datetime import date

from django.db import migrations

# Offizielle Termine laut km.bayern.de (Bayerisches Ministerialblatt 2022 Nr. 747).
# Künftige Schuljahre bitte manuell im Admin unter "Ferienzeiträume (Bayern)" ergänzen.
FERIEN = [
    ("Sommerferien 2026", date(2026, 8, 3), date(2026, 9, 14)),
    ("Herbstferien 2026", date(2026, 11, 2), date(2026, 11, 6)),
    ("Weihnachtsferien 2026/2027", date(2026, 12, 24), date(2027, 1, 8)),
    ("Frühjahrsferien 2027", date(2027, 2, 8), date(2027, 2, 12)),
    ("Osterferien 2027", date(2027, 3, 22), date(2027, 4, 2)),
    ("Pfingstferien 2027", date(2027, 5, 18), date(2027, 5, 28)),
    ("Sommerferien 2027", date(2027, 8, 2), date(2027, 9, 13)),
]


def seed_ferien(apps, schema_editor):
    Ferienzeitraum = apps.get_model("mitglieder", "Ferienzeitraum")
    for name, start, ende in FERIEN:
        Ferienzeitraum.objects.get_or_create(name=name, defaults={"start_datum": start, "end_datum": ende})


def entferne_ferien(apps, schema_editor):
    Ferienzeitraum = apps.get_model("mitglieder", "Ferienzeitraum")
    Ferienzeitraum.objects.filter(name__in=[name for name, _, _ in FERIEN]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('mitglieder', '0015_ferienzeitraum'),
    ]

    operations = [
        migrations.RunPython(seed_ferien, entferne_ferien),
    ]
