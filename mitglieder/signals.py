from django.contrib.auth.models import Group, User
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.utils import timezone

from .models import Nachricht, NewsPost, Taenzerin, Termin, TrainingTermin, VeranstaltungTermin, Zusage
from .utils import eltern_emails_fuer_kind, sichere_mail_senden

CREATOR_GRUPPENNAME = "Creator"
TRAINERTEAM_GRUPPENNAME = "Trainerteam"

# Django sendet Signale für Proxy-Modelle mit dem Proxy als "sender" (nicht dem
# Basis-Modell). Da Termine im Admin über die Proxys TrainingTermin/VeranstaltungTermin
# angelegt/gelöscht werden, müssen wir auf alle drei Klassen hören, sonst feuert das Signal nie.
TERMIN_MODELLE = (Termin, TrainingTermin, VeranstaltungTermin)


def _zeitraum_text(termin):
    beginn_lokal = timezone.localtime(termin.beginn)
    text = f"{beginn_lokal:%d.%m.%Y %H:%M}"
    if termin.ende:
        text += f"–{timezone.localtime(termin.ende):%H:%M}"
    text += " Uhr"
    if termin.ort:
        text += f"\nOrt: {termin.ort}"
    return text


def _alle_kinder_emails(gruppen=None):
    """E-Mails aller Eltern/Mitverwalter, optional eingeschränkt auf bestimmte Gruppen
    (leer/None = gilt für alle Gruppen)."""
    gruppen_ids = {g.id for g in gruppen} if gruppen else set()
    empfaenger_emails = set()
    for kind in Taenzerin.objects.select_related("eltern").prefetch_related("mitverwaltet_von"):
        if not gruppen_ids or (kind.gruppe and kind.gruppe.id in gruppen_ids):
            empfaenger_emails |= eltern_emails_fuer_kind(kind)
    return empfaenger_emails


def termin_absage_benachrichtigen(sender, instance, **kwargs):
    """Informiert Eltern per E-Mail, wenn ein Termin gestrichen wird, für den zugesagt wurde."""
    zusagen = instance.zusagen.filter(status=Zusage.STATUS_ZUGESAGT).select_related("taenzerin__eltern").prefetch_related(
        "taenzerin__mitverwaltet_von"
    )
    for zusage in zusagen:
        for email in eltern_emails_fuer_kind(zusage.taenzerin):
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


def neue_veranstaltung_benachrichtigen(instance):
    """Informiert passende Eltern per E-Mail über eine neu angelegte Veranstaltung.
    Wird explizit aus dem Admin aufgerufen (in save_related, NACH dem Speichern der
    Gruppen-Auswahl) statt über ein post_save-Signal, da beim Anlegen die
    Gruppen-Zuordnung (ManyToMany) erst nach dem eigentlichen obj.save() gespeichert wird."""
    for email in _alle_kinder_emails(instance.gruppen.all()):
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


def termin_update_benachrichtigen(instance):
    """Informiert passende Eltern per E-Mail über eine Aktualisierung eines Termins.
    Wird NICHT automatisch bei jedem Speichern ausgelöst, sondern nur, wenn im Admin
    bewusst der Button 'Speichern und Mitglieder benachrichtigen' genutzt wurde."""
    for email in _alle_kinder_emails(instance.gruppen.all()):
        sichere_mail_senden(
            subject=f"Termin aktualisiert: {instance.titel}",
            message=(
                f"Es gibt eine Aktualisierung zu folgendem Termin:\n\n"
                f"{instance.titel} ({instance.get_art_display()})\n"
                f"{_zeitraum_text(instance)}"
                + (f"\n\n{instance.beschreibung}" if instance.beschreibung else "")
                + "\n\nLogg dich in der Garde-Tanz-App ein, um die Details zu sehen."
            ),
            from_email=None,
            recipient_list=[email],
        )


