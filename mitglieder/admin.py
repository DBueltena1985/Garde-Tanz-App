from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import login
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import (
    Anmeldepunkt, Anmeldung, Aufgabe, AufgabeErledigung, Feedback, Ferienzeitraum, Galeriebild, Galerieordner,
    Nachricht, NewsPost, Profil, Taenzerin, Termin, TrainingTermin, VeranstaltungTermin, Zusage,
)


class LoeschLinkMixin:
    """Fügt eine Mülleimer-Spalte zum Löschen einzelner Zeilen hinzu (statt nur über die
    Sammel-Aktion oben im Dropdown - "Ausgewählte Objekte löschen" ist deaktiviert)."""

    save_on_top = True

    LOESCHEN_SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" '
        'fill="#b3261e" style="vertical-align:middle;">'
        '<path d="M9 3v1H4v2h1v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6h1V4h-5V3H9zm-2 3h10v13H7V6zm2 2v9h2V8H9zm4 0v9h2V8h-2z"/>'
        "</svg>"
    )

    def loeschen_link(self, obj):
        url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_delete", args=[obj.pk])
        return format_html(
            '<a href="{}" title="Löschen" onclick="return confirm(\'Wirklich löschen?\');" '
            'style="text-decoration:none;">{}</a>',
            url, mark_safe(self.LOESCHEN_SVG),
        )

    loeschen_link.short_description = ""


def _relevante_kinder(gruppe):
    """Liefert alle Tänzerinnen, deren Gruppe zum Termin passt (oder alle bei 'beide')."""
    alle = Taenzerin.objects.select_related("eltern")
    if gruppe == Termin.GRUPPE_BEIDE:
        return list(alle)
    return [k for k in alle if k.gruppe == gruppe]


class TaenzerinInline(admin.TabularInline):
    model = Taenzerin
    fk_name = "eltern"
    extra = 0
    fields = ("vorname", "nachname", "schuhgroesse", "kleidergroesse", "stammdaten_bestaetigt_am")
    show_change_link = True


class ProfilInline(admin.StackedInline):
    model = Profil
    extra = 0
    can_delete = False


def _verknuepfte_benutzer_ids(user):
    """Andere Benutzer, die über ein gemeinsames Kind (Eltern/Mitverwaltung/eigenes Konto) verbunden sind."""
    kinder = Taenzerin.objects.filter(
        Q(eltern=user) | Q(mitverwaltet_von=user) | Q(nutzer=user)
    ).prefetch_related("mitverwaltet_von")
    ids = set()
    for kind in kinder:
        ids.add(kind.eltern_id)
        ids.update(kind.mitverwaltet_von.values_list("id", flat=True))
        if kind.nutzer_id:
            ids.add(kind.nutzer_id)
    ids.discard(user.id)
    return ids


class UnterstuetzungFilter(admin.SimpleListFilter):
    title = "Kann unterstützen bei"
    parameter_name = "kann_unterstuetzen_bei"

    def lookups(self, request, model_admin):
        return (
            ("hilfe_fahrdienste", "Fahrdiensten"),
            ("hilfe_veranstaltungen", "Veranstaltungen"),
            ("hilfe_kuchen_essensspenden", "Kuchen / Essensspenden"),
            ("hilfe_dekoration_basteln", "Dekoration / Basteln"),
            ("hilfe_naehen_aenderungen", "Nähen / Änderungen an Kostümen"),
            ("hilfe_fotos_social_media", "Fotos / Social Media"),
            ("hilfe_organisation", "Organisation"),
            ("hilfe_sponsoring_kontakte", "Sponsoring / Kontakte"),
        )

    def queryset(self, request, queryset):
        wert = self.value()
        if not wert:
            return queryset
        return queryset.filter(**{f"profil__{wert}": True})


class CustomUserAdmin(LoeschLinkMixin, UserAdmin):
    inlines = [TaenzerinInline, ProfilInline]
    list_display = (
        "first_name", "last_name", "username", "orga_team", "admin_team", "verknuepfte_benutzer", "loeschen_link",
    )
    list_filter = UserAdmin.list_filter + (UnterstuetzungFilter,)
    ordering = ("first_name", "last_name")
    change_form_template = "admin/mitglieder_user_change_form.html"
    change_list_template = "admin/mitglieder_user_change_list.html"

    def orga_team(self, obj):
        return obj.is_staff

    orga_team.short_description = "Orga-Team"
    orga_team.boolean = True
    orga_team.admin_order_field = "is_staff"

    def admin_team(self, obj):
        return obj.is_superuser

    admin_team.short_description = "Admin-Team"
    admin_team.boolean = True
    admin_team.admin_order_field = "is_superuser"

    def verknuepfte_benutzer(self, obj):
        ids = _verknuepfte_benutzer_ids(obj)
        if not ids:
            return "–"
        andere = User.objects.filter(id__in=ids)
        return format_html_join(
            ", ",
            '<a href="{}">{}</a>',
            (
                (reverse("admin:auth_user_change", args=[u.id]), u.first_name or u.username)
                for u in andere
            ),
        )

    verknuepfte_benutzer.short_description = "Verknüpfte Benutzer"

    def get_urls(self):
        eigene_urls = [
            path(
                "<int:user_id>/als-mitglied-ansehen/",
                self.admin_site.admin_view(self.als_mitglied_ansehen),
                name="auth_user_impersonate_start",
            ),
        ]
        return eigene_urls + super().get_urls()

    def als_mitglied_ansehen(self, request, user_id):
        if not request.user.is_superuser:
            raise PermissionDenied
        ziel = get_object_or_404(User, pk=user_id, is_active=True)
        if request.method != "POST":
            raise PermissionDenied

        echter_admin_id = request.user.id
        login(request, ziel, backend="django.contrib.auth.backends.ModelBackend")
        request.session["impersonator_id"] = echter_admin_id
        messages.success(request, f"Du siehst die App jetzt als {ziel.first_name or ziel.username} an.")
        return redirect("dashboard")


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


