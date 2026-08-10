import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.urls import reverse

logger = logging.getLogger("mitglieder")

TRAINERTEAM_GRUPPENNAME = "Trainerteam"


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


def trainer_und_orga_emails():
    """E-Mails von Trainerinnen (Gruppe 'Trainerteam') und Orga-Team (is_staff)."""
    from django.contrib.auth.models import User

    emails = set(
        User.objects.filter(Q(is_staff=True) | Q(groups__name=TRAINERTEAM_GRUPPENNAME))
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if settings.ADMIN_BENACHRICHTIGUNGS_EMAIL:
        emails.add(settings.ADMIN_BENACHRICHTIGUNGS_EMAIL)
    return emails


def absolute_url(url_name, *args, fragment=""):
    """Baut eine absolute URL (fuer Mails aus Management-Commands, wo es keinen Request
    gibt, aus dem man das sonst per request.build_absolute_uri() ableiten koennte)."""
    url = f"{settings.SITE_URL}{reverse(url_name, args=args)}"
    return f"{url}#{fragment}" if fragment else url


def benutzer_name(user):
    """Klarname eines Benutzers (Vor-/Nachname), mit Fallback auf Benutzername falls kein Name hinterlegt ist."""
    if not user:
        return ""
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.username
