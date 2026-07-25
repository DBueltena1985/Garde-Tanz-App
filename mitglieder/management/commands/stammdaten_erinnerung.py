from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an alle Mitglieder, deren Stammdaten "
        "seit mehr als 90 Tagen nicht bestätigt wurden (oder noch nie). "
        "Für den echten Betrieb einmal täglich per Cron ausführen."
    )

    def handle(self, *args, **options):
        angeschrieben = 0
        for user in User.objects.filter(is_active=True).select_related("profil"):
            if not hasattr(user, "profil"):
                continue
            if not user.profil.bestaetigung_faellig:
                continue
            if not user.email:
                self.stdout.write(self.style.WARNING(
                    f"{user.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                ))
                continue

            send_mail(
                subject="Bitte Stammdaten bestätigen – Garde Tanz",
                message=(
                    f"Hallo {user.first_name or user.username},\n\n"
                    "bitte prüfe und bestätige deine Stammdaten (Notfallkontakt, "
                    "Schuhgröße, Allergien etc.) in der Garde-Tanz-App.\n\n"
                    "Das dauert nur eine Minute – auch wenn sich nichts geändert hat, "
                    "bitte einmal speichern, um zu bestätigen."
                ),
                from_email=None,
                recipient_list=[user.email],
            )
            angeschrieben += 1

        self.stdout.write(self.style.SUCCESS(f"{angeschrieben} Erinnerungs-Mail(s) verschickt."))
