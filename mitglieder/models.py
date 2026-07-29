from django.conf import settings
from django.db import models
from django.utils import timezone


class Taenzerin(models.Model):
    """Ein Kind, das von einem Elternaccount verwaltet wird, inkl. Stammdaten."""

    GRUPPE_JUGEND = "jugend"
    GRUPPE_JUNIOREN = "junioren"
    # Jahrgang 2016 und juenger zaehlt zur Jugend, 2015 und aelter zu den Junioren.
    JUGEND_JAHRGANG_AB = 2016

    eltern = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kinder"
    )
    mitverwaltet_von = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="mitverwaltete_kinder", blank=True,
        verbose_name="Mitverwaltet von",
        help_text="Weitere Benutzer (z.B. Partner:in), die dieses Kind ebenfalls sehen und verwalten dürfen.",
    )

    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsjahr = models.PositiveIntegerField(
        "Geburtsjahr", null=True, blank=True,
        help_text="Bestimmt die Trainingsgruppe (Jugend/Junioren).",
    )

    # Notfallkontakt
    notfallkontakt_name = models.CharField("Notfallkontakt Name", max_length=200, blank=True)
    notfallkontakt_telefon = models.CharField("Notfallkontakt Telefon", max_length=50, blank=True)
    notfallkontakt_beziehung = models.CharField(
        "Beziehung zum Notfallkontakt", max_length=100, blank=True,
        help_text="z.B. Mutter, Vater, Partner:in",
    )

    # Weitere Stammdaten
    schuhgroesse = models.CharField("Schuhgröße", max_length=10, blank=True)
    kleidergroesse = models.CharField("Kleidergröße", max_length=10, blank=True)
    allergien = models.TextField("Allergien", blank=True)
    medikamente = models.TextField("Medikamente", blank=True)
    sonstige_hinweise = models.TextField(
        "Sonstige Hinweise", blank=True,
        help_text="z.B. Vorerkrankungen, Besonderheiten",
    )

    stammdaten_bestaetigt_am = models.DateTimeField(
        "Stammdaten zuletzt bestätigt am", null=True, blank=True
    )

    class Meta:
        verbose_name = "Tänzerin"
        verbose_name_plural = "Tänzerinnen"
        ordering = ["vorname", "nachname"]

    def __str__(self):
        return f"{self.vorname} {self.nachname}"

    @property
    def bestaetigung_faellig(self):
        """True, wenn die Stammdaten noch nie oder vor mehr als 90 Tagen bestätigt wurden."""
        if not self.stammdaten_bestaetigt_am:
            return True
        return (timezone.now() - self.stammdaten_bestaetigt_am).days >= 90

    def stammdaten_bestaetigen(self):
        self.stammdaten_bestaetigt_am = timezone.now()
        self.save(update_fields=["stammdaten_bestaetigt_am"])

    @property
    def gruppe(self):
        if not self.geburtsjahr:
            return None
        return self.GRUPPE_JUGEND if self.geburtsjahr >= self.JUGEND_JAHRGANG_AB else self.GRUPPE_JUNIOREN

    @property
    def gruppe_anzeige(self):
        return {
            self.GRUPPE_JUGEND: "Jugend",
            self.GRUPPE_JUNIOREN: "Junioren",
        }.get(self.gruppe, "unbekannt")


class Termin(models.Model):
    ART_TRAINING = "training"
    ART_VERANSTALTUNG = "veranstaltung"
    ART_CHOICES = [
        (ART_TRAINING, "Training"),
        (ART_VERANSTALTUNG, "Veranstaltung"),
    ]

    GRUPPE_BEIDE = "beide"
    GRUPPE_JUGEND = "jugend"
    GRUPPE_JUNIOREN = "junioren"
    GRUPPE_CHOICES = [
        (GRUPPE_BEIDE, "Beide Gruppen"),
        (GRUPPE_JUGEND, "Jugend"),
        (GRUPPE_JUNIOREN, "Junioren"),
    ]

    titel = models.CharField("Titel", max_length=200)
    art = models.CharField("Art", max_length=20, choices=ART_CHOICES, default=ART_TRAINING)
    gruppe = models.CharField("Gruppe", max_length=20, choices=GRUPPE_CHOICES, default=GRUPPE_BEIDE)
    taenzerinnen_erforderlich = models.BooleanField(
        "Tänzerinnen müssen anwesend sein (Auftritt)", default=True,
        help_text="Deaktivieren bei Veranstaltungen ohne Auftritt der Tänzerinnen, z.B. 'Ladies Night'.",
    )
    beginn = models.DateTimeField("Beginn")
    ende = models.DateTimeField("Ende", null=True, blank=True)
    ort = models.CharField("Ort", max_length=200, blank=True)
    beschreibung = models.TextField("Beschreibung", blank=True)
    wichtiges_training = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="wichtig_fuer_veranstaltungen",
        limit_choices_to={"art": ART_TRAINING},
        verbose_name="Wichtiges Training (Verweis)",
        help_text="Optional: z.B. bei einer Veranstaltung auf ein Training verweisen, "
        "zu dem Anwesenheit wichtig ist (etwa eine Generalprobe).",
    )
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="erstellte_termine"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Termin"
        verbose_name_plural = "Termine"
        ordering = ["beginn"]

    def __str__(self):
        return f"{self.get_art_display()}: {self.titel} ({self.beginn:%d.%m.%Y %H:%M})"


class TrainingManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(art=Termin.ART_TRAINING)


class VeranstaltungManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(art=Termin.ART_VERANSTALTUNG)


class TrainingTermin(Termin):
    """Zeigt im Admin-Bereich nur Trainings an (gleiche Tabelle wie Termin)."""

    objects = TrainingManager()

    class Meta:
        proxy = True
        verbose_name = "Training"
        verbose_name_plural = "Trainings"


class VeranstaltungTermin(Termin):
    """Zeigt im Admin-Bereich nur Veranstaltungen an (gleiche Tabelle wie Termin)."""

    objects = VeranstaltungManager()

    class Meta:
        proxy = True
        verbose_name = "Veranstaltung"
        verbose_name_plural = "Veranstaltungen"


class Zusage(models.Model):
    STATUS_ZUGESAGT = "zugesagt"
    STATUS_ABGESAGT = "abgesagt"
    STATUS_OFFEN = "offen"
    STATUS_CHOICES = [
        (STATUS_ZUGESAGT, "Zugesagt"),
        (STATUS_ABGESAGT, "Abgesagt"),
        (STATUS_OFFEN, "Noch offen"),
    ]

    taenzerin = models.ForeignKey(
        Taenzerin, on_delete=models.CASCADE, related_name="zusagen"
    )
    termin = models.ForeignKey(Termin, on_delete=models.CASCADE, related_name="zusagen")
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default=STATUS_OFFEN)
    kommentar = models.CharField("Kommentar", max_length=300, blank=True)
    anwesend = models.BooleanField(
        "Anwesend", null=True, blank=True,
        help_text="Von Admin/Betreuer nach dem Termin bestätigt. Leer = noch nicht erfasst.",
    )
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zu-/Absage"
        verbose_name_plural = "Zu-/Absagen"
        unique_together = ("taenzerin", "termin")

    def __str__(self):
        return f"{self.taenzerin} - {self.termin} - {self.get_status_display()}"


class Anmeldepunkt(models.Model):
    """Ein Punkt auf einer Helfer- oder Mitbringliste, optional zu einem Termin, sonst allgemeine Aufgabe."""

    termin = models.ForeignKey(
        Termin, on_delete=models.CASCADE, null=True, blank=True, related_name="anmeldepunkte",
        help_text="Optional: zu welcher Veranstaltung gehört das? Leer lassen für eine allgemeine Aufgabe "
        "(z.B. 'Leibchen waschen'), zu der sich Mitglieder unabhängig von einem Termin eintragen können.",
    )
    titel = models.CharField("Titel", max_length=200, help_text="z.B. 'Kuchen mitbringen', 'Aufbauhelfer', 'Fahrdienst'")
    beschreibung = models.TextField("Beschreibung", blank=True)
    max_anzahl = models.PositiveIntegerField(
        "Benötigte Anzahl", null=True, blank=True,
        help_text="Leer lassen für unbegrenzt viele Anmeldungen",
    )
    mit_kommentar = models.BooleanField(
        "Mit Kommentar (z.B. für Mitbringen)", default=True,
        help_text="Aktiviert: Eltern können angeben, was sie mitbringen. Deaktiviert: reine Helferliste, einfach nur eintragen.",
    )

    class Meta:
        verbose_name = "Helfer-/Mitbringpunkt"
        verbose_name_plural = "Helfer-/Mitbringpunkte"

    def __str__(self):
        return f"{self.titel} ({self.termin.titel})" if self.termin else self.titel

    @property
    def anzahl_angemeldet(self):
        return self.anmeldungen.count()

    @property
    def plaetze_frei(self):
        if self.max_anzahl is None:
            return None
        return max(self.max_anzahl - self.anzahl_angemeldet, 0)


