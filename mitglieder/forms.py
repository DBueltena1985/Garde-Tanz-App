from django import forms

from .models import Taenzerin


class TaenzerinForm(forms.ModelForm):
    class Meta:
        model = Taenzerin
        fields = [
            "vorname",
            "nachname",
            "notfallkontakt_name",
            "notfallkontakt_telefon",
            "notfallkontakt_beziehung",
            "schuhgroesse",
            "allergien",
            "medikamente",
            "sonstige_hinweise",
        ]
        widgets = {
            "allergien": forms.Textarea(attrs={"rows": 3}),
            "medikamente": forms.Textarea(attrs={"rows": 3}),
            "sonstige_hinweise": forms.Textarea(attrs={"rows": 3}),
        }
