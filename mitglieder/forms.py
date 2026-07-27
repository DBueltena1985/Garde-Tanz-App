from django import forms
from django.contrib.auth.models import User

from .models import Taenzerin


class KontoForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        labels = {
            "username": "Benutzername",
            "first_name": "Vorname",
            "last_name": "Nachname",
            "email": "E-Mail",
        }


class TaenzerinForm(forms.ModelForm):
    class Meta:
        model = Taenzerin
        fields = [
            "vorname",
            "nachname",
            "geburtsjahr",
            "notfallkontakt_name",
            "notfallkontakt_telefon",
            "notfallkontakt_beziehung",
            "schuhgroesse",
            "kleidergroesse",
            "allergien",
            "medikamente",
            "sonstige_hinweise",
        ]
        widgets = {
            "allergien": forms.Textarea(attrs={"rows": 3}),
            "medikamente": forms.Textarea(attrs={"rows": 3}),
            "sonstige_hinweise": forms.Textarea(attrs={"rows": 3}),
        }