class Anmeldung(models.Model):
    """Die Anmeldung eines Elternteils zu einem Anmeldepunkt (helfen/mitbringen/fahren)."""

    anmeldepunkt = models.ForeignKey(Anmeldepunkt, on_delete=models.CASCADE, related_name="anmeldungen")
    eltern = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="helfer_anmeldungen"
    )
    kommentar = models.CharField("Kommentar", max_length=300, blank=True, help_text="z.B. was du mitbringst")
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anmeldung"
        verbose_name_plural = "Anmeldungen"

    def __str__(self):
        return f"{self.eltern} - {self.anmeldepunkt}"


class Aufgabe(models.Model):
    """To-Do-Eintrag für Admins/Betreuer, optional zu einer Veranstaltung, sonst allgemeine Planung."""

    titel = models.CharField("Titel", max_length=200)
    beschreibung = models.TextField("Beschreibung", blank=True)
    termin = models.ForeignKey(
        Termin, on_delete=models.CASCADE, null=True, blank=True, related_name="aufgaben",
        limit_choices_to={"art": Termin.ART_VERANSTALTUNG},
        help_text="Optional: zu welcher Veranstaltung gehört die Aufgabe? Leer lassen für allgemeine Planung.",
        verbose_name="Veranstaltung",
    )
    faellig_am = models.DateField(
        "Fällig am", null=True, blank=True,
        help_text="Optional: bis wann soll die Aufgabe erledigt sein? (z.B. 'Leibchen waschen' bis zum "
        "nächsten Training).",
    )
    erledigt = models.BooleanField("Erledigt", default=False)
    erledigt_am = models.DateTimeField(null=True, blank=True)
    zugewiesen_an = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="zugewiesene_aufgaben",
        verbose_name="Zugewiesen an",
        help_text="Optional: wer kümmert sich darum? (Wird auch automatisch gesetzt, wenn sich jemand "
        "im Mitgliederbereich selbst einträgt.)",
    )
    nur_team = models.BooleanField(
        "Nur Orga-/Admin-Team", default=True,
        help_text="Aktiviert: nur Orga-/Admin-Team sieht diese Aufgabe im Mitgliederbereich und kann "
        "sie übernehmen. Deaktiviert: auch Eltern können sich dafür eintragen.",
    )
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="aufgaben"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Aufgabe"
        verbose_name_plural = "Aufgaben (To-Do)"
        ordering = ["erledigt", "termin__beginn", "-erstellt_am"]

    def __str__(self):
        return self.titel

    @property
    def ueberfaellig(self):
        return bool(self.faellig_am and not self.erledigt and self.faellig_am < timezone.localdate())

    def save(self, *args, **kwargs):
        if self.erledigt and not self.erledigt_am:
            self.erledigt_am = timezone.now()
        elif not self.erledigt:
            self.erledigt_am = None
        super().save(*args, **kwargs)


class NewsPost(models.Model):
    titel = models.CharField("Titel", max_length=200)
    text = models.TextField("Text")
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="news_posts"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "News-Beitrag"
        verbose_name_plural = "News-Beiträge"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return self.titel


class Feedback(models.Model):
    """Nachricht eines Mitglieds an die Admins/Betreuer."""

    absender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="feedbacks"
    )
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    nachricht = models.TextField("Nachricht")
    gelesen = models.BooleanField("Gelesen", default=False)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Feedback"
        verbose_name_plural = "Feedback / Nachrichten"
        ordering = ["gelesen", "-erstellt_am"]

    def __str__(self):
        return f"{self.absender}: {self.betreff or self.nachricht[:40]}"


class Ferienzeitraum(models.Model):
    """Schulferien in Bayern. Werden jährlich vom Kultusministerium neu festgelegt,
    darum hier manuell pflegen (aktuelle Termine unter www.km.bayern.de)."""

    name = models.CharField("Name", max_length=100, help_text="z.B. 'Sommerferien 2026'")
    start_datum = models.DateField("Von")
    end_datum = models.DateField("Bis (einschließlich)")

    class Meta:
        verbose_name = "Ferienzeitraum"
        verbose_name_plural = "Ferienzeiträume (Bayern)"
        ordering = ["start_datum"]

    def __str__(self):
        return f"{self.name} ({self.start_datum:%d.%m.%Y} – {self.end_datum:%d.%m.%Y})"
