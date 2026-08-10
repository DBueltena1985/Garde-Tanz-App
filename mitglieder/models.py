from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Gruppe(models.Model):
    """Eine frei anlegbare Trainingsgruppe (z.B. Jugend, Junioren, Damen), der Tänzerinnen
    anhand ihres Geburtsjahrs automatisch zugeordnet werden."""

    name = models.CharField("Name", max_length=50, unique=True, help_text="z.B. Jugend, Junioren, Damen")
    jahrgang_ab = models.IntegerField(
        "Jahrgang ab", unique=True,
        help_text="Tänzerinnen mit diesem Geburtsjahr oder jünger gehören zu dieser Gruppe - "
        "es sei denn, eine andere Gruppe hat eine noch höhere Jahrgangsgrenze und passt damit besser. "
        "Die Gruppe mit der niedrigsten Zahl fängt automatisch auch alle älteren Jahrgänge auf.",
    )

    class Meta:
        verbose_name = "Gruppe"
        verbose_name_plural = "Gruppen"
        ordering = ["-jahrgang_ab"]

    def __str__(self):
        return self.name

    @classmethod
    def fuer_jahrgang(cls, jahr):
        """Liefert die passende Gruppe fuer ein Geburtsjahr, oder None falls keine Gruppe existiert."""
        gruppen = list(cls.objects.order_by("-jahrgang_ab"))
        for gruppe in gruppen:
            if jahr >= gruppe.jahrgang_ab:
                return gruppe
        return gruppen[-1] if gruppen else None


