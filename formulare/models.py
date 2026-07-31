from django.db import models


class Formular(models.Model):
    """Ein Dokument (z.B. PDF-Formular), das im Mitgliederbereich verlinkt wird."""

    titel = models.CharField("Titel", max_length=200, help_text="z.B. 'Anmeldung Sommerlager'")
    datei = models.FileField("Datei", upload_to="formulare/")
    reihenfolge = models.PositiveIntegerField(
        "Reihenfolge", default=0, help_text="Kleinere Zahl wird zuerst angezeigt."
    )
    hochgeladen_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Formular"
        verbose_name_plural = "Formulare"
        ordering = ["reihenfolge", "titel"]

    def __str__(self):
        return self.titel
