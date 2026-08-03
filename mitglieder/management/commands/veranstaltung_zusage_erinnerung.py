from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from mitglieder.models import Taenzerin, Termin, Zusage
from mitglieder.utils import eltern_emails_fuer_kind, sichere_mail_senden

VORLAUF_TAGE = 3


class Command(BaseCommand):
    help = (
        f"Verschickt eine Erinnerungs-Mail an alle Eltern/Mitverwalter, deren Kind fuer eine "
        f"Veranstaltung in {VORLAUF_TAGE} Tagen noch nicht zu- oder abgesagt hat. "
        "Fuer den echten Betrieb taeglich um 12:00 Uhr per Cron ausfuehren."
    )

    def handle(self, *args, **options):
        zieltag = timezone.localdate() + timedelta(days=VORLAUF_TAGE)
        veranstaltungen = Termin.objects.filter(
            art=Termin.ART_VERANSTALTUNG, taenzerinnen_erforderlich=True, beginn__date=zieltag,
        )

        angeschrieben = 0
        for veranstaltung in veranstaltungen:
            kinder = Taenzerin.objects.select_related("eltern").filter(eltern__is_active=True).prefetch_related(
                "mitverwaltet_von"
            )
            # "gruppe" ist bei Taenzerin eine berechnete Property (aus dem Geburtsdatum), kein
            # echtes DB-Feld - Filterung muss daher in Python passieren, nicht per .filter().
            if veranstaltung.gruppe != Termin.GRUPPE_BEIDE:
                kinder = [k for k in kinder if k.gruppe == veranstaltung.gruppe]

            for kind in kinder:
                zusage = Zusage.objects.filter(taenzerin=kind, termin=veranstaltung).first()
                if zusage and zusage.status != Zusage.STATUS_OFFEN:
                    continue

                empfaenger = eltern_emails_fuer_kind(kind)
                if not empfaenger:
                    self.stdout.write(self.style.WARNING(
                        f"{kind.eltern.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                    ))
                    continue

                lokal = timezone.localtime(veranstaltung.beginn)
                for email in empfaenger:
                    sichere_mail_senden(
                        subject=(
                            f"Erinnerung: Bitte für {kind.vorname} zu „{veranstaltung.titel}“ zu-/absagen"
                        ),
                        message=(
                            f"Hallo,\n\n"
                            f"in {VORLAUF_TAGE} Tagen ({lokal:%d.%m.%Y %H:%M} Uhr) findet die "
                            f"Veranstaltung „{veranstaltung.titel}“ statt. Für {kind.vorname} liegt "
                            "noch keine Zu- oder Absage vor.\n\n"
                            "Bitte in der Garde-Tanz-App eintragen, damit die Planung stimmt."
                        ),
                        from_email=None,
                        recipient_list=[email],
                    )
                angeschrieben += 1

        self.stdout.write(self.style.SUCCESS(f"{angeschrieben} Kind(er) mit Erinnerungs-Mail(s) angeschrieben."))
