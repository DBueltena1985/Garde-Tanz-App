from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

TRAINERTEAM_GRUPPENNAME = "Trainerteam"


class Command(BaseCommand):
    help = (
        "Legt die Gruppe 'Trainerteam' an (falls noch nicht vorhanden) und weist ihr alle aktuell "
        "vorhandenen Berechtigungen zu - volle Rechte zum Eintragen/Bearbeiten ueberall im Admin, "
        "aber ohne Superuser-Status. Erneut ausfuehren, wenn neue Modelle/Berechtigungen dazugekommen "
        "sind, damit die Gruppe wieder alle Berechtigungen hat."
    )

    def handle(self, *args, **options):
        gruppe, erstellt = Group.objects.get_or_create(name=TRAINERTEAM_GRUPPENNAME)
        alle_berechtigungen = Permission.objects.all()
        gruppe.permissions.set(alle_berechtigungen)
        self.stdout.write(self.style.SUCCESS(
            f"Gruppe '{TRAINERTEAM_GRUPPENNAME}' {'angelegt' if erstellt else 'aktualisiert'} mit "
            f"{alle_berechtigungen.count()} Berechtigungen."
        ))