class Taenzerin(models.Model):
    """Ein Kind, das von einem Elternaccount verwaltet wird, inkl. Stammdaten."""

    eltern = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kinder"
    )
    mitverwaltet_von = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="mitverwaltete_kinder", blank=True,
        verbose_name="Mitverwaltet von",
        help_text="Weitere Benutzer (z.B. Partner:in), die dieses Kind ebenfalls sehen und verwalten dürfen.",
    )
    nutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="taenzerin_konto",
        verbose_name="Gehört zu Benutzerkonto",
        help_text="Falls dieser Eintrag zu einem eigenen Login-Konto gehört (z.B. eine Tänzerin mit "
        "eigenem Zugang statt rein von einem Elternteil verwaltet zu werden).",
    )

    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsdatum = models.DateField(
        "Geburtsdatum", null=True, blank=True,
        help_text="Bestimmt die Trainingsgruppe (siehe Verwaltung unter Gruppen).",
    )
    adresse = models.CharField("Adresse", max_length=200, blank=True)
    plz_ort = models.CharField("PLZ / Ort", max_length=100, blank=True)
    mobil = models.CharField(
        "Mobil", max_length=50, blank=True,
        help_text="Eigene Mobilnummer der Tänzerin/des Tänzers, falls vorhanden.",
    )

    # Notfallkontakt
    notfallkontakt_name = models.CharField("Notfallkontakt Name", max_length=200, blank=True)
    notfallkontakt_telefon = models.CharField("Notfallkontakt Telefon", max_length=50, blank=True)
    notfallkontakt_beziehung = models.CharField(
        "Beziehung zum Notfallkontakt", max_length=100, blank=True,
        help_text="z.B. Mutter, Vater, Partner:in",
    )

    alleine_nach_hause = models.BooleanField(
        "Darf nach dem Training selbstständig nach Hause", null=True, blank=True, default=None,
        help_text="Leer = noch nicht angegeben.",
    )
    abholberechtigte = models.TextField(
        "Abholberechtigte", blank=True,
        help_text="Namen der Personen, die die Tänzerin/den Tänzer abholen dürfen "
        "(falls nicht selbstständig nach Hause darf).",
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

    einverstaendnis_bildaufnahmen = models.BooleanField(
        "Einverständnis Bild-/Videoaufnahmen (Social Media, Homepage, Presse)",
        null=True, blank=True, default=None,
        help_text="Muss separat bestätigt werden, ist nicht Teil der allgemeinen Stammdaten-Bestätigung. "
        "Leer = noch nicht entschieden.",
    )
    einverstaendnis_bildaufnahmen_am = models.DateTimeField(
        "Einverständnis zuletzt bestätigt am", null=True, blank=True
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
    def fehlende_pflichtfelder(self):
        """Namen der Pflichtfelder, die noch nicht ausgefüllt sind (unabhängig vom Bestätigt-Status)."""
        pflichtfelder = [
            "schuhgroesse", "kleidergroesse", "notfallkontakt_name", "notfallkontakt_telefon",
        ]
        fehlend = [
            self._meta.get_field(feld).verbose_name
            for feld in pflichtfelder
            if not getattr(self, feld)
        ]
        if self.alleine_nach_hause is None:
            fehlend.append(self._meta.get_field("alleine_nach_hause").verbose_name)
        elif self.alleine_nach_hause is False and not self.abholberechtigte:
            fehlend.append(self._meta.get_field("abholberechtigte").verbose_name)
        if self.einverstaendnis_bildaufnahmen is None:
            fehlend.append(self._meta.get_field("einverstaendnis_bildaufnahmen").verbose_name)
        return fehlend

    def einverstaendnis_bildaufnahmen_setzen(self, wert):
        self.einverstaendnis_bildaufnahmen = wert
        self.einverstaendnis_bildaufnahmen_am = timezone.now()
        self.save(update_fields=["einverstaendnis_bildaufnahmen", "einverstaendnis_bildaufnahmen_am"])

    @property
    def gruppe(self):
        if not self.geburtsdatum:
            return None
        return Gruppe.fuer_jahrgang(self.geburtsdatum.year)

    @property
    def gruppe_anzeige(self):
        gruppe = self.gruppe
        return gruppe.name if gruppe else "unbekannt"


class Profil(models.Model):
    """Zusaetzliche Angaben zum Benutzerkonto (z.B. Eltern), unabhaengig von einer einzelnen Taenzerin."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil"
    )

    hilfe_fahrdienste = models.BooleanField("Fahrdienste", default=False)
    hilfe_veranstaltungen = models.BooleanField("Veranstaltungen", default=False)
    hilfe_kuchen_essensspenden = models.BooleanField("Kuchen / Essensspenden", default=False)
    hilfe_dekoration_basteln = models.BooleanField("Dekoration / Basteln", default=False)
    hilfe_naehen_aenderungen = models.BooleanField("Nähen / Änderungen an Kostümen", default=False)
    hilfe_fotos_social_media = models.BooleanField("Fotos / Social Media", default=False)
    hilfe_organisation = models.BooleanField("Organisation", default=False)
    hilfe_sponsoring_kontakte = models.BooleanField("Sponsoring / Kontakte", default=False)
    hilfe_sonstiges = models.CharField("Sonstiges", max_length=200, blank=True)

    einverstanden_datennutzung = models.BooleanField(
        "Einverstanden, dass meine Daten für vereinsinterne Zwecke genutzt werden",
        null=True, blank=True, default=None,
        help_text="Muss separat bestätigt werden. Leer = noch nicht entschieden.",
    )
    einverstanden_datennutzung_am = models.DateTimeField(
        "Einverständnis zuletzt bestätigt am", null=True, blank=True
    )

    class Meta:
        verbose_name = "Profil"
        verbose_name_plural = "Profile"

    def __str__(self):
        return f"Profil von {self.user}"

    def datennutzung_setzen(self, wert):
        self.einverstanden_datennutzung = wert
        self.einverstanden_datennutzung_am = timezone.now()
        self.save(update_fields=["einverstanden_datennutzung", "einverstanden_datennutzung_am"])


class Termin(models.Model):
    ART_TRAINING = "training"
    ART_VERANSTALTUNG = "veranstaltung"
    ART_CHOICES = [
        (ART_TRAINING, "Training"),
        (ART_VERANSTALTUNG, "Veranstaltung"),
    ]

    titel = models.CharField("Titel", max_length=200)
    art = models.CharField("Art", max_length=20, choices=ART_CHOICES, default=ART_TRAINING)
    gruppen = models.ManyToManyField(
        Gruppe, blank=True, verbose_name="Gruppen",
        help_text="Für welche Gruppen gilt dieser Termin? Leer lassen = gilt für alle Gruppen.",
    )
    taenzerinnen_erforderlich = models.BooleanField(
        "Tänzerinnen müssen anwesend sein (Auftritt)", default=True,
        help_text="Deaktivieren bei Veranstaltungen ohne Auftritt der Tänzerinnen, z.B. 'Ladies Night'.",
    )
    beginn = models.DateTimeField("Beginn")
    ende = models.DateTimeField("Ende", null=True, blank=True)
    uhrzeit_unbekannt = models.BooleanField(
        "Uhrzeit steht noch nicht fest", default=False,
        help_text="Datum ist bekannt, aber die genaue Uhrzeit noch nicht - wird den Mitgliedern als "
        "\"Uhrzeit folgt noch\" angezeigt (die Uhrzeit von Beginn/Ende wird dann ignoriert).",
    )
    ort = models.CharField("Ort", max_length=200, blank=True)
    beschreibung = models.TextField("Beschreibung", blank=True)
    beschreibung_bild = models.ImageField(
        "Bild zur Beschreibung", upload_to="termine/", blank=True, null=True,
        help_text="Optional: wird zusammen mit der Beschreibung angezeigt, z.B. ein Flyer.",
    )
    interne_notiz = models.TextField(
        "Interne Notiz", blank=True,
        help_text="Nicht öffentlich – nur für Orga-/Admin-Team sichtbar, z.B. im Mitgliederbereich.",
    )
    wichtige_trainings = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="wichtig_fuer_veranstaltungen",
        limit_choices_to={"art": ART_TRAINING},
        verbose_name="Wichtige Trainings (Verweis)",
        help_text="Optional: z.B. bei einer Veranstaltung auf ein oder mehrere Trainings verweisen, "
        "zu denen Anwesenheit wichtig ist (etwa Generalproben).",
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
        lokal = timezone.localtime(self.beginn)
        return f"{self.get_art_display()}: {self.titel} ({lokal:%d.%m.%Y %H:%M})"

    @property
    def hat_galeriebilder(self):
        """Ob es zu dieser Veranstaltung Fotos gibt - direkt zugeordnet oder über einen verlinkten Galerie-Ordner."""
        return self.galeriebilder.exists() or self.galerie_ordner.filter(bilder__isnull=False).exists()


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

    ZIELGRUPPE_TEAM = "team"
    ZIELGRUPPE_ELTERN = "eltern"
    ZIELGRUPPE_TAENZERINNEN = "taenzerinnen"
    ZIELGRUPPE_CHOICES = [
        (ZIELGRUPPE_TEAM, "Nur Orga-/Admin-Team"),
        (ZIELGRUPPE_ELTERN, "Eltern"),
        (ZIELGRUPPE_TAENZERINNEN, "Tänzerinnen"),
    ]

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
    sichtbar_fuer = models.CharField(
        "Sichtbar für", max_length=20, choices=ZIELGRUPPE_CHOICES, default=ZIELGRUPPE_TEAM,
        help_text="Wer sieht diese Aufgabe im Mitgliederbereich und kann sie übernehmen? "
        "Eltern sehen zusätzlich alle für Tänzerinnen bestimmten Aufgaben, das Orga-/Admin-Team sieht immer alles.",
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


class AufgabeErledigung(models.Model):
    """Pro-Taenzerin-Erledigt-Status fuer eine Aufgabe mit Zielgruppe 'Taenzerinnen'
    (z.B. waescht jede Taenzerin ihr eigenes Leibchen - eine Aufgabe, aber pro Kind einzeln erledigt)."""

    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.CASCADE, related_name="erledigungen")
    taenzerin = models.ForeignKey(Taenzerin, on_delete=models.CASCADE, related_name="aufgaben_erledigungen")
    erledigt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Aufgaben-Erledigung"
        verbose_name_plural = "Aufgaben-Erledigungen"
        unique_together = ("aufgabe", "taenzerin")

    def __str__(self):
        return f"{self.aufgabe.titel} – {self.taenzerin} erledigt"


class NewsPostManager(models.Manager):
    def aktuell(self):
        """Nur Beitraege, deren 'Anzeigen bis'-Datum noch nicht erreicht ist (oder leer ist)."""
        heute = timezone.localdate()
        return self.filter(Q(anzeigen_bis__isnull=True) | Q(anzeigen_bis__gte=heute))


class NewsPost(models.Model):
    titel = models.CharField("Titel", max_length=200)
    text = models.TextField("Text", blank=True, help_text="Optional, wenn stattdessen nur ein Bild gezeigt werden soll.")
    bild = models.ImageField("Bild", upload_to="news/", blank=True, null=True)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="news_posts"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    anzeigen_bis = models.DateField(
        "Anzeigen bis", null=True, blank=True,
        help_text="Optional: ab dem Folgetag wird der Beitrag nicht mehr angezeigt. Leer = zeitlich unbegrenzt.",
    )

    objects = NewsPostManager()

    class Meta:
        verbose_name = "News-Beitrag"
        verbose_name_plural = "News-Beiträge"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return self.titel

    def clean(self):
        if not self.text and not self.bild:
            raise ValidationError("Bitte entweder einen Text oder ein Bild angeben.")


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


class Nachricht(models.Model):
    """Eine Nachricht von Admin/Orgateam an einen einzelnen Nutzer."""

    empfaenger = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="erhaltene_nachrichten",
        verbose_name="An",
    )
    absender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="gesendete_nachrichten",
    )
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    nachricht = models.TextField("Nachricht")
    gelesen = models.BooleanField("Gelesen", default=False)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nachricht an Mitglied"
        verbose_name_plural = "Nachrichten an Mitglieder"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"{self.betreff or self.nachricht[:40]} → {self.empfaenger}"


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


class Galerieordner(models.Model):
    """Ein Ordner in der allgemeinen Bildergalerie, optional komplett einer Veranstaltung zugeordnet."""

    name = models.CharField("Name", max_length=200)
    veranstaltung = models.ForeignKey(
        Termin, on_delete=models.SET_NULL, null=True, blank=True, related_name="galerie_ordner",
        limit_choices_to={"art": Termin.ART_VERANSTALTUNG},
        verbose_name="Veranstaltung",
        help_text="Optional: den kompletten Ordner (inkl. aller Bilder) einer Veranstaltung zuordnen - "
        "die Bilder erscheinen dann in der Galerie unter dieser Veranstaltung statt als eigener Ordner.",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Galerie-Ordner"
        verbose_name_plural = "Galerie-Ordner"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return self.name


class Galeriebild(models.Model):
    """Ein Foto in der Bildergalerie, optional einer Veranstaltung oder einem Ordner zugeordnet."""

    termin = models.ForeignKey(
        Termin, on_delete=models.CASCADE, null=True, blank=True, related_name="galeriebilder",
        limit_choices_to={"art": Termin.ART_VERANSTALTUNG},
        verbose_name="Veranstaltung",
        help_text="Optional: zu welcher Veranstaltung gehört das Bild? Leer lassen für die allgemeine Galerie.",
    )
    ordner = models.ForeignKey(
        Galerieordner, on_delete=models.CASCADE, null=True, blank=True, related_name="bilder",
        verbose_name="Ordner",
        help_text="Optional: alternativ zu einer Veranstaltung - Ordner in der allgemeinen Galerie.",
    )
    bild = models.ImageField("Bild", upload_to="galerie/")
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)
    titelbild = models.BooleanField(
        "Titelbild", default=False,
        help_text="Wird in der Galerie-Übersicht zuerst und größer angezeigt (nur eines pro Ordner/Veranstaltung).",
    )
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hochgeladene_bilder"
    )
    hochgeladen_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Galeriebild"
        verbose_name_plural = "Galeriebilder"
        ordering = ["-hochgeladen_am"]

    def __str__(self):
        if self.beschreibung:
            return self.beschreibung
        if self.termin:
            return self.termin.titel
        if self.ordner:
            return self.ordner.name
        return "Allgemeines Bild"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.titelbild:
            Galeriebild.objects.filter(ordner=self.ordner, termin=self.termin).exclude(pk=self.pk).update(
                titelbild=False
            )
