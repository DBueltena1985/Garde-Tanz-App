import logging

from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Feedback, Taenzerin

logger = logging.getLogger("mitglieder")


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


class FamilieEinladenForm(UserCreationForm):
    email = forms.EmailField(label="E-Mail", required=False)
    first_name = forms.CharField(label="Vorname", required=False)
    last_name = forms.CharField(label="Nachname", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    field_order = ["username", "first_name", "last_name", "email", "password1", "password2"]


class SicherePasswordResetForm(PasswordResetForm):
    """Wie PasswordResetForm, aber ein E-Mail-Fehler (z.B. Brevo down) darf die Anfrage
    nicht mit einem Server-Fehler abbrechen (gleiches Prinzip wie sichere_mail_senden)."""

    def send_mail(self, *args, **kwargs):
        try:
            super().send_mail(*args, **kwargs)
        except Exception:
            logger.exception("Passwort-Reset-Mail fehlgeschlagen")


class BenutzernameVergessenForm(forms.Form):
    email = forms.EmailField(label="E-Mail-Adresse")


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
            "nutzer",
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
        labels = {
            "nutzer": "Gehört zu Benutzerkonto",
        }
        help_texts = {
            "nutzer": "Falls dieser Eintrag zu einem eigenen Login (z.B. dir selbst oder einem "
            "verbundenen Familienmitglied) gehört, statt rein von dir verwaltet zu werden.",
        }

    def __init__(self, *args, moegliche_nutzer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if moegliche_nutzer is not None:
            self.fields["nutzer"].queryset = moegliche_nutzer
            self.fields["nutzer"].required = False
            self.fields["nutzer"].empty_label = "– niemandem zugeordnet –"
