import secrets

from django.db import migrations, models
import django.db.models.deletion


def token_je_zeile_setzen(apps, schema_editor):
    Termin = apps.get_model("mitglieder", "Termin")
    for termin in Termin.objects.all():
        termin.oeffentlicher_token = secrets.token_urlsafe()
        termin.save(update_fields=["oeffentlicher_token"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mitglieder', '0051_trainingsmaterial'),
    ]

    operations = [
        migrations.AddField(
            model_name='anmeldung',
            name='name_ohne_konto',
            field=models.CharField(
                blank=True, max_length=150, verbose_name='Name (ohne Konto)',
                help_text="Nur ausgefüllt bei einer Anmeldung über den öffentlichen WhatsApp-Link ohne App-Konto.",
                default='',
            ),
        ),
        migrations.AlterField(
            model_name='anmeldung',
            name='eltern',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='helfer_anmeldungen', to='auth.user',
                help_text="Leer, falls über den öffentlichen Link ohne Konto eingetragen (siehe 'Name ohne Konto').",
            ),
        ),
        migrations.AddField(
            model_name='termin',
            name='oeffentlicher_token',
            field=models.CharField(default='', max_length=43, blank=True),
            preserve_default=False,
        ),
        migrations.RunPython(token_je_zeile_setzen, noop),
        migrations.AlterField(
            model_name='termin',
            name='oeffentlicher_token',
            field=models.CharField(
                default=secrets.token_urlsafe, max_length=43, unique=True,
                help_text="Für den öffentlichen Link zum Teilen (z.B. per WhatsApp an Eltern ohne App-Konto).",
            ),
        ),
    ]
