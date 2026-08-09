from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from mitglieder.models import Profil, Taenzerin
from mitglieder.utils import benutzer_name, eltern_emails_fuer_kind, sichere_mail_senden, trainer_und_orga_emails


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an Eltern/Mitverwalter, deren Kind noch nicht "
        "ausgefuellte Pflichtfelder hat (z.B. Kleidergroesse, Notfallkontakt, Einverstaendnis "
        "Bildaufnahmen), sowie an Benutzer, deren Einverstaendnis Datennutzung im eigenen Konto "
        "noch offen ist (weder erteilt noch abgelehnt). Zusaetzlich eine Sammel-Mail ans "
        "Trainerinnen-/Orga-Team mit allen Betroffenen. Fuer den echten Betrieb einmal "
        "woechentlich per Cron ausfuehren - solange etwas fehlt, wird bei jedem Lauf erneut "
        "erinnert."
    )

    def handle(self, *args, **options):
        angeschrieben, offene_kinder = self._kinder_pruefen()
        offene_konten = self._konten_pruefen()

        if offene_kinder or offene_konten:
            self._trainer_zusammenfassung_senden(offene_kinder, offene_konten)

        self.stdout.write(self.style.SUCCESS(
            f"{angeschrieben} Kind(er) mit Erinnerungs-Mail(s) angeschrieben, "
            f"{len(offene_kinder)} Kind(er) mit fehlenden Pflichtfeldern, "
            f"{len(offene_konten)} Konto/Konten mit offenem Einverständnis Datennutzung."
        ))

    def _kinder_pruefen(self):
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

        return angeschrieben, offene_kinder

    def _konten_pruefen(self):
        """Benutzer, deren Einverstaendnis Datennutzung im eigenen Konto noch offen ist
        (weder erteilt noch abgelehnt) - unabhaengig von etwaigen Kindern."""
        offene_konten = []
        for user in User.objects.filter(is_active=True).exclude(email=""):
            profil, _ = Profil.objects.get_or_create(user=user)
            if profil.einverstanden_datennutzung is not None:
                continue

            offene_konten.append(user)
            sichere_mail_senden(
                subject="Bitte Einverständnis Datennutzung angeben – Garde Tanz",
                message=(
                    f"Hallo,\n\n"
                    "bei deinem Konto in der Garde-Tanz-App steht das Einverständnis zur "
                    "Datennutzung noch aus (weder erteilt noch abgelehnt).\n\n"
                    "Bitte unter „Mein Konto“ kurz Bescheid geben - danke!"
                ),
                from_email=None,
                recipient_list=[user.email],
            )
        return offene_konten

    def _trainer_zusammenfassung_senden(self, offene_kinder, offene_konten):
        trainer_emails = trainer_und_orga_emails()
        if not trainer_emails:
            return

        abschnitte = []
        if offene_kinder:
            kinder_liste = "\n\n".join(
                f"{kind.vorname} {kind.nachname} ({benutzer_name(kind.eltern)}):\n"
                + "\n".join(f"- {feld}" for feld in fehlend)
                for kind, fehlend in offene_kinder
            )
            abschnitte.append(
                "Bei folgenden Kindern fehlen noch Angaben in den Stammdaten "
                f"(Eltern wurden per Mail erinnert):\n\n{kinder_liste}"
            )
        if offene_konten:
            konten_liste = "\n".join(f"- {benutzer_name(user)}" for user in offene_konten)
            abschnitte.append(
                "Folgende Konten haben das Einverständnis Datennutzung noch nicht "
                f"entschieden (wurden per Mail erinnert):\n\n{konten_liste}"
            )

        anzahl = len(offene_kinder) + len(offene_konten)
        sichere_mail_senden(
            subject=f"{anzahl} offene Stammdaten-/Einverständnis-Punkt(e)",
            message="\n\n---\n\n".join(abschnitte),
            from_email=None,
            recipient_list=list(trainer_emails),
        )
