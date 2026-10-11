from django.db import migrations, models
from django.utils import timezone


def benoetigt_am_aufteilen(apps, schema_editor):
    """Teilt die bisherige kombinierte Datum+Uhrzeit (in lokaler Zeit) in Datum (benoetigt_am_datum)
    und Beginn-Uhrzeit (benoetigt_von) auf."""
    Anmeldepunkt = apps.get_model('mitglieder', 'Anmeldepunkt')
    for punkt in Anmeldepunkt.objects.exclude(benoetigt_am__isnull=True):
        lokal = timezone.localtime(punkt.benoetigt_am)
        punkt.benoetigt_am_datum = lokal.date()
        punkt.benoetigt_von = lokal.time()
        punkt.save(update_fields=['benoetigt_am_datum', 'benoetigt_von'])


def benoetigt_am_zusammenfuehren(apps, schema_editor):
    """Rueckwaerts: Datum + Uhrzeit-von wieder zu einer kombinierten Datum+Uhrzeit zusammenfuehren."""
    Anmeldepunkt = apps.get_model('mitglieder', 'Anmeldepunkt')
    for punkt in Anmeldepunkt.objects.exclude(benoetigt_am_datum__isnull=True):
        uhrzeit = punkt.benoetigt_von or timezone.datetime.min.time()
        naiv = timezone.datetime.combine(punkt.benoetigt_am_datum, uhrzeit)
        punkt.benoetigt_am = timezone.make_aware(naiv)
        punkt.save(update_fields=['benoetigt_am'])


class Migration(migrations.Migration):

    dependencies = [
        ('mitglieder', '0056_aufgabe_kategorie'),
    ]

    operations = [
        migrations.AddField(
            model_name='anmeldepunkt',
            name='benoetigt_am_datum',
            field=models.DateField(blank=True, null=True, verbose_name='Benötigt am'),
        ),
        migrations.AddField(
            model_name='anmeldepunkt',
            name='benoetigt_von',
            field=models.TimeField(
                blank=True, null=True, verbose_name='Uhrzeit von',
                help_text='Optional: Beginn der Uhrzeit/Schicht. Leer lassen, falls noch keine Uhrzeit feststeht.',
            ),
        ),
        migrations.AddField(
            model_name='anmeldepunkt',
            name='benoetigt_bis',
            field=models.TimeField(
                blank=True, null=True, verbose_name='Uhrzeit bis',
                help_text='Optional: Ende der Uhrzeit/Schicht, falls es z.B. mehrere Schichten an diesem Tag gibt.',
            ),
        ),
        migrations.RunPython(benoetigt_am_aufteilen, benoetigt_am_zusammenfuehren),
        migrations.RemoveField(
            model_name='anmeldepunkt',
            name='benoetigt_am',
        ),
        migrations.RenameField(
            model_name='anmeldepunkt',
            old_name='benoetigt_am_datum',
            new_name='benoetigt_am',
        ),
        migrations.AlterField(
            model_name='anmeldepunkt',
            name='benoetigt_am',
            field=models.DateField(
                blank=True, null=True, verbose_name='Benötigt am',
                help_text='Optional: bei mehrtägigen Terminen, an welchem Tag genau das gebraucht bzw. '
                'abgegeben werden soll (z.B. Frühstück am 2. Tag).',
            ),
        ),
    ]
