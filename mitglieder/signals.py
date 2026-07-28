from django.db.models.signals import post_save, pre_delete

from .models import Taenzerin, Termin, TrainingTermin, VeranstaltungTermin, Zusage
from .utils import sichere_mail_senden

# Django sendet Signale für Proxy-Modelle mit dem Proxy als "sender" (nicht dem
# Basis-Modell). Da Termine im Admin über die Proxys TrainingTermin/VeranstaltungTermin
# angelegt/gelöscht werden, müssen wir auf alle drei Klassen hören, sonst feuert das Signal nie.
TERMIN_MODELLE = (Termin, TrainingTermin, VeranstaltungTermin)


def _zeitraum_text(termin):
    text = f"{termin.beginn:%d.%m.%Y %H:%M}"
    if termin.ende:
        text += f"–{termin.ende:%H:%M}"
    text += " Uhr"
    if termin.ort:
        text += f"\nOrt: {termin.ort}"
    return text


def _eltern_emails_fuer_kind(kind):
    """Alle E-Mails der Benutzer, die dieses Kind sehen/verwalten dürfen (Eltern + Mitverwalter)."""
    emails = {u.email for u in kind.mitverwaltet_von.all() if u.email}
    if kind.eltern.email:
        emails.add(kind.eltern.email)
    return emails


def termin_absage_benachrichtigen(sender, instance, **kwargs):
    """Informiert Eltern per E-Mail, wenn ein Termin gestrichen wird, für den zugesagt wurde."""
    zusagen = instance.zusagen.filter(status=Zusage.STATUS_ZUGESAGT).select_related("taenzerin__eltern").prefetch_related(
        "taenzerin__mitverwaltet_von"
    )
    for zusage in zusagen:
        for email in _eltern_emails_fuer_kind(zusage.taenzerin):
            sichere_mail_senden(
                subject=f"Termin abgesagt: {instance.titel}",
                message=(
                    f"Hallo,\n\n"
                    f"folgender Termin, für den {zusage.taenzerin.vorname} zugesagt hatte, wurde gestrichen:\n\n"
                    f"{instance.titel} ({instance.get_art_display()})\n"
                    f"{_zeitraum_text(instance)}\n\n"
                    "Bitte den Wegfall entsprechend einplanen."
                ),
                from_email=None,
                recipient_list=[email],
            )


def neue_veranstaltung_benachrichtigen(sender, instance, created, **kwargs):
    """Informiert passende Eltern per E-Mail über neu angelegte Veranstaltungen."""
    if not created or instance.art != Termin.ART_VERANSTALTUNG:
        return

    empfaenger_emails = set()
    for kind in Taenzerin.objects.select_related("eltern").prefetch_related("mitverwaltet_von"):
        if instance.gruppe == Termin.GRUPPE_BEIDE or kind.gruppe == instance.gruppe:
            empfaenger_emails |= _eltern_emails_fuer_kind(kind)

    for email in empfaenger_emails:
        sichere_mail_senden(
            subject=f"Neue Veranstaltung: {instance.titel}",
            message=(
                f"Es gibt eine neue Veranstaltung:\n\n"
                f"{instance.titel}\n"
                f"{_zeitraum_text(instance)}"
                + (f"\n\n{instance.beschreibung}" if instance.beschreibung else "")
                + "\n\nLogg dich in der Garde-Tanz-App ein, um zu- oder abzusagen."
            ),
            from_email=None,
            recipient_list=[email],
        )


for _modell in TERMIN_MODELLE:
    pre_delete.connect(termin_absage_benachrichtigen, sender=_modell)
    post_save.connect(neue_veranstaltung_benachrichtigen, sender=_modell)
