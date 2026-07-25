from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import NewsPost, Profil, Termin, Zusage


class ProfilInline(admin.StackedInline):
    model = Profil
    can_delete = False
    verbose_name_plural = "Stammdaten"
    fields = (
        "notfallkontakt_name",
        "notfallkontakt_telefon",
        "notfallkontakt_beziehung",
        "schuhgroesse",
        "allergien",
        "medikamente",
        "sonstige_hinweise",
        "stammdaten_bestaetigt_am",
    )


class ProfilStatusFilter(admin.SimpleListFilter):
    title = "Stammdaten-Status"
    parameter_name = "stammdaten_status"

    def lookups(self, request, model_admin):
        return (("faellig", "Bestätigung fällig (>90 Tage / nie)"),)

    def queryset(self, request, queryset):
        if self.value() == "faellig":
            return [u for u in queryset if hasattr(u, "profil") and u.profil.bestaetigung_faellig]
        return queryset


class CustomUserAdmin(UserAdmin):
    inlines = [ProfilInline]
    list_display = ("username", "first_name", "last_name", "is_staff", "stammdaten_status")
    list_filter = UserAdmin.list_filter + (ProfilStatusFilter,)

    def stammdaten_status(self, obj):
        if not hasattr(obj, "profil"):
            return "kein Profil"
        return "fällig" if obj.profil.bestaetigung_faellig else "aktuell"

    stammdaten_status.short_description = "Stammdaten"


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


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
    list_display = ("termin", "mitglied", "status", "aktualisiert_am")
    list_filter = ("status", "termin")
    search_fields = ("mitglied__username", "mitglied__first_name", "mitglied__last_name")


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("titel", "autor", "erstellt_am")
    readonly_fields = ("autor", "erstellt_am")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.autor = request.user
        super().save_model(request, obj, form, change)
