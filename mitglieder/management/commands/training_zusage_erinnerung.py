from django.core.management.base import BaseCommand
from django.utils import timezone

from mitglieder.models import Taenzerin, Termin, Zusage
from mitglieder.utils import eltern_emails_fuer_kind, sichere_mail_senden


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an alle Eltern/Mitverwalter, deren Kind fuer ein "
        "heutiges Training noch nicht zu- oder abgesagt hat. "
        "Fuer den echten Betrieb taeglich um 12:00 Uhr per Cron ausfuehren."
    )

    def handle(self, *args, **options):
        heute = timezone.localdate()
        trainings_heute = Termin.objects.filter(art=Termin.ART_TRAINING, beginn__date=heute)

        angeschrieben = 0
        for training in trainings_heute:
            kinder = Taenzerin.objects.select_related("eltern").filter(eltern__is_active=True).prefetch_related(
                "mitverwaltet_von"
            )
            # "gruppe" ist bei Taenzerin eine berechnete Property (aus dem Geburtsdatum), kein
            # echtes DB-Feld - Filterung muss daher in Python passieren, nicht per .filter().
            if training.gruppe != Termin.GRUPPE_BEIDE:
                kinder = [k for k in kinder if k.gruppe == training.gruppe]

            for kind in kinder:
                zusage = Zusage.objects.filter(taenzerin=kind, termin=training).first()
                if zusage and zusage.status != Zusage.STATUS_OFFEN:
                    continue

                empfaenger = eltern_emails_fuer_kind(kind)
                if not empfaenger:
                    self.stdout.write(self.style.WARNING(
                        f"{kind.eltern.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                    ))
                    continue

                lokal = timezone.localtime(training.beginn)
                for email in empfaenger:
                    sichere_mail_senden(
                        subject=f"Erinnerung: Bitte für {kind.vorname} zum heutigen Training zu-/absagen",
                        message=(
                            f"Hallo,\n\n"
                            f"heute um {lokal:%H:%M} Uhr ist Training. Für {kind.vorname} liegt "
                            "noch keine Zu- oder Absage vor.\n\n"
                            "Bitte in der Garde-Tanz-App eintragen, damit die Planung stimmt."
                        ),
                        from_email=None,
                        recipient_list=[email],
                    )
                angeschrieben += 1

        self.stdout.write(self.style.SUCCESS(f"{angeschrieben} Kind(er) mit Erinnerungs-Mail(s) angeschrieben."))