class TaenzerinStatusFilter(admin.SimpleListFilter):
    title = "Stammdaten-Status"
    parameter_name = "stammdaten_status"

    def lookups(self, request, model_admin):
        return (("faellig", "Bestätigung fällig (>90 Tage / nie)"),)

    def queryset(self, request, queryset):
        if self.value() == "faellig":
            ids = [t.pk for t in queryset if t.bestaetigung_faellig]
            return queryset.filter(pk__in=ids)
        return queryset


@admin.register(Taenzerin)
class TaenzerinAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = (
        "vorname", "nachname", "eltern_name", "nutzer", "gruppe_anzeige",
        "notfallkontakt_anruf", "schuhgroesse", "kleidergroesse", "stammdaten_status",
        "einverstaendnis_bildaufnahmen", "loeschen_link",
    )
    list_filter = (TaenzerinStatusFilter, "einverstaendnis_bildaufnahmen")
    search_fields = ("vorname", "nachname", "eltern__username", "eltern__first_name", "eltern__last_name")

    def eltern_name(self, obj):
        voller_name = f"{obj.eltern.first_name} {obj.eltern.last_name}".strip()
        return voller_name or obj.eltern.username

    eltern_name.short_description = "Eltern"
    eltern_name.admin_order_field = "eltern__first_name"
    filter_horizontal = ("mitverwaltet_von",)
    fields = (
        "eltern", "mitverwaltet_von", "nutzer", "vorname", "nachname", "geburtsdatum",
        "adresse", "plz_ort", "mobil",
        "notfallkontakt_name", "notfallkontakt_telefon", "notfallkontakt_beziehung",
        "alleine_nach_hause", "abholberechtigte",
        "schuhgroesse", "kleidergroesse", "allergien", "medikamente", "sonstige_hinweise",
        "stammdaten_bestaetigt_am", "einverstaendnis_bildaufnahmen", "einverstaendnis_bildaufnahmen_am",
    )

    def stammdaten_status(self, obj):
        return "fällig" if obj.bestaetigung_faellig else "aktuell"

    stammdaten_status.short_description = "Stammdaten"

    def notfallkontakt_anruf(self, obj):
        if not obj.notfallkontakt_telefon:
            return "–"
        telefon_waehlbar = "".join(ch for ch in obj.notfallkontakt_telefon if ch.isdigit() or ch == "+")
        return format_html(
            '<a href="tel:{}">📞 {}</a>', telefon_waehlbar, obj.notfallkontakt_telefon
        )

    notfallkontakt_anruf.short_description = "Notfallkontakt"


