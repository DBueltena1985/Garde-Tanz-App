from collections import defaultdict

from django.core.management.base import BaseCommand

from mitglieder.models import Aufgabe
from mitglieder.utils import sichere_mail_senden


class Command(BaseCommand):
    help = (
        "Verschickt eine Erinnerungs-Mail an alle Benutzer mit offenen, ihnen zugewiesenen "
        "ToDo's (Aufgaben). Fuer den echten Betrieb einmal woechentlich per Cron ausfuehren - "
        "solange ToDo's offen sind, wird bei jedem Lauf erneut erinnert."
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

        aufgaben = Aufgabe.objects.filter(
            zugewiesen_an__isnull=False, zugewiesen_an__is_active=True, erledigt=False,
        ).select_related("zugewiesen_an", "termin").order_by("faellig_am")

        nach_user = defaultdict(list)
        for aufgabe in aufgaben:
            nach_user[aufgabe.zugewiesen_an].append(aufgabe)

        angeschrieben = 0
        for user, offene_aufgaben in nach_user.items():
            if not user.email:
                self.stdout.write(self.style.WARNING(
                    f"{user.username}: keine E-Mail-Adresse hinterlegt, übersprungen."
                ))
                continue

            zeilen = []
            for aufgabe in offene_aufgaben:
                zeile = f"- {aufgabe.titel}"
                if aufgabe.termin:
                    zeile += f" ({aufgabe.termin.titel})"
                if aufgabe.faellig_am:
                    zeile += f" – fällig am {aufgabe.faellig_am:%d.%m.%Y}"
                    if aufgabe.ueberfaellig:
                        zeile += " – überfällig"
                zeilen.append(zeile)
            aufgaben_liste = "\n".join(zeilen)

            if trockenlauf:
                self.stdout.write(f"[würde senden] {user.email}: {len(offene_aufgaben)} offene ToDo(s)")
            else:
                sichere_mail_senden(
                    subject=f"{len(offene_aufgaben)} offene ToDo(s) – Garde Tanz",
                    message=(
                        f"Hallo,\n\n"
                        f"folgende ToDo's sind dir noch zugewiesen und offen:\n\n"
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
