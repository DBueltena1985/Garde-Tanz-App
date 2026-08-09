from django.core.management.base import BaseCommand

from mitglieder.models import Taenzerin
from mitglieder.utils import benutzer_name, eltern_emails_fuer_kind, sichere_mail_senden, trainer_und_orga_emails


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an Eltern/Mitverwalter, deren Kind noch nicht "
        "ausgefuellte Pflichtfelder hat (z.B. Kleidergroesse, Notfallkontakt), sowie eine "
        "Sammel-Mail ans Trainerinnen-/Orga-Team mit allen betroffenen Kindern. "
        "Fuer den echten Betrieb einmal woechentlich per Cron ausfuehren - solange Daten "
        "fehlen, wird bei jedem Lauf erneut erinnert."
    )

    def handle(self, *args, **options):
        kinder = Taenzerin.objects.select_related("eltern").filter(eltern__is_active=True).prefetch_related(
            "mitverwaltet_von"
        )

        angeschrieben = 0
        offene_kinder = []

        for kind in kinder:
            fehlend = kind.fehlende_pflichtfelder
            if not fehlend:
                continue

            offene_kinder.append((kind, fehlend))

            empfaenger = eltern_emails_fuer_kind(kind)
            if not empfaenger:
                self.stdout.write(self.style.WARNING(
                    f"{kind.eltern.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                ))
                continue

            fehlend_liste = "\n".join(f"- {feld}" for feld in fehlend)
            for email in empfaenger:
                sichere_mail_senden(
                    subject=f"Bitte fehlende Angaben zu {kind.vorname} ergänzen – Garde Tanz",
                    message=(
                        f"Hallo,\n\n"
                        f"bei {kind.vorname} fehlen noch folgende Angaben in der Garde-Tanz-App "
                        "(unter „Meine Kinder“ zu ergänzen):\n\n"
                        f"{fehlend_liste}\n\n"
                        "Bitte einmal kurz nachtragen - danke!"
                    ),
                    from_email=None,
                    recipient_list=[email],
                )
            angeschrieben += 1

        if offene_kinder:
            zusammenfassung = "\n\n".join(
                f"{kind.vorname} {kind.nachname} ({benutzer_name(kind.eltern)}):\n"
                + "\n".join(f"- {feld}" for feld in fehlend)
                for kind, fehlend in offene_kinder
            )
            trainer_emails = trainer_und_orga_emails()
            if trainer_emails:
                sichere_mail_senden(
                    subject=f"{len(offene_kinder)} Kind(er) mit fehlenden Stammdaten",
                    message=(
                        "Bei folgenden Kindern fehlen noch Angaben in den Stammdaten "
                        "(Eltern wurden per Mail erinnert):\n\n"
                        f"{zusammenfassung}"
                    ),
                    from_email=None,
                    recipient_list=list(trainer_emails),
                )

        self.stdout.write(self.style.SUCCESS(
            f"{angeschrieben} Kind(er) mit Erinnerungs-Mail(s) angeschrieben, "
            f"{len(offene_kinder)} Kind(er) insgesamt mit fehlenden Pflichtfeldern."
        ))
