from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Profil(models.Model):
    """Stammdaten einer Tänzerin/eines Mitglieds, zusätzlich zum Django-User."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil"
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
        verbose_name = "Profil"
        verbose_name_plural = "Profile"

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def bestaetigung_faellig(self):
        """True, wenn die Stammdaten noch nie oder vor mehr als 90 Tagen bestätigt wurden."""
        if not self.stammdaten_bestaetigt_am:
            return True
        return (timezone.now() - self.stammdaten_bestaetigt_am).days >= 90

    def stammdaten_bestaetigen(self):
        self.stammdaten_bestaetigt_am = timezone.now()
        self.save(update_fields=["stammdaten_bestaetigt_am"])


class Termin(models.Model):
    ART_TRAINING = "training"
    ART_VERANSTALTUNG = "veranstaltung"
    ART_CHOICES = [
        (ART_TRAINING, "Training"),
        (ART_VERANSTALTUNG, "Veranstaltung"),
    ]

    titel = models.CharField("Titel", max_length=200)
    art = models.CharField("Art", max_length=20, choices=ART_CHOICES, default=ART_TRAINING)
    beginn = models.DateTimeField("Beginn")
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

    mitglied = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="zusagen"
    )
    termin = models.ForeignKey(Termin, on_delete=models.CASCADE, related_name="zusagen")
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default=STATUS_OFFEN)
    kommentar = models.CharField("Kommentar", max_length=300, blank=True)
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zu-/Absage"
        verbose_name_plural = "Zu-/Absagen"
        unique_together = ("mitglied", "termin")

    def __str__(self):
        return f"{self.mitglied} - {self.termin} - {self.get_status_display()}"


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
