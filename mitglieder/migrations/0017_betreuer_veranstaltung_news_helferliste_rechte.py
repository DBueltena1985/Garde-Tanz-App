from django.db import migrations

CODENAMES = [
    "view_veranstaltungtermin", "add_veranstaltungtermin", "change_veranstaltungtermin",
    "view_anmeldepunkt",
    "view_newspost",
]


def rechte_ergaenzen(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    gruppe = Group.objects.filter(name="Betreuer").first()
    if not gruppe:
        return

    berechtigungen = Permission.objects.filter(
        content_type__app_label="mitglieder", codename__in=CODENAMES
    )
    gruppe.permissions.add(*berechtigungen)


def rechte_entfernen(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    gruppe = Group.objects.filter(name="Betreuer").first()
    if not gruppe:
        return

    berechtigungen = Permission.objects.filter(
        content_type__app_label="mitglieder", codename__in=CODENAMES
    )
    gruppe.permissions.remove(*berechtigungen)


class Migration(migrations.Migration):

    dependencies = [
        ("mitglieder", "0016_seed_ferien_2026_2027"),
    ]

    operations = [
        migrations.RunPython(rechte_ergaenzen, rechte_entfernen),
    ]
