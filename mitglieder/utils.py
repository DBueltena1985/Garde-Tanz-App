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


def eltern_emails_fuer_kind(kind):
    """Alle E-Mails der Benutzer, die dieses Kind sehen/verwalten dürfen (Eltern + Mitverwalter)."""
    emails = {u.email for u in kind.mitverwaltet_von.all() if u.email}
    if kind.eltern.email:
        emails.add(kind.eltern.email)
    return emails


def benutzer_name(user):
    """Klarname eines Benutzers (Vor-/Nachname), mit Fallback auf Benutzername falls kein Name hinterlegt ist."""
    if not user:
        return ""
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.username
