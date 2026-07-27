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
    beginn = models.DateTimeField("Beginn")
    ende = models.DateTimeField("Ende", null=True, blank=True)
    ort = models.CharField("Ort", max_length=200, blank=True)
    beschreibung = models.TextField("Beschreibung", blank=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="erstellte_termine"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Termin"
        verbose_name_plural = "Termine"
        ordering = ["beginn"]

    def __str__(self):
        return f"{self.get_art_display()}: {self.titel} ({self.beginn:%d.%m.%Y %H:%M})"


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
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zu-/Absage"
        verbose_name_plural = "Zu-/Absagen"
        unique_together = ("taenzerin", "termin")

    def __str__(self):
        return f"{self.taenzerin} - {self.termin} - {self.get_status_display()}"


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
