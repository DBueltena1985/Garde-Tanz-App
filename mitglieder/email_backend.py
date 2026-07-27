import json
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoAPIBackend(BaseEmailBackend):
    """Verschickt E-Mails über die Brevo-HTTP-API statt per SMTP.

    Notwendig, weil ausgehende SMTP-Verbindungen auf dem kostenlosen
    PythonAnywhere-Plan blockiert sind, HTTPS-Aufrufe an die Brevo-API aber nicht.
    """

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, "BREVO_API_KEY", "")
        if not api_key:
            if not self.fail_silently:
                raise ValueError("BREVO_API_KEY ist nicht gesetzt.")
            return 0

        gesendet = 0
        for message in email_messages:
            try:
                self._sende_einzeln(message, api_key)
                gesendet += 1
            except (HTTPError, URLError, ValueError, KeyError):
                if not self.fail_silently:
                    raise
        return gesendet

    def _sende_einzeln(self, message, api_key):
        absender_name, absender_email = parseaddr(message.from_email)
        daten = {
            "sender": {"email": absender_email, "name": absender_name or absender_email},
            "to": [{"email": adresse} for adresse in message.to],
            "subject": message.subject,
            "textContent": message.body,
        }
        request = Request(
            BREVO_API_URL,
            data=json.dumps(daten).encode("utf-8"),
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=10) as antwort:
            antwort.read()
