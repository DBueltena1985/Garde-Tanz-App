from django.contrib import admin

from mitglieder.admin import LoeschLinkMixin

from .models import Formular


@admin.register(Formular)
class FormularAdmin(LoeschLinkMixin, admin.ModelAdmin):
    list_display = ("titel", "hochgeladen_am", "loeschen_link")
    ordering = ("titel",)
