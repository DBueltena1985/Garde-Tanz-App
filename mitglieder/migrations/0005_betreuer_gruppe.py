from django.db import migrations


def betreuer_gruppe_erstellen(apps, schema_editor):
    # Berechtigungen werden normalerweise erst nach allen Migrationen erzeugt (post_migrate-Signal).
    # Hier stossen wir das vorzeitig an, damit wir sie direkt zuweisen koennen.
    from django.contrib.auth.management import create_permissions

    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    gruppe, _ = Group.objects.get_or_create(name="Betreuer")

    codenames = [
        "add_termin", "change_termin",
        "view_taenzerin",
        "add_newspost", "change_newspost",
    ]
    berechtigungen = Permission.objects.filter(
        content_type__app_label="mitglieder", codename__in=codenames
    )
    gruppe.permissions.set(berechtigungen)


def betreuer_gruppe_entfernen(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Betreuer").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mitglieder", "0004_taenzerin_kleidergroesse"),
    ]

    operations = [
        migrations.RunPython(betreuer_gruppe_erstellen, betreuer_gruppe_entfernen),
    ]
