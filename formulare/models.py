from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models

# PDFs/Dokumente sind bei Cloudinary kein "image", sondern "raw" - mit der normalen
# (Bild-)Storage wuerden hochgeladene PDFs nicht korrekt abrufbar sein ("Fehler beim
# Laden des PDF-Dokuments"). Ohne Cloudinary-Zugangsdaten (z.B. lokal) ganz normal lokal.
if settings.CLOUDINARY_STORAGE.get("CLOUD_NAME"):
    from cloudinary_storage.storage import RawMediaCloudinaryStorage

    _formular_storage = RawMediaCloudinaryStorage()
else:
    _formular_storage = FileSystemStorage()


class Formular(models.Model):
    """Ein Dokument (z.B. PDF-Formular), das im Mitgliederbereich verlinkt wird."""

    titel = models.CharField("Titel", max_length=200, help_text="z.B. 'Anmeldung Sommerlager'")
    datei = models.FileField("Datei", upload_to="formulare/", storage=_formular_storage)
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
