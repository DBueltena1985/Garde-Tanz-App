from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from mitglieder.models import Taenzerin


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an die Eltern, deren Kinder seit mehr "
        "als 90 Tagen keine bestätigten Stammdaten haben (oder noch nie). "
        "Für den echten Betrieb einmal täglich per Cron ausführen."
    )

    def handle(self, *args, **options):
        angeschrieben = 0
        for kind in Taenzerin.objects.select_related("eltern").filter(eltern__is_active=True):
            if not kind.bestaetigung_faellig:
                continue

            eltern = kind.eltern
            if not eltern.email:
                self.stdout.write(self.style.WARNING(
                    f"{eltern.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                ))
                continue

            send_mail(
                subject=f"Bitte Stammdaten von {kind.vorname} bestätigen – Garde Tanz",
                message=(
                    f"Hallo {eltern.first_name or eltern.username},\n\n"
                    f"bitte prüfe und bestätige die Stammdaten von {kind.vorname} "
                    "(Notfallkontakt, Schuhgröße, Allergien etc.) in der Garde-Tanz-App.\n\n"
                    "Das dauert nur eine Minute – auch wenn sich nichts geändert hat, "
                    "bitte einmal speichern, um zu bestätigen."
                ),
                from_email=None,
                recipient_list=[eltern.email],
            )
            angeschrieben += 1

        self.stdout.write(self.style.SUCCESS(f"{angeschrieben} Erinnerungs-Mail(s) verschickt."))
