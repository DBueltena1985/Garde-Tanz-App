from django import forms

from .models import Profil


class ProfilForm(forms.ModelForm):
    class Meta:
        model = Profil
        fields = [
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
