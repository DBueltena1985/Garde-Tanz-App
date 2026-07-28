from django.db import migrations


def auf_team_only_zuruecksetzen(apps, schema_editor):
    Aufgabe = apps.get_model("mitglieder", "Aufgabe")
    Aufgabe.objects.filter(nur_team=False).update(nur_team=True)


def keine_umkehrung_moeglich(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mitglieder', '0022_alter_aufgabe_nur_team'),
    ]

    operations = [
        migrations.RunPython(auf_team_only_zuruecksetzen, keine_umkehrung_moeglich),
    ]
