from datetime import datetime, timedelta

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from .models import NewsPost, Taenzerin, Termin, Zusage


class TaenzerinInline(admin.TabularInline):
    model = Taenzerin
    fk_name = "eltern"
    extra = 0
    fields = ("vorname", "nachname", "schuhgroesse", "kleidergroesse", "stammdaten_bestaetigt_am")
    show_change_link = True


class CustomUserAdmin(UserAdmin):
    inlines = [TaenzerinInline]
    list_display = ("username", "first_name", "last_name", "is_staff", "anzahl_kinder")

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
    art = forms.ChoiceField(label="Art", choices=Termin.ART_CHOICES)
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


@admin.register(Termin)
class TerminAdmin(admin.ModelAdmin):
    list_display = ("titel", "art", "gruppe_anzeige", "beginn", "ende", "ort", "anzahl_zusagen", "anzahl_absagen")
    list_filter = ("art", "gruppe")
    date_hierarchy = "beginn"
    ordering = ("-beginn",)

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
        if not obj.pk:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        eigene_urls = [
            path("serie-erstellen/", self.admin_site.admin_view(self.serie_erstellen), name="mitglieder_termin_serie"),
        ]
        return eigene_urls + super().get_urls()

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
                    Termin.objects.create(
                        titel=daten["titel"],
                        art=daten["art"],
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
                return redirect("admin:mitglieder_termin_changelist")
        else:
            form = SerienTerminForm()

        return render(
            request,
            "admin/mitglieder/serie_erstellen.html",
            {"form": form, "opts": self.model._meta, "title": "Terminserie erstellen"},
        )


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
