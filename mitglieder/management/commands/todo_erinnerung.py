from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from mitglieder.models import Aufgabe
from mitglieder.utils import sichere_mail_senden

VORLAUF_TAGE = (7, 1)


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an Benutzer mit einem zugewiesenen, offenen ToDo "
        f"(Aufgabe), dessen Faellig-am-Datum genau {' bzw. '.join(str(t) for t in VORLAUF_TAGE)} "
        "Tag(e) in der Zukunft liegt. ToDo's ohne Faellig-am-Datum werden nicht erinnert. "
        "Fuer den echten Betrieb TAEGLICH per Cron ausfuehren, da die Vorlauf-Tage nur an genau "
        "einem Tag zutreffen."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Nur anzeigen, was verschickt werden wuerde, ohne tatsaechlich Mails zu senden.",
        )

    def handle(self, *args, **options):
        trockenlauf = options["dry_run"]
        if trockenlauf:
            self.stdout.write(self.style.WARNING("Trockenlauf - es werden KEINE Mails versendet.\n"))

        heute = timezone.localdate()
        zieltage = [heute + timedelta(days=tage) for tage in VORLAUF_TAGE]

        aufgaben = Aufgabe.objects.filter(
            zugewiesen_an__isnull=False, zugewiesen_an__is_active=True, erledigt=False,
            faellig_am__in=zieltage,
        ).select_related("zugewiesen_an", "termin").order_by("faellig_am")

        nach_user = defaultdict(list)
        for aufgabe in aufgaben:
            nach_user[aufgabe.zugewiesen_an].append(aufgabe)

        angeschrieben = 0
        for user, faellige_aufgaben in nach_user.items():
            if not user.email:
                self.stdout.write(self.style.WARNING(
                    f"{user.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                ))
                continue

            zeilen = []
            for aufgabe in faellige_aufgaben:
                tage_bis_faellig = (aufgabe.faellig_am - heute).days
                zeile = f"- {aufgabe.titel}"
                if aufgabe.termin:
                    zeile += f" ({aufgabe.termin.titel})"
                zeile += f" – fällig am {aufgabe.faellig_am:%d.%m.%Y}"
                zeile += " (morgen)" if tage_bis_faellig == 1 else f" (in {tage_bis_faellig} Tagen)"
                zeilen.append(zeile)
            aufgaben_liste = "\n".join(zeilen)

            if trockenlauf:
                self.stdout.write(f"[würde senden] {user.email}: {len(faellige_aufgaben)} bald fällige(s) ToDo(s)")
            else:
                sichere_mail_senden(
                    subject=f"{len(faellige_aufgaben)} ToDo(s) werden bald fällig – Garde Tanz",
                    message=(
                        f"Hallo,\n\n"
                        f"folgende dir zugewiesene ToDo's werden bald fällig:\n\n"
                        f"{aufgaben_liste}\n\n"
                        "In der Garde-Tanz-App unter „Meine Aufgaben“ als erledigt markieren, "
                        "sobald es fertig ist."
                    ),
                    from_email=None,
                    recipient_list=[user.email],
                )
            angeschrieben += 1

        self.stdout.write(self.style.SUCCESS(
            f"{angeschrieben} Benutzer mit Erinnerungs-Mail(s) angeschrieben."
        ))
