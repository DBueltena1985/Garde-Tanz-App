import logging

from django.core.mail import send_mail

logger = logging.getLogger("mitglieder")


def sichere_mail_senden(**kwargs):
    """Wie send_mail(), aber ein Fehler beim Versand (z.B. Brevo-API nicht erreichbar)
    bricht die aufrufende Aktion (Registrierung, Termin speichern, Erinnerungs-Cron, ...)
    nicht mit einem Server-Fehler ab, sondern wird nur geloggt."""
    try:
        send_mail(**kwargs)
    except Exception:
        logger.exception("E-Mail-Versand fehlgeschlagen (Betreff: %s)", kwargs.get("subject"))
