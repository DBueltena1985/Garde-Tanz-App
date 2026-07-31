from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from mitglieder.models import Taenzerin


class Command(BaseCommand):
    help = (
        "Legt ein Demo-Elternkonto mit zwei Demo-Kindern (Jugend & Junioren) an, um die "
        "Mitgliederansicht per 'Als Mitglied ansehen' im Admin zu testen, ohne dass sich "
        "schon echte Eltern registriert haben. Kann mehrfach ausgeführt werden, ohne Duplikate "
        "anzulegen."
    )

    def handle(self, *args, **options):
        eltern, neu_angelegt = User.objects.get_or_create(
            username="demo_eltern",
            defaults={"first_name": "Demo", "last_name": "Eltern"},
        )
        if neu_angelegt:
            eltern.set_unusable_password()
            eltern.save()
            self.stdout.write(self.style.SUCCESS("Demo-Elternkonto 'demo_eltern' angelegt."))
        else:
            self.stdout.write("Demo-Elternkonto 'demo_eltern' existiert bereits.")

        demo_kinder = [
            ("Demo", "Jugend-Kind", 2018),
            ("Demo", "Junioren-Kind", 2012),
        ]
        for vorname, nachname, geburtsjahr in demo_kinder:
            kind, kind_neu_angelegt = Taenzerin.objects.get_or_create(
                eltern=eltern, vorname=vorname, nachname=nachname,
                defaults={"geburtsdatum": date(geburtsjahr, 1, 1)},
            )
            if kind_neu_angelegt:
                self.stdout.write(self.style.SUCCESS(f"Demo-Kind '{vorname} {nachname}' angelegt."))
            else:
                self.stdout.write(f"Demo-Kind '{vorname} {nachname}' existiert bereits.")

        self.stdout.write(self.style.SUCCESS(
            "Fertig. Im Admin unter Benutzer -> 'Demo Eltern' oeffnen und "
            "'Als Mitglied ansehen' klicken."
        ))