class SerienTerminForm(forms.Form):
    WOCHENTAG_CHOICES = [
        (0, "Montag"), (1, "Dienstag"), (2, "Mittwoch"), (3, "Donnerstag"),
        (4, "Freitag"), (5, "Samstag"), (6, "Sonntag"),
    ]

    titel = forms.CharField(label="Titel", max_length=200)
    gruppe = forms.ChoiceField(label="Gruppe", choices=Termin.GRUPPE_CHOICES)
    wochentag = forms.ChoiceField(label="Wochentag", choices=WOCHENTAG_CHOICES)
    startzeit = forms.TimeField(label="Startzeit", widget=forms.TimeInput(attrs={"type": "time"}))
    endzeit = forms.TimeField(label="Endzeit", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    ort = forms.CharField(label="Ort", max_length=200, required=False)
    beschreibung = forms.CharField(label="Beschreibung", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    start_datum = forms.DateField(label="Erster Termin ab", widget=forms.DateInput(attrs={"type": "date"}))
    end_datum = forms.DateField(label="Serie bis (einschließlich)", widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_datum")
        ende = cleaned.get("end_datum")
        if start and ende and ende < start:
            raise forms.ValidationError("Das Enddatum muss nach dem Startdatum liegen.")
        return cleaned


class SerieBearbeitenForm(forms.Form):
    titel = forms.ChoiceField(label="Serie (Titel)")
    ab_datum = forms.DateField(
        label="Änderungen gelten ab (einschließlich)",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Termine vor diesem Datum bleiben unverändert.",
    )
    neue_startzeit = forms.TimeField(label="Neue Startzeit", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    neue_endzeit = forms.TimeField(label="Neue Endzeit", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    neuer_ort = forms.CharField(label="Neuer Ort", max_length=200, required=False)
    neue_gruppe = forms.ChoiceField(
        label="Neue Gruppe", required=False,
        choices=[("", "— unverändert —")] + Termin.GRUPPE_CHOICES,
    )
    neue_beschreibung = forms.CharField(label="Neue Beschreibung", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    serie_verlaengern_bis = forms.DateField(
        label="Serie verlängern bis (optional)", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Ergänzt zusätzliche Termine im gleichen Wochenrhythmus bis zu diesem Datum, "
                   "im Anschluss an den letzten bestehenden Termin der Serie.",
    )

    def __init__(self, *args, titel_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["titel"].choices = titel_choices or []


class SerieLoeschenForm(forms.Form):
    titel = forms.ChoiceField(label="Serie (Titel)")
    ab_datum = forms.DateField(
        label="Nur löschen ab (optional)", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Leer lassen, um alle Termine dieser Serie zu löschen.",
    )

    def __init__(self, *args, titel_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["titel"].choices = titel_choices or []


class AnmeldepunktInline(admin.TabularInline):
    model = Anmeldepunkt
    extra = 0
    fields = ("titel", "beschreibung", "max_anzahl", "mit_kommentar", "status_anzeige")
    readonly_fields = ("status_anzeige",)

    def status_anzeige(self, obj):
        if not obj or not obj.pk:
            return "–"
        if obj.max_anzahl is None:
            return f"{obj.anzahl_angemeldet} angemeldet"
        if obj.plaetze_frei == 0:
            return format_html('<span style="color:#1a7a3c; font-weight:600;">{}</span>', f"{obj.anzahl_angemeldet}/{obj.max_anzahl} – voll")
        return format_html('<span style="color:#b3261e; font-weight:600;">{}</span>', f"{obj.anzahl_angemeldet}/{obj.max_anzahl} – {obj.plaetze_frei} offen")

    status_anzeige.short_description = "Status"


class AufgabeInline(admin.TabularInline):
    model = Aufgabe
    extra = 0
    fields = ("titel", "beschreibung", "faellig_am", "zugewiesen_an", "erledigt")

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["zugewiesen_an"].queryset = User.objects.filter(is_staff=True)
        return formset


class GaleriebildInline(admin.TabularInline):
    model = Galeriebild
    extra = 1
    fields = ("bild", "vorschau", "beschreibung", "titelbild")
    readonly_fields = ("vorschau",)

    def vorschau(self, obj):
        if obj and obj.pk and obj.bild:
            return format_html('<img src="{}" style="height:60px; border-radius:4px;">', obj.bild.url)
        return "–"


class GalerieordnerVeranstaltungInline(admin.TabularInline):
    """Zeigt Galerie-Ordner, die dieser Veranstaltung zugeordnet sind - nur zum Anschauen/Anklicken,
    bearbeitet werden die Ordner weiterhin über ihre eigene Admin-Seite."""

    model = Galerieordner
    fk_name = "veranstaltung"
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("name", "anzahl_bilder_anzeige", "erstellt_am")
    readonly_fields = ("name", "anzahl_bilder_anzeige", "erstellt_am")
    verbose_name = "Zugeordneter Galerie-Ordner"
    verbose_name_plural = "Zugeordnete Galerie-Ordner"

    def has_add_permission(self, request, obj=None):
        return False

    def anzahl_bilder_anzeige(self, obj):
        return obj.bilder.count()

    anzahl_bilder_anzeige.short_description = "Bilder"


class GaleriebildOrdnerInline(admin.TabularInline):
    model = Galeriebild
    fk_name = "ordner"
    extra = 5
    fields = ("bild", "vorschau", "beschreibung", "titelbild")
    readonly_fields = ("vorschau",)

    def vorschau(self, obj):
        if obj and obj.pk and obj.bild:
            return format_html('<img src="{}" style="height:60px; border-radius:4px;">', obj.bild.url)
        return "–"

    vorschau.short_description = "Vorschau"


class BildBulkUploadMixin:
    """Fügt einen Button 'Bilder hochladen' hinzu, mit dem man auf einmal mehrere Bilder in
    einem Rutsch hochladen kann (statt einzeln über Inline-Formularzeilen) - auch nachträglich."""

    bild_fk_feld = None  # in Unterklassen setzen: Name des FK-Felds auf Galeriebild ("ordner" oder "termin")
    change_form_template = "admin/mitglieder/bild_bulk_upload_change_form.html"

    def _url_name(self, suffix):
        return f"{self.model._meta.app_label}_{self.model._meta.model_name}_{suffix}"

    def get_urls(self):
        eigene_urls = [
            path(
                "<int:object_id>/bilder-hochladen/",
                self.admin_site.admin_view(self.bilder_hochladen),
                name=self._url_name("bilder_hochladen"),
            ),
        ]
        return eigene_urls + super().get_urls()

    def bilder_hochladen(self, request, object_id):
        obj = get_object_or_404(self.model, pk=object_id)

        if request.method == "POST":
            dateien = request.FILES.getlist("bilder")
            for datei in dateien:
                Galeriebild.objects.create(
                    **{self.bild_fk_feld: obj}, bild=datei, hochgeladen_von=request.user,
                )
            messages.success(request, f"{len(dateien)} Bild(er) hochgeladen.")
            return redirect(f"admin:{self._url_name('change')}", object_id)

        return render(request, "admin/mitglieder/bilder_hochladen.html", {
            "opts": self.model._meta, "original": obj, "title": f"Bilder hochladen: {obj}",
        })


class TerminForm(forms.ModelForm):
    """Native Datum-/Uhrzeit-Picker für Beginn/Ende (kein Tippen von Punkten/Doppelpunkten nötig)."""

    # date_format="%Y-%m-%d": native <input type="date"> verlangt zwingend ISO-Format als value,
    # sonst zeigt der Browser das Feld leer an (das deutsche Locale-Format TT.MM.JJJJ funktioniert nicht).
    beginn = forms.SplitDateTimeField(
        label="Beginn",
        widget=forms.SplitDateTimeWidget(
            date_attrs={"type": "date"}, time_attrs={"type": "time"}, date_format="%Y-%m-%d",
        ),
    )
    ende = forms.SplitDateTimeField(
        label="Ende",
        required=False,
        widget=forms.SplitDateTimeWidget(
            date_attrs={"type": "date"}, time_attrs={"type": "time"}, date_format="%Y-%m-%d",
        ),
    )

    class Meta:
        model = Termin
        fields = "__all__"


class TerminAdminBase(LoeschLinkMixin, admin.ModelAdmin):
    """Gemeinsame Basis für die getrennten Training-/Veranstaltungs-Admins (gleiche DB-Tabelle)."""

    ART_WERT = None  # in Unterklassen setzen
    DUPLIKAT_FELDER = ["titel", "gruppe", "beginn", "ende", "ort", "beschreibung"]

    form = TerminForm
    filter_horizontal = ("wichtige_trainings",)
    list_display = (
        "titel", "gruppe_anzeige", "beginn", "ende", "ort", "erstellt_am",
        "anzahl_zusagen", "anzahl_absagen", "anwesenheit_link", "loeschen_link",
    )
    list_filter = ("gruppe",)
    search_fields = ("titel",)
    date_hierarchy = "beginn"
    ordering = ("beginn",)
    exclude = ("art",)
    change_list_template = "admin/mitglieder/termin_change_list.html"

    def gruppe_anzeige(self, obj):
        return obj.get_gruppe_display()

    gruppe_anzeige.short_description = "Gruppe"

    def _zusagen_link(self, obj, status):
        anzahl = obj.zusagen.filter(status=status).count()
        url = reverse("admin:mitglieder_zusage_changelist")
        url += f"?termin__id__exact={obj.pk}&status__exact={status}"
        return format_html('<a href="{}">{}</a>', url, anzahl)

    def anzahl_zusagen(self, obj):
        return self._zusagen_link(obj, Zusage.STATUS_ZUGESAGT)

    anzahl_zusagen.short_description = "Zusagen"

    def anzahl_absagen(self, obj):
        return self._zusagen_link(obj, Zusage.STATUS_ABGESAGT)

    anzahl_absagen.short_description = "Absagen"

    def anwesenheit_link(self, obj):
        url = reverse(f"admin:{self._url_name('anwesenheit')}", args=[obj.pk])
        return format_html('<a class="button" href="{}">📋 Anwesenheit</a>', url)

    anwesenheit_link.short_description = "Anwesenheit"

    change_form_template = "admin/mitglieder_termin_change_form.html"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "erstellt_von":
            kwargs["queryset"] = User.objects.filter(is_staff=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.art = self.ART_WERT
        if not obj.pk:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)
        if change and "_save_and_notify" in request.POST:
            from .signals import termin_update_benachrichtigen
            termin_update_benachrichtigen(obj)
            messages.success(request, "Mitglieder wurden per E-Mail über die Änderung informiert.")

    def _url_name(self, suffix):
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_{suffix}"

    def _changelist_redirect(self):
        return redirect(f"admin:{self._url_name('changelist')}")

    def get_urls(self):
        eigene_urls = [
            path("serie-erstellen/", self.admin_site.admin_view(self.serie_erstellen), name=self._url_name("serie")),
            path("duplikate/", self.admin_site.admin_view(self.duplikate_bereinigen), name=self._url_name("duplikate")),
            path("serie-bearbeiten/", self.admin_site.admin_view(self.serie_bearbeiten), name=self._url_name("serie_bearbeiten")),
            path("serie-loeschen/", self.admin_site.admin_view(self.serie_loeschen), name=self._url_name("serie_loeschen")),
            path("<int:object_id>/anwesenheit/", self.admin_site.admin_view(self.anwesenheit), name=self._url_name("anwesenheit")),
        ]
        return eigene_urls + super().get_urls()

    def anwesenheit(self, request, object_id):
        if not self.has_change_permission(request):
            raise PermissionDenied

        termin = get_object_or_404(self.model, pk=object_id)
        kinder = _relevante_kinder(termin.gruppe)

        if request.method == "POST":
            for kind in kinder:
                zusage, _ = Zusage.objects.get_or_create(taenzerin=kind, termin=termin)
                zusage.anwesend = request.POST.get(f"anwesend_{kind.id}") == "on"
                zusage.save()
            messages.success(request, f"Anwesenheit für '{termin.titel}' gespeichert.")
            return self._changelist_redirect()

        zusagen = {z.taenzerin_id: z for z in Zusage.objects.filter(termin=termin)}
        zeilen = []
        for kind in sorted(kinder, key=lambda k: k.vorname):
            zusage = zusagen.get(kind.id)
            zeilen.append({
                "kind": kind,
                "status": zusage.status if zusage else Zusage.STATUS_OFFEN,
                "anwesend": zusage.anwesend if zusage else None,
            })

        return render(
            request,
            "admin/mitglieder/anwesenheit.html",
            {"termin": termin, "zeilen": zeilen, "opts": self.model._meta, "title": f"Anwesenheit: {termin.titel}"},
        )

    def serie_loeschen(self, request):
        if not self.has_delete_permission(request):
            raise PermissionDenied

        titel_choices = [
            (t, t) for t in self.model.objects.order_by("titel").values_list("titel", flat=True).distinct()
        ]

        vorschau = None
        if request.method == "POST":
            form = SerieLoeschenForm(request.POST, titel_choices=titel_choices)
            if form.is_valid():
                daten = form.cleaned_data
                passende = self.model.objects.filter(titel=daten["titel"])
                if daten["ab_datum"]:
                    passende = passende.filter(beginn__date__gte=daten["ab_datum"])

                if request.POST.get("bestaetigt") == "1":
                    anzahl = passende.count()
                    passende.delete()
                    messages.success(request, f"{anzahl} Termine der Serie '{daten['titel']}' wurden gelöscht.")
                    return self._changelist_redirect()

                vorschau = {
                    "titel": daten["titel"],
                    "ab_datum": daten["ab_datum"],
                    "termine": list(passende.order_by("beginn")),
                }
        else:
            form = SerieLoeschenForm(titel_choices=titel_choices)

        return render(
            request,
            "admin/mitglieder/serie_loeschen.html",
            {"form": form, "vorschau": vorschau, "opts": self.model._meta, "title": "Terminserie löschen"},
        )

    def serie_bearbeiten(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        titel_choices = [
            (t, t) for t in self.model.objects.order_by("titel").values_list("titel", flat=True).distinct()
        ]

        if request.method == "POST":
            form = SerieBearbeitenForm(request.POST, titel_choices=titel_choices)
            if form.is_valid():
                daten = form.cleaned_data
                passende = self.model.objects.filter(titel=daten["titel"], beginn__date__gte=daten["ab_datum"])

                aktualisiert = 0
                for termin in passende:
                    geaendert = False
                    lokales_datum = timezone.localtime(termin.beginn).date()

                    if daten["neue_startzeit"]:
                        termin.beginn = timezone.make_aware(datetime.combine(lokales_datum, daten["neue_startzeit"]))
                        geaendert = True
                    if daten["neue_endzeit"]:
                        termin.ende = timezone.make_aware(datetime.combine(lokales_datum, daten["neue_endzeit"]))
                        geaendert = True
                    if daten["neuer_ort"]:
                        termin.ort = daten["neuer_ort"]
                        geaendert = True
                    if daten["neue_gruppe"]:
                        termin.gruppe = daten["neue_gruppe"]
                        geaendert = True
                    if daten["neue_beschreibung"]:
                        termin.beschreibung = daten["neue_beschreibung"]
                        geaendert = True

                    if geaendert:
                        termin.save()
                        aktualisiert += 1

                neu_erstellt = 0
                if daten["serie_verlaengern_bis"]:
                    letzter_termin = self.model.objects.filter(titel=daten["titel"]).order_by("-beginn").first()
                    if letzter_termin:
                        letzter_lokal = timezone.localtime(letzter_termin.beginn)
                        startzeit = daten["neue_startzeit"] or letzter_lokal.time()
                        endzeit = daten["neue_endzeit"] or (
                            timezone.localtime(letzter_termin.ende).time() if letzter_termin.ende else None
                        )
                        ort = daten["neuer_ort"] or letzter_termin.ort
                        gruppe = daten["neue_gruppe"] or letzter_termin.gruppe
                        beschreibung = daten["neue_beschreibung"] or letzter_termin.beschreibung

                        naechstes_datum = letzter_lokal.date() + timedelta(days=7)
                        while naechstes_datum <= daten["serie_verlaengern_bis"]:
                            neuer_beginn = timezone.make_aware(datetime.combine(naechstes_datum, startzeit))
                            neues_ende = (
                                timezone.make_aware(datetime.combine(naechstes_datum, endzeit)) if endzeit else None
                            )
                            self.model.objects.create(
                                titel=daten["titel"], art=self.ART_WERT, gruppe=gruppe,
                                beginn=neuer_beginn, ende=neues_ende, ort=ort,
                                beschreibung=beschreibung, erstellt_von=request.user,
                            )
                            neu_erstellt += 1
                            naechstes_datum += timedelta(days=7)

                teile = []
                if aktualisiert:
                    teile.append(f"{aktualisiert} Termine aktualisiert")
                if neu_erstellt:
                    teile.append(f"{neu_erstellt} neue Termine ergänzt")
                if not teile:
                    teile.append("keine Änderungen vorgenommen")
                messages.success(request, f"Serie '{daten['titel']}': " + ", ".join(teile) + ".")
                return self._changelist_redirect()
        else:
            form = SerieBearbeitenForm(titel_choices=titel_choices)

        return render(
            request,
            "admin/mitglieder/serie_bearbeiten.html",
            {"form": form, "opts": self.model._meta, "title": "Terminserie bearbeiten"},
        )

    def _duplikat_gruppen(self):
        return (
            self.model.objects.values(*self.DUPLIKAT_FELDER)
            .annotate(anzahl=Count("id"))
            .filter(anzahl__gt=1)
        )

    def duplikate_bereinigen(self, request):
        if not self.has_delete_permission(request):
            raise PermissionDenied

        gruppen = list(self._duplikat_gruppen())

        if request.method == "POST":
            geloescht = 0
            for gruppe in gruppen:
                filter_kwargs = {feld: gruppe[feld] for feld in self.DUPLIKAT_FELDER}
                kandidaten = list(
                    self.model.objects.filter(**filter_kwargs)
                    .annotate(n_zusagen=Count("zusagen", distinct=True), n_anmeldepunkte=Count("anmeldepunkte", distinct=True))
                    .order_by("-n_zusagen", "-n_anmeldepunkte", "id")
                    .values_list("id", flat=True)
                )
                zu_loeschen = kandidaten[1:]
                geloescht += len(zu_loeschen)
                self.model.objects.filter(id__in=zu_loeschen).delete()

            messages.success(request, f"{geloescht} doppelte Termine wurden entfernt.")
            return self._changelist_redirect()

        vorschau = []
        for gruppe in gruppen:
            filter_kwargs = {feld: gruppe[feld] for feld in self.DUPLIKAT_FELDER}
            beispiel = self.model.objects.filter(**filter_kwargs).order_by("id").first()
            vorschau.append({"termin": beispiel, "anzahl": gruppe["anzahl"]})

        return render(
            request,
            "admin/mitglieder/duplikate.html",
            {
                "vorschau": vorschau,
                "gesamt_ueberschuss": sum(v["anzahl"] - 1 for v in vorschau),
                "opts": self.model._meta,
                "title": "Doppelte Termine bereinigen",
            },
        )

    def serie_erstellen(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied

        if request.method == "POST":
            form = SerienTerminForm(request.POST)
            if form.is_valid():
                daten = form.cleaned_data
                wochentag = int(daten["wochentag"])
                aktuelles_datum = daten["start_datum"]
                aktuelles_datum += timedelta(days=(wochentag - aktuelles_datum.weekday()) % 7)

                erstellt = 0
                while aktuelles_datum <= daten["end_datum"]:
                    beginn = timezone.make_aware(datetime.combine(aktuelles_datum, daten["startzeit"]))
                    ende = None
                    if daten["endzeit"]:
                        ende = timezone.make_aware(datetime.combine(aktuelles_datum, daten["endzeit"]))
                    self.model.objects.create(
                        titel=daten["titel"],
                        art=self.ART_WERT,
                        gruppe=daten["gruppe"],
                        beginn=beginn,
                        ende=ende,
                        ort=daten["ort"],
                        beschreibung=daten["beschreibung"],
                        erstellt_von=request.user,
                    )
                    erstellt += 1
                    aktuelles_datum += timedelta(days=7)

                messages.success(request, f"{erstellt} Termine wurden angelegt.")
                return self._changelist_redirect()
        else:
            form = SerienTerminForm()

        return render(
            request,
            "admin/mitglieder/serie_erstellen.html",
            {"form": form, "opts": self.model._meta, "title": "Terminserie erstellen"},
        )


@admin.register(TrainingTermin)
class TrainingAdmin(TerminAdminBase):
    ART_WERT = Termin.ART_TRAINING
    change_list_template = "admin/mitglieder/training_change_list.html"
    exclude = TerminAdminBase.exclude + ("interne_notiz", "uhrzeit_unbekannt")

    def get_urls(self):
        eigene_urls = [
            path(
                "teilnahme-statistik/",
                self.admin_site.admin_view(self.teilnahme_statistik),
                name=self._url_name("teilnahme_statistik"),
            ),
        ]
        return eigene_urls + super().get_urls()

    def teilnahme_statistik(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied

        trainings_alle = Termin.objects.filter(art=Termin.ART_TRAINING)
        zeilen = []
        for kind in Taenzerin.objects.select_related("eltern"):
            if kind.gruppe:
                trainings = trainings_alle.filter(Q(gruppe=Termin.GRUPPE_BEIDE) | Q(gruppe=kind.gruppe))
            else:
                trainings = trainings_alle.filter(gruppe=Termin.GRUPPE_BEIDE)
            gesamt = trainings.count()
            zusagen_qs = Zusage.objects.filter(taenzerin=kind, termin__in=trainings)
            zugesagt = zusagen_qs.filter(status=Zusage.STATUS_ZUGESAGT).count()
            abgesagt = zusagen_qs.filter(status=Zusage.STATUS_ABGESAGT).count()
            offen = gesamt - zugesagt - abgesagt
            quote = round(zugesagt / gesamt * 100) if gesamt else None
            zeilen.append({
                "kind": kind, "gesamt": gesamt, "zugesagt": zugesagt,
                "abgesagt": abgesagt, "offen": offen, "quote": quote,
            })
        zeilen.sort(key=lambda z: (z["quote"] is None, -(z["quote"] or 0)))

        return render(
            request,
            "admin/mitglieder/teilnahme_statistik.html",
            {"zeilen": zeilen, "opts": self.model._meta, "title": "Teilnahme-Statistik Training"},
        )


@admin.register(VeranstaltungTermin)
class VeranstaltungAdmin(BildBulkUploadMixin, TerminAdminBase):
    ART_WERT = Termin.ART_VERANSTALTUNG
    bild_fk_feld = "termin"
    inlines = [AnmeldepunktInline, AufgabeInline, GaleriebildInline, GalerieordnerVeranstaltungInline]
    list_display = TerminAdminBase.list_display + ("offene_helferpunkte", "offene_aufgaben")
    change_list_template = "admin/mitglieder/veranstaltung_change_list.html"

    def loeschen_link(self, obj):
        """Versteckte Markierung mit dem Beginn-Zeitpunkt (als Unix-Millisekunden, um
        Datums-String-Parsing-Unterschiede zwischen Browsern zu vermeiden), damit die Liste
        per JS in offene/abgeschlossene Veranstaltungen aufgeteilt werden kann
        (siehe change_list_template)."""
        link = super().loeschen_link(obj)
        beginn_ms = round(obj.beginn.timestamp() * 1000)
        return format_html('<span data-beginn-ms="{}" style="display:none;"></span>{}', beginn_ms, link)

    loeschen_link.short_description = ""

    def offene_aufgaben(self, obj):
        anzahl = obj.aufgaben.filter(erledigt=False).count()
        if not anzahl:
            return "–"
        url = reverse("admin:mitglieder_aufgabe_changelist")
        url += f"?termin__id__exact={obj.pk}&erledigt__exact=0"
        return format_html('<a href="{}">{}</a>', url, anzahl)

    offene_aufgaben.short_description = "Offene To-Dos"

    def save_formset(self, request, form, formset, change):
        instanzen = formset.save(commit=False)
        # commit=False speichert Loeschungen NICHT automatisch (anders als bei einem
        # einzelnen ModelForm) - muessen wir hier explizit selbst ausfuehren.
        for geloescht in formset.deleted_objects:
            geloescht.delete()
        for instanz in instanzen:
            if isinstance(instanz, Aufgabe) and not instanz.pk:
                instanz.erstellt_von = request.user
            if isinstance(instanz, Galeriebild) and not instanz.pk:
                instanz.hochgeladen_von = request.user
            instanz.save()
        formset.save_m2m()

    def offene_helferpunkte(self, obj):
        offene = [a for a in obj.anmeldepunkte.all() if a.max_anzahl is not None and a.plaetze_frei > 0]
        if not offene:
            return "–"
        return format_html_join(
            "",
            '<div style="color:#b3261e; white-space:nowrap;">⚠️ {} ({} offen)</div>',
            ((a.titel, a.plaetze_frei) for a in offene),
        )

    offene_helferpunkte.short_description = "Noch offene Helferpunkte"


class AnmeldungInline(admin.TabularInline):
    model = Anmeldung
    extra = 0
    fields = ("eltern", "kommentar", "erstellt_am")
    readonly_fields = ("erstellt_am",)


class AnmeldepunktOffenFilter(admin.SimpleListFilter):
    title = "Status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return (("offen", "Noch offen (Plätze frei)"), ("voll", "Voll"))

    def queryset(self, request, queryset):
        if self.value() == "offen":
            ids = [a.pk for a in queryset if a.max_anzahl is not None and a.plaetze_frei > 0]
            return queryset.filter(pk__in=ids)
        if self.value() == "voll":
            ids = [a.pk for a in queryset if a.max_anzahl is not None and a.plaetze_frei == 0]
            return queryset.filter(pk__in=ids)
        return queryset


@admin.register(Anmeldepunkt)
class AnmeldepunktAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = (
        "titel", "termin", "mit_kommentar", "max_anzahl", "anzahl_angemeldet", "noch_offen", "loeschen_link",
    )
    list_filter = ("termin", "mit_kommentar", AnmeldepunktOffenFilter)
    inlines = [AnmeldungInline]

    def anzahl_angemeldet(self, obj):
        return obj.anmeldungen.count()

    anzahl_angemeldet.short_description = "Angemeldet"

    def noch_offen(self, obj):
        if obj.max_anzahl is None:
            return "unbegrenzt"
        if obj.plaetze_frei == 0:
            return format_html('<span style="color:#1a7a3c;">{}</span>', "✅ voll")
        return format_html('<span style="color:#b3261e;">⚠️ {} offen</span>', obj.plaetze_frei)

    noch_offen.short_description = "Noch offen"


class AufgabeErledigungInline(admin.TabularInline):
    model = AufgabeErledigung
    extra = 0
    readonly_fields = ("erledigt_am",)


@admin.register(Aufgabe)
class AufgabeAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = (
        "titel", "termin", "faellig_am", "sichtbar_fuer", "zugewiesen_an", "erledigt", "erstellt_von",
        "erstellt_am", "loeschen_link",
    )
    list_display_links = ("titel",)
    list_editable = ("erledigt",)
    list_filter = ("erledigt", "sichtbar_fuer", "zugewiesen_an", "termin")
    search_fields = ("titel", "beschreibung")
    ordering = ("erledigt", "faellig_am", "termin__beginn", "-erstellt_am")
    inlines = [AufgabeErledigungInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "zugewiesen_an":
            kwargs["queryset"] = User.objects.filter(is_staff=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(Zusage)
class ZusageAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = ("termin_datum", "termin", "taenzerin", "status", "anwesend", "aktualisiert_am", "loeschen_link")
    list_editable = ("anwesend",)
    list_filter = ("status", "anwesend", "termin")
    search_fields = ("taenzerin__vorname", "taenzerin__nachname")
    date_hierarchy = "termin__beginn"
    ordering = ("termin__beginn", "taenzerin__vorname")
    change_list_template = "admin/mitglieder/zusage_change_list.html"

    def termin_datum(self, obj):
        lokal = timezone.localtime(obj.termin.beginn)
        return format_html('<span data-tag="{}">{}</span>', lokal.date().isoformat(), lokal.strftime("%d.%m.%Y %H:%M"))

    termin_datum.short_description = "Datum"
    termin_datum.admin_order_field = "termin__beginn"


@admin.register(NewsPost)
class NewsPostAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = ("titel", "autor", "erstellt_am", "loeschen_link")
    readonly_fields = ("autor", "erstellt_am")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.autor = request.user
        super().save_model(request, obj, form, change)


@admin.register(Galerieordner)
class GalerieordnerAdmin(BildBulkUploadMixin, LoeschLinkMixin, admin.ModelAdmin):
    bild_fk_feld = "ordner"
    list_display = ("name", "veranstaltung", "anzahl_bilder", "erstellt_am", "loeschen_link")
    list_editable = ("veranstaltung",)
    list_filter = ("veranstaltung",)
    inlines = [GaleriebildOrdnerInline]

    def anzahl_bilder(self, obj):
        return obj.bilder.count()

    anzahl_bilder.short_description = "Bilder"


# Galeriebild hat keine eigene Admin-Seite - Bilder werden ausschließlich über die Inlines
# bei Galerie-Ordner/Veranstaltung verwaltet (Bearbeiten, Titelbild, Löschen, Bulk-Upload).

    def thumbnail(self, obj):
        if obj.bild:
            return format_html('<img src="{}" style="height:50px; border-radius:4px;">', obj.bild.url)
        return "–"

    thumbnail.short_description = "Bild"

    def vorschau(self, obj):
        if obj.bild:
            return format_html('<img src="{}" style="max-width:400px; border-radius:6px;">', obj.bild.url)
        return "–"

    vorschau.short_description = "Vorschau"

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.hochgeladen_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(Feedback)
class FeedbackAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = ("betreff_anzeige", "absender", "gelesen", "erstellt_am", "loeschen_link")
    list_display_links = ("betreff_anzeige",)
    list_editable = ("gelesen",)
    list_filter = ("gelesen",)
    readonly_fields = ("absender", "betreff", "nachricht", "erstellt_am")
    ordering = ("gelesen", "-erstellt_am")

    def betreff_anzeige(self, obj):
        return obj.betreff or obj.nachricht[:60]

    betreff_anzeige.short_description = "Betreff"

    def has_add_permission(self, request):
        return False


@admin.register(Nachricht)
class NachrichtAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = ("betreff_anzeige", "empfaenger", "gelesen", "erstellt_am", "loeschen_link")
    list_display_links = ("betreff_anzeige",)
    list_editable = ("gelesen",)
    list_filter = ("gelesen", "empfaenger")
    readonly_fields = ("absender", "erstellt_am")
    fields = ("empfaenger", "betreff", "nachricht", "gelesen", "absender", "erstellt_am")

    def betreff_anzeige(self, obj):
        return obj.betreff or obj.nachricht[:60]

    betreff_anzeige.short_description = "Betreff"

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.absender = request.user
        super().save_model(request, obj, form, change)


@admin.register(Ferienzeitraum)
class FerienzeitraumAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = ("name", "start_datum", "end_datum", "loeschen_link")
    ordering = ("start_datum",)


_get_app_list_ohne_anzahl = admin.site.get_app_list

# Diese Modelle wachsen unbegrenzt mit der Zeit (jedes Training/jede Zu-/Absage
# bleibt für immer in der DB) – die Anzahl davor waechst dadurch beliebig hoch
# und wird im Admin-Menü nicht angezeigt.
_MODELLE_OHNE_ANZAHL = (TrainingTermin, Zusage)


def _veranstaltungen_offen_abgeschlossen_text(model_name):
    jetzt = timezone.now()
    offen = VeranstaltungTermin.objects.filter(beginn__gte=jetzt).count()
    abgeschlossen = VeranstaltungTermin.objects.filter(beginn__lt=jetzt).count()
    return f"{offen} offene / {abgeschlossen} abgeschlossene {model_name}"


def _get_app_list_mit_anzahl(request, app_label=None):
    """Zeigt vor jedem Modellnamen im Admin-Menü die Anzahl der Datensätze an."""
    app_list = _get_app_list_ohne_anzahl(request, app_label=app_label)
    for app in app_list:
        for model in app["models"]:
            model_class = model.get("model")
            if model_class is None or model_class in _MODELLE_OHNE_ANZAHL:
                continue
            if model_class is VeranstaltungTermin:
                model["name"] = _veranstaltungen_offen_abgeschlossen_text(model["name"])
            else:
                anzahl = model_class._default_manager.count()
                model["name"] = f"{anzahl} {model['name']}"
    return app_list


admin.site.get_app_list = _get_app_list_mit_anzahl

# "Ausgewählte Objekte löschen" bleibt zusätzlich zum Muelleimer-Symbol pro Zeile
# (LoeschLinkMixin) erhalten, damit man z.B. bei langen Terminserien mehrere
# Eintraege auf einmal auswaehlen und loeschen kann.


_each_context_ohne_einladung = admin.site.each_context


def _each_context_mit_einladung(request):
    """Ergänzt Registrierungslink und Einladungscode im Admin-Kontext (für die Startseite)."""
    context = _each_context_ohne_einladung(request)
    context["einladungscode"] = settings.EINLADUNGSCODE
    context["registrierungslink"] = request.build_absolute_uri(reverse("registrieren"))
    return context


admin.site.each_context = _each_context_mit_einladung
admin.site.index_template = "admin/mitglieder_index.html"
