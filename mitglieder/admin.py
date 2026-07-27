from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import NewsPost, Taenzerin, Termin, Zusage


class TaenzerinInline(admin.TabularInline):
    model = Taenzerin
    fk_name = "eltern"
    extra = 0
    fields = ("vorname", "nachname", "schuhgroesse", "stammdaten_bestaetigt_am")
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
    list_display = ("vorname", "nachname", "eltern", "schuhgroesse", "stammdaten_status")
    list_filter = (TaenzerinStatusFilter,)
    search_fields = ("vorname", "nachname", "eltern__username", "eltern__first_name", "eltern__last_name")
    fields = (
        "eltern", "vorname", "nachname",
        "notfallkontakt_name", "notfallkontakt_telefon", "notfallkontakt_beziehung",
        "schuhgroesse", "allergien", "medikamente", "sonstige_hinweise",
        "stammdaten_bestaetigt_am",
    )

    def stammdaten_status(self, obj):
        return "fällig" if obj.bestaetigung_faellig else "aktuell"

    stammdaten_status.short_description = "Stammdaten"


@admin.register(Termin)
class TerminAdmin(admin.ModelAdmin):
    list_display = ("titel", "art", "beginn", "ort", "anzahl_zusagen", "anzahl_absagen")
    list_filter = ("art",)
    date_hierarchy = "beginn"
    ordering = ("-beginn",)

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


@admin.register(Zusage)
class ZusageAdmin(admin.ModelAdmin):
    list_display = ("termin", "taenzerin", "status", "aktualisiert_am")
    list_filter = ("status", "termin")
    search_fields = ("taenzerin__vorname", "taenzerin__nachname")


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