def neue_news_benachrichtigen(sender, instance, created, **kwargs):
    """Informiert alle Mitglieder per E-Mail über neue News-Beiträge."""
    if not created:
        return

    for email in _alle_kinder_emails():
        sichere_mail_senden(
            subject=f"Neuer Beitrag: {instance.titel}",
            message=(
                f"Es gibt einen neuen Beitrag in der Garde-Tanz-App:\n\n"
                f"{instance.titel}\n\n"
                f"{instance.text}\n\n"
                "Logg dich ein, um mehr zu sehen."
            ),
            from_email=None,
            recipient_list=[email],
        )


def neue_nachricht_benachrichtigen(sender, instance, created, **kwargs):
    """Informiert den Empfaenger per E-Mail ueber eine neue Nachricht von Admin/Orgateam."""
    if not created or not instance.empfaenger.email:
        return

    sichere_mail_senden(
        subject=f"Neue Nachricht: {instance.betreff}" if instance.betreff else "Neue Nachricht in der Garde-Tanz-App",
        message=(
            f"Hallo {instance.empfaenger.first_name or instance.empfaenger.username},\n\n"
            f"du hast eine neue Nachricht erhalten:\n\n"
            f"{instance.nachricht}\n\n"
            "Logg dich in der Garde-Tanz-App ein, um sie zu lesen."
        ),
        from_email=None,
        recipient_list=[instance.empfaenger.email],
    )


def creator_gruppe_macht_superuser(sender, instance, action, pk_set, **kwargs):
    """Wer der Gruppe 'Creator' hinzugefuegt wird, bekommt automatisch Superuser-/Staff-Status -
    Django-Gruppen koennen das nicht selbst vergeben (nur einzelne Permissions), daher hier per Signal."""
    if action != "post_add":
        return
    try:
        creator_gruppe = Group.objects.get(name=CREATOR_GRUPPENNAME)
    except Group.DoesNotExist:
        return
    # Bei bereits bestehender Mitgliedschaft ist pk_set nach einem erneuten .add() leer (Django fuegt
    # nur tatsaechlich NEUE Zeilen ein) - deshalb zusaetzlich direkt die aktuelle Mitgliedschaft
    # pruefen, sonst wird is_staff/is_superuser bei jedem weiteren Speichern faelschlich uebersprungen.
    ist_mitglied = creator_gruppe.pk in pk_set or instance.groups.filter(pk=creator_gruppe.pk).exists()
    if not ist_mitglied:
        return
    if not instance.is_superuser or not instance.is_staff:
        instance.is_superuser = True
        instance.is_staff = True
        instance.save(update_fields=["is_superuser", "is_staff"])


def trainerteam_gruppe_macht_staff(sender, instance, action, pk_set, **kwargs):
    """Wer der Gruppe 'Trainerteam' hinzugefuegt wird, bekommt Staff-Status (fuer den Admin-Login),
    aber bewusst KEINEN Superuser-Status - die Gruppe soll volle Rechte per einzelnen Berechtigungen
    geben, nicht das komplette Ueberspringen aller Pruefungen."""
    if action != "post_add":
        return
    try:
        trainerteam_gruppe = Group.objects.get(name=TRAINERTEAM_GRUPPENNAME)
    except Group.DoesNotExist:
        return
    # Siehe Kommentar in creator_gruppe_macht_superuser: bei bereits bestehender Mitgliedschaft
    # ist pk_set leer, deshalb zusaetzlich die tatsaechliche Mitgliedschaft direkt pruefen.
    ist_mitglied = trainerteam_gruppe.pk in pk_set or instance.groups.filter(pk=trainerteam_gruppe.pk).exists()
    if not ist_mitglied:
        return
    if not instance.is_staff:
        instance.is_staff = True
        instance.save(update_fields=["is_staff"])


for _modell in TERMIN_MODELLE:
    pre_delete.connect(termin_absage_benachrichtigen, sender=_modell)

post_save.connect(neue_news_benachrichtigen, sender=NewsPost)
post_save.connect(neue_nachricht_benachrichtigen, sender=Nachricht)
m2m_changed.connect(creator_gruppe_macht_superuser, sender=User.groups.through)
m2m_changed.connect(trainerteam_gruppe_macht_staff, sender=User.groups.through)
