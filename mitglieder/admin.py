from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Anmeldepunkt, Anmeldung, Aufgabe, NewsPost, Taenzerin, Termin, TrainingTermin, VeranstaltungTermin, Zusage,
)


class TaenzerinInline(admin.TabularInline):
    model = Taenzerin
    fk_name = "eltern"
    extra = 0
    fields = ("vorname", "nachname", "schuhgroesse", "kleidergroesse", "stammdaten_bestaetigt_am")
    show_change_link = True


class CustomUserAdmin(UserAdmin):
    inlines = [TaenzerinInline]
    list_display = ("username", "first_name", "last_name", "is_staff", "is_superuser", "anzahl_kinder")

    def anzahl_kinder(self, obj):
        return obj.kinder.count()

    anzahl_kinder.short_description = "Kinder"


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
class TaenzerinAdmin(admin.ModelAdmin):
    list_display = (
        "vorname", "nachname", "eltern", "gruppe_anzeige",
        "notfallkontakt_anruf", "schuhgroesse", "kleidergroesse", "stammdaten_status",
    )
    list_filter = (TaenzerinStatusFilter,)
    search_fields = ("vorname", "nachname", "eltern__username", "eltern__first_name", "eltern__last_name")
    fields = (
        "eltern", "vorname", "nachname", "geburtsjahr",
        "notfallkontakt_name", "notfallkontakt_telefon", "notfallkontakt_beziehung",
        "schuhgroesse", "kleidergroesse", "allergien", "medikamente", "sonstige_hinweise",
        "stammdaten_bestaetigt_am",
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
    fields = ("titel", "beschreibung", "max_anzahl", "mit_kommentar")


class TerminAdminBase(admin.ModelAdmin):
    """Gemeinsame Basis für die getrennten Training-/Veranstaltungs-Admins (gleiche DB-Tabelle)."""

    ART_WERT = None  # in Unterklassen setzen
    DUPLIKAT_FELDER = ["titel", "gruppe", "beginn", "ende", "ort", "beschreibung"]

    list_display = ("titel", "gruppe_anzeige", "beginn", "ende", "ort", "erstellt_am", "anzahl_zusagen", "anzahl_absagen")
    list_filter = ("gruppe",)
    search_fields = ("titel",)
    date_hierarchy = "beginn"
    ordering = ("-beginn",)
    exclude = ("art",)
    change_list_template = "admin/mitglieder/termin_change_list.html"

    def gruppe_anzeige(self, obj):
        return obj.get_gruppe_display()

    gruppe_anzeige.short_description = "Gruppe"

    def anzahl_zusagen(self, obj):
        return obj.zusagen.filter(status=Zusage.STATUS_ZUGESAGT).count()

    anzahl_zusagen.short_description = "Zusagen"

    def anzahl_absagen(self, obj):
        return obj.zusagen.filter(status=Zusage.STATUS_ABGESAGT).count()

    anzahl_absagen.short_description = "Absagen"

    def save_model(self, request, obj, form, change):
        obj.art = self.ART_WERT
        if not obj.pk:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)

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
        ]
        return eigene_urls + super().get_urls()

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


@admin.register(VeranstaltungTermin)
class VeranstaltungAdmin(TerminAdminBase):
    ART_WERT = Termin.ART_VERANSTALTUNG
    inlines = [AnmeldepunktInline]
    list_display = TerminAdminBase.list_display + ("offene_helferpunkte",)

    def offene_helferpunkte(self, obj):
        offene = [a for a in obj.anmeldepunkte.all() if a.max_anzahl is not None and a.plaetze_frei > 0]
        if not offene:
            return "–"
        return format_html(
            '<span style="color:#b3261e;">⚠️ {}</span>',
            ", ".join(f"{a.titel} ({a.plaetze_frei})" for a in offene),
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
class AnmeldepunktAdmin(admin.ModelAdmin):
    list_display = ("titel", "termin", "mit_kommentar", "max_anzahl", "anzahl_angemeldet", "noch_offen")
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


@admin.register(Aufgabe)
class AufgabeAdmin(admin.ModelAdmin):
    list_display = ("titel", "termin", "erledigt", "erstellt_von", "erstellt_am")
    list_display_links = ("titel",)
    list_editable = ("erledigt",)
    list_filter = ("erledigt", "termin")
    search_fields = ("titel", "beschreibung")
    ordering = ("erledigt", "termin__beginn", "-erstellt_am")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(Zusage)
class ZusageAdmin(admin.ModelAdmin):
    list_display = ("termin_datum", "termin", "taenzerin", "status", "aktualisiert_am")
    list_filter = ("status", "termin")
    search_fields = ("taenzerin__vorname", "taenzerin__nachname")
    date_hierarchy = "termin__beginn"
    ordering = ("termin__beginn", "taenzerin__vorname")

    def termin_datum(self, obj):
        return obj.termin.beginn

    termin_datum.short_description = "Datum"
    termin_datum.admin_order_field = "termin__beginn"


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("titel", "autor", "erstellt_am")
    readonly_fields = ("autor", "erstellt_am")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.autor = request.user
        super().save_model(request, obj, form, change)


_get_app_list_ohne_anzahl = admin.site.get_app_list


def _get_app_list_mit_anzahl(request, app_label=None):
    """Zeigt vor jedem Modellnamen im Admin-Menü die Anzahl der Datensätze an."""
    app_list = _get_app_list_ohne_anzahl(request, app_label=app_label)
    for app in app_list:
        for model in app["models"]:
            model_class = model.get("model")
            if model_class is not None:
                anzahl = model_class._default_manager.count()
                model["name"] = f"{anzahl} {model['name']}"
    return app_list


admin.site.get_app_list = _get_app_list_mit_anzahl


_each_context_ohne_einladung = admin.site.each_context


def _each_context_mit_einladung(request):
    """Ergänzt Registrierungslink und Einladungscode im Admin-Kontext (für die Startseite)."""
    context = _each_context_ohne_einladung(request)
    context["einladungscode"] = settings.EINLADUNGSCODE
    context["registrierungslink"] = request.build_absolute_uri(reverse("registrieren"))
    return context


admin.site.each_context = _each_context_mit_einladung
admin.site.index_template = "admin/mitglieder_index.html"
