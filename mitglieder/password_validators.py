import re

from django.core.exceptions import ValidationError


class KomplexitaetValidator:
    """Verlangt mindestens einen Großbuchstaben, eine Zahl und ein Sonderzeichen."""

    def validate(self, password, user=None):
        fehlt = []
        if not re.search(r'[A-Z]', password):
            fehlt.append("einen Großbuchstaben")
        if not re.search(r'[0-9]', password):
            fehlt.append("eine Zahl")
        if not re.search(r'[^A-Za-z0-9]', password):
            fehlt.append("ein Sonderzeichen")

        if fehlt:
            raise ValidationError(
                "Das Passwort muss zusätzlich " + ", ".join(fehlt) + " enthalten.",
                code="password_no_complexity",
            )

    def get_help_text(self):
        return "Das Passwort muss mindestens einen Großbuchstaben, eine Zahl und ein Sonderzeichen enthalten."
