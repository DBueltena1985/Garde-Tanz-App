from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Feedback, Taenzerin


class RegistrierenForm(UserCreationForm):
    einladungscode = forms.CharField(label="Einladungscode")
    email = forms.EmailField(label="E-Mail", required=False)
    first_name = forms.CharField(label="Vorname", required=False)
    last_name = forms.CharField(label="Nachname", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    field_order = ["username", "first_name", "last_name", "email", "password1", "password2", "einladungscode"]

    def clean_einladungscode(self):
        code = self.cleaned_data.get("einladungscode", "")
        if code != settings.EINLADUNGSCODE:
            raise forms.ValidationError("Der Einladungscode ist nicht korrekt.")
        return code


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


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ["betreff", "nachricht"]
        labels = {"betreff": "Betreff (optional)", "nachricht": "Nachricht"}
        widgets = {"nachricht": forms.Textarea(attrs={"rows": 5})}


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
