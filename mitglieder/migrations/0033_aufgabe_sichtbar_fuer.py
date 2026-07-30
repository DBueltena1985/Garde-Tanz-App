from django.db import migrations, models


def nur_team_zu_sichtbar_fuer(apps, schema_editor):
    Aufgabe = apps.get_model('mitglieder', 'Aufgabe')
    Aufgabe.objects.filter(nur_team=True).update(sichtbar_fuer='team')
    Aufgabe.objects.filter(nur_team=False).update(sichtbar_fuer='eltern')


def sichtbar_fuer_zu_nur_team(apps, schema_editor):
    Aufgabe = apps.get_model('mitglieder', 'Aufgabe')
    Aufgabe.objects.exclude(sichtbar_fuer='team').update(nur_team=False)
    Aufgabe.objects.filter(sichtbar_fuer='team').update(nur_team=True)


class Migration(migrations.Migration):

    dependencies = [
        ('mitglieder', '0032_taenzerin_nutzer'),
    ]

    operations = [
        migrations.AddField(
            model_name='aufgabe',
            name='sichtbar_fuer',
            field=models.CharField(
                choices=[('team', 'Nur Orga-/Admin-Team'), ('eltern', 'Eltern'), ('taenzerinnen', 'Tänzerinnen')],
                default='team', max_length=20, verbose_name='Sichtbar für',
                help_text='Wer sieht diese Aufgabe im Mitgliederbereich und kann sie übernehmen? '
                'Eltern sehen zusätzlich alle für Tänzerinnen bestimmten Aufgaben, das Orga-/Admin-Team sieht immer alles.',
            ),
        ),
        migrations.RunPython(nur_team_zu_sichtbar_fuer, sichtbar_fuer_zu_nur_team),
        migrations.RemoveField(
            model_name='aufgabe',
            name='nur_team',
        ),
    ]
