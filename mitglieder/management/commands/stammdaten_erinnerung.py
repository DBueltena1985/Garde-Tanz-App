from django.core.management.base import BaseCommand

from mitglieder.models import Taenzerin
from mitglieder.utils import eltern_emails_fuer_kind, sichere_mail_senden


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an alle Eltern/Mitverwalter, deren Kinder seit mehr "
        "als 90 Tagen keine bestätigten Stammdaten haben (oder noch nie). "
        "Für den echten Betrieb einmal täglich per Cron ausführen."
    )

    def handle(self, *args, **options):
        angeschrieben = 0
        kinder = Taenzerin.objects.select_related("eltern").filter(eltern__is_active=True).prefetch_related(
            "mitverwaltet_von"
        )
        for kind in kinder:
            if not kind.bestaetigung_faellig:
                continue

            empfaenger = eltern_emails_fuer_kind(kind)
            if not empfaenger:
                self.stdout.write(self.style.WARNING(
                    f"{kind.eltern.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                ))
                continue

            for email in empfaenger:
                sichere_mail_senden(
                    subject=f"Bitte Stammdaten von {kind.vorname} bestätigen – Garde Tanz",
                    message=(
                        f"Hallo,\n\n"
                        f"bitte prüfe und bestätige die Stammdaten von {kind.vorname} "
                        "(Notfallkontakt, Schuhgröße, Allergien etc.) in der Garde-Tanz-App.\n\n"
                        "Das dauert nur eine Minute – auch wenn sich nichts geändert hat, "
                        "bitte einmal speichern, um zu bestätigen."
                    ),
                    from_email=None,
                    recipient_list=[email],
                )
            angeschrieben += 1

        self.stdout.write(self.style.SUCCESS(f"{angeschrieben} Kind(er) mit Erinnerungs-Mail(s) angeschrieben."))
