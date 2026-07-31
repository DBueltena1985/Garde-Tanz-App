from django.contrib import admin

from .models import Formular


@admin.register(Formular)
class FormularAdmin(admin.ModelAdmin):
    list_display = ("titel", "reihenfolge", "hochgeladen_am")
    list_editable = ("reihenfolge",)
    ordering = ("reihenfolge", "titel")
