import calendar
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .feiertage import bayerische_feiertage
from .forms import (
    BenutzernameVergessenForm, FamilieEinladenForm, FeedbackForm, KontoForm, ProfilForm, RegistrierenForm,
    TaenzerinForm,
)
from .models import (
    Anmeldepunkt, Anmeldung, Aufgabe, AufgabeErledigung, Ferienzeitraum, Galeriebild, Galerieordner, Nachricht,
    NewsPost, Profil, Taenzerin, Termin, Zusage,
)
from .utils import benutzer_name, sichere_mail_senden

FAMILIEN_EINLADUNG_SALT = "familien-einladung"


def _familien_einladungs_token(user):
    return signing.dumps(user.id, salt=FAMILIEN_EINLADUNG_SALT)


def _einladendes_konto_aus_token(token):
    try:
        user_id = signing.loads(token, salt=FAMILIEN_EINLADUNG_SALT)
    except signing.BadSignature:
        return None
    return User.objects.filter(id=user_id).first()


def _kinder_fuer_nutzer(user):
    """Kinder, die ein Benutzer sehen/verwalten darf: eigene, mitverwaltete und der eigene Taenzerin-Eintrag."""
    return Taenzerin.objects.filter(Q(eltern=user) | Q(mitverwaltet_von=user) | Q(nutzer=user)).distinct()


def _eigene_taenzerin(user):
    """Der Taenzerin-Eintrag, der zum Login-Konto des Benutzers selbst gehört (falls vorhanden)."""
    return Taenzerin.objects.filter(nutzer=user).first()


def _kinder_fuer_termine(user):
    """Wie _kinder_fuer_nutzer, aber ein Konto, das selbst eine Tänzerin ist, sieht dort nur sich
    selbst und nicht zusätzlich verwaltete Geschwister."""
    eigene = _eigene_taenzerin(user)
    if eigene:
        return Taenzerin.objects.filter(pk=eigene.pk)
    return _kinder_fuer_nutzer(user)


def _erlaubte_aufgaben_zielgruppen(user):
    """None = alles sichtbar (Team). Sonst Liste der sichtbar_fuer-Werte, die dieser Benutzer sehen darf."""
    if user.is_staff:
        return None
    if _eigene_taenzerin(user):
        return [Aufgabe.ZIELGRUPPE_TAENZERINNEN]
    if _kinder_fuer_nutzer(user).exists():
        return [Aufgabe.ZIELGRUPPE_ELTERN, Aufgabe.ZIELGRUPPE_TAENZERINNEN]
    return [Aufgabe.ZIELGRUPPE_ELTERN]


def _aufgaben_fuer_nutzer_sichtbar(queryset, user):
    zielgruppen = _erlaubte_aufgaben_zielgruppen(user)
    if zielgruppen is None:
        return queryset
    return queryset.filter(sichtbar_fuer__in=zielgruppen)


def _offene_aufgaben_liste(queryset, user):
    """Baut aus den sichtbaren offenen Aufgaben eine Liste fuer die Anzeige. Bei Aufgaben fuer
    Taenzerinnen wird pro Kind einzeln erfasst, ob es fuer dieses Kind schon erledigt ist -
    hat der Nutzer fuer ALLE seine Kinder schon erledigt, wird die Aufgabe fuer ihn ausgeblendet.
    Ein Taenzerin-Konto (eigener Login) sieht dabei nur sich selbst, nicht mitverwaltete Geschwister."""
    kinder = list(_kinder_fuer_termine(user))
    liste = []
    for aufgabe in queryset:
        if aufgabe.sichtbar_fuer == Aufgabe.ZIELGRUPPE_TAENZERINNEN:
            erledigt_ids = set(
                AufgabeErledigung.objects.filter(aufgabe=aufgabe, taenzerin__in=kinder)
                .values_list("taenzerin_id", flat=True)
            )
            offene_kinder = [kind for kind in kinder if kind.id not in erledigt_ids]
            if not offene_kinder:
                continue
            liste.append({"aufgabe": aufgabe, "offene_kinder": offene_kinder})
        else:
            liste.append({"aufgabe": aufgabe, "offene_kinder": None})
    return liste


def _anmeldepunkt_info(punkt, user):
    anmeldungen = list(punkt.anmeldungen.all())
    eigene_anmeldung = next((a for a in anmeldungen if a.eltern_id == user.id), None)
    return {"punkt": punkt, "anmeldungen": anmeldungen, "eigene_anmeldung": eigene_anmeldung}


def _verbundene_mitglieder(user):
    """Andere Benutzer, die über eine Familien-Einladung mit diesem Konto verbunden sind."""
    mitverwalter = set()
    for kind in Taenzerin.objects.filter(eltern=user).prefetch_related("mitverwaltet_von"):
        mitverwalter |= set(kind.mitverwaltet_von.all())

    einladende = set()
    for kind in Taenzerin.objects.filter(mitverwaltet_von=user).select_related("eltern"):
        if kind.eltern_id != user.id:
            einladende.add(kind.eltern)

    return mitverwalter, einladende


MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _fuer_gruppen_relevant(queryset, gruppen):
    """Schränkt Termine auf 'gilt für alle Gruppen' (keine Gruppe zugewiesen) plus die übergebenen Gruppen ein."""
    return queryset.filter(Q(gruppen__isnull=True) | Q(gruppen__in=gruppen)).distinct()


def _offener_termin_id(request):
    try:
        return int(request.GET.get("offener_termin", 0)) or None
    except (ValueError, TypeError):
        return None


def _nach_monat_gruppieren(termin_liste, offener_termin_id=None):
    """Gruppiert eine Liste von Termin-Einträgen nach Monat (Reihenfolge bleibt erhalten)."""
    gruppen = []
    for eintrag in termin_liste:
        monat_label = f"{MONATSNAMEN[eintrag['termin'].beginn.month - 1]} {eintrag['termin'].beginn.year}"
        if not gruppen or gruppen[-1]["monat_label"] != monat_label:
            gruppen.append({"monat_label": monat_label, "eintraege": [], "force_open": False})
        gruppen[-1]["eintraege"].append(eintrag)
        if offener_termin_id and eintrag["termin"].id == offener_termin_id:
            gruppen[-1]["force_open"] = True
    return gruppen


def _feiertage_fuer_monat(jahr, monat):
    """Liefert {tag: name} der bayerischen Feiertage, die in den Monat fallen."""
    feiertage = bayerische_feiertage(jahr)
    return {datum.day: name for datum, name in feiertage.items() if datum.month == monat}


def _ferien_fuer_monat(jahr, monat):
    """Liefert ({tag: name}, [Ferienzeitraum, ...]) für einen Monat."""
    monatsanfang = date(jahr, monat, 1)
    monatsende = date(jahr, monat, calendar.monthrange(jahr, monat)[1])
    zeitraeume = list(Ferienzeitraum.objects.filter(start_datum__lte=monatsende, end_datum__gte=monatsanfang))
    ferien_nach_tag = {}
    for zeitraum in zeitraeume:
        tag = max(zeitraum.start_datum, monatsanfang)
        ende = min(zeitraum.end_datum, monatsende)
        while tag <= ende:
            ferien_nach_tag[tag.day] = zeitraum.name
            tag += timedelta(days=1)
    return ferien_nach_tag, zeitraeume


def _kalender_monat(jahr, monat, gruppen):
    """Baut ein Wochenraster (Mo-So) für den Monat, inkl. relevanter Termine pro Tag."""
    termine_im_monat = _fuer_gruppen_relevant(
        Termin.objects.filter(beginn__year=jahr, beginn__month=monat), gruppen
    )
    termine_nach_tag = {}
    for termin in termine_im_monat:
        termine_nach_tag.setdefault(termin.beginn.day, []).append(termin)

    feiertage_nach_tag = _feiertage_fuer_monat(jahr, monat)
    ferien_nach_tag, ferien_zeitraeume = _ferien_fuer_monat(jahr, monat)

    wochen = []
    woche = []
    for tag in calendar.Calendar(firstweekday=0).itermonthdates(jahr, monat):
        if tag.month == monat:
            woche.append({
                "datum": tag,
                "termine": termine_nach_tag.get(tag.day, []),
                "feiertag": feiertage_nach_tag.get(tag.day),
                "ferien": ferien_nach_tag.get(tag.day),
            })
        else:
            woche.append(None)
        if len(woche) == 7:
            wochen.append(woche)
            woche = []

    legende = [f"{date(jahr, monat, tag):%d.%m.} {name}" for tag, name in sorted(feiertage_nach_tag.items())]
    legende += [
        f"{z.name} ({z.start_datum:%d.%m.}–{z.end_datum:%d.%m.})" for z in ferien_zeitraeume
    ]
    return wochen, legende


def _termin_eintraege(termine, kinder, user):
    """Baut für eine Liste von Terminen die Anzeige-Einträge (Zusagen der Kinder, Helferpunkte, Zusagen-Anzahl)."""
    zusagen = {
        (z.termin_id, z.taenzerin_id): z
        for z in Zusage.objects.filter(taenzerin__in=kinder, termin__in=termine)
    }

    zusagen_anzahl = {
        row["termin_id"]: row["anzahl"]
        for row in Zusage.objects.filter(termin__in=termine, status=Zusage.STATUS_ZUGESAGT)
        .values("termin_id")
        .annotate(anzahl=Count("id"))
    }

    termin_liste = []
    for termin in termine:
        termin_gruppen_ids = set(termin.gruppen.values_list("id", flat=True))
        kinder_status = []
        for kind in kinder:
            kind_gruppe = kind.gruppe
            if termin_gruppen_ids and (kind_gruppe is None or kind_gruppe.id not in termin_gruppen_ids):
                continue
            zusage = zusagen.get((termin.id, kind.id))
            kinder_status.append({
                "kind": kind,
                "status": zusage.status if zusage else Zusage.STATUS_OFFEN,
            })

        anmeldepunkte_info = []
        if termin.art == Termin.ART_VERANSTALTUNG:
            for punkt in termin.anmeldepunkte.all():
                anmeldepunkte_info.append(_anmeldepunkt_info(punkt, user))

        termin_liste.append({
            "termin": termin,
            "kinder_status": kinder_status,
            "anmeldepunkte": anmeldepunkte_info,
            "anzahl_zusagen": zusagen_anzahl.get(termin.id, 0),
        })
    return termin_liste


@login_required
def dashboard(request):
    kinder = _kinder_fuer_termine(request.user)
    kinder_gruppen = {kind.gruppe for kind in kinder if kind.gruppe}

    termine = _fuer_gruppen_relevant(
        Termin.objects.filter(beginn__gte=timezone.now()).prefetch_related("anmeldepunkte__anmeldungen__eltern"),
        kinder_gruppen,
    ).order_by("beginn")

    termin_liste = _termin_eintraege(termine, kinder, request.user)

    offener_termin_id = _offener_termin_id(request)

    veranstaltungen_gruppen = _nach_monat_gruppieren(
        [e for e in termin_liste if e["termin"].art == Termin.ART_VERANSTALTUNG], offener_termin_id
    )
    training_gruppen = _nach_monat_gruppieren(
        [e for e in termin_liste if e["termin"].art == Termin.ART_TRAINING], offener_termin_id
    )

    faellige_kinder = [kind for kind in kinder if kind.bestaetigung_faellig]

    heute = timezone.localdate()
    try:
        jahr = int(request.GET.get("jahr", heute.year))
        monat = int(request.GET.get("monat", heute.month))
        date(jahr, monat, 1)
    except (ValueError, TypeError):
        jahr, monat = heute.year, heute.month

    vorheriger_monat = (jahr, monat - 1) if monat > 1 else (jahr - 1, 12)
    naechster_monat = (jahr, monat + 1) if monat < 12 else (jahr + 1, 1)

    kalender_wochen, kalender_legende = _kalender_monat(jahr, monat, kinder_gruppen)

    neueste_news = NewsPost.objects.all()[:3]

    return render(request, "mitglieder/dashboard.html", {
        "kinder": kinder,
        "neueste_news": neueste_news,
        "veranstaltungen_gruppen": veranstaltungen_gruppen,
        "training_gruppen": training_gruppen,
        "faellige_kinder": faellige_kinder,
        "kalender_wochen": kalender_wochen,
        "kalender_legende": kalender_legende,
        "kalender_monat_name": MONATSNAMEN[monat - 1],
        "kalender_jahr": jahr,
        "kalender_heute": heute,
        "vorheriger_monat": vorheriger_monat,
        "naechster_monat": naechster_monat,
    })


def _aufgaben_kontext(user):
    """Sammelt alle To-Do-bezogenen Daten (eigene Aufgaben, offene allgemeine Aufgaben,
    allgemeine Helferpunkte) - genutzt sowohl von der ToDo-Seite als auch vom Badge-Zaehler."""
    meine_aufgaben = Aufgabe.objects.filter(zugewiesen_an=user, erledigt=False).select_related("termin")

    offene_allgemeine_aufgaben = Aufgabe.objects.filter(
        termin__isnull=True, zugewiesen_an__isnull=True, erledigt=False,
    )
    offene_allgemeine_aufgaben = _aufgaben_fuer_nutzer_sichtbar(offene_allgemeine_aufgaben, user)
    offene_allgemeine_aufgaben = _offene_aufgaben_liste(offene_allgemeine_aufgaben, user)

    allgemeine_helferpunkte = [
        _anmeldepunkt_info(punkt, user)
        for punkt in Anmeldepunkt.objects.filter(termin__isnull=True).prefetch_related("anmeldungen__eltern")
    ]
    return meine_aufgaben, offene_allgemeine_aufgaben, allgemeine_helferpunkte


@login_required
def meine_aufgaben_liste(request):
    meine_aufgaben, offene_allgemeine_aufgaben, allgemeine_helferpunkte = _aufgaben_kontext(request.user)
    return render(request, "mitglieder/aufgaben_liste.html", {
        "meine_aufgaben": meine_aufgaben,
        "offene_allgemeine_aufgaben": offene_allgemeine_aufgaben,
        "allgemeine_helferpunkte": allgemeine_helferpunkte,
    })


@login_required
def veranstaltungen(request):
    """Eigene Übersicht aller Veranstaltungen, getrennt nach offen (noch nicht stattgefunden)
    und abgeschlossen (bereits vorbei)."""
    kinder = _kinder_fuer_termine(request.user)
    kinder_gruppen = {kind.gruppe for kind in kinder if kind.gruppe}

    offene_veranstaltungen = _fuer_gruppen_relevant(
        Termin.objects.filter(
            art=Termin.ART_VERANSTALTUNG, beginn__gte=timezone.now(),
        ).prefetch_related("anmeldepunkte__anmeldungen__eltern"),
        kinder_gruppen,
    ).order_by("beginn")
    offene_gruppen = _nach_monat_gruppieren(_termin_eintraege(offene_veranstaltungen, kinder, request.user))

    abgeschlossene_veranstaltungen = _fuer_gruppen_relevant(
        Termin.objects.filter(
            art=Termin.ART_VERANSTALTUNG, beginn__lt=timezone.now(),
        ).prefetch_related("anmeldepunkte__anmeldungen__eltern"),
        kinder_gruppen,
    ).order_by("-beginn")
    abgeschlossene_gruppen = _nach_monat_gruppieren(
        _termin_eintraege(abgeschlossene_veranstaltungen, kinder, request.user)
    )

    return render(request, "mitglieder/veranstaltungen.html", {
        "offene_gruppen": offene_gruppen,
        "abgeschlossene_gruppen": abgeschlossene_gruppen,
    })


@login_required
def trainings_liste(request):
    """Uebersicht aller zukuenftigen Trainings (nicht nur der offenen), egal ob zugesagt/abgesagt/offen."""
    kinder = _kinder_fuer_termine(request.user)
    kinder_gruppen = {kind.gruppe for kind in kinder if kind.gruppe}

    anstehende_trainings = _fuer_gruppen_relevant(
        Termin.objects.filter(art=Termin.ART_TRAINING, beginn__gte=timezone.now()),
        kinder_gruppen,
    ).order_by("beginn")
    anstehende_gruppen = _nach_monat_gruppieren(
        _termin_eintraege(anstehende_trainings, kinder, request.user), _offener_termin_id(request)
    )
    jetzt = timezone.now()
    aktueller_monat = f"{MONATSNAMEN[jetzt.month - 1]} {jetzt.year}"

    return render(request, "mitglieder/trainings_liste.html", {
        "anstehende_gruppen": anstehende_gruppen,
        "aktueller_monat": aktueller_monat,
    })


SEITEN_MIT_TERMIN_KARTEN = {"dashboard", "veranstaltungen", "trainings_liste", "offene_trainings"}


def _zurueck_zu_termin_seite(request, termin_id):
    """Leitet zurueck zu der Seite, von der das Formular abgeschickt wurde (Dashboard,
    Veranstaltungen, Training, Offene Trainings), damit man nach Zu-/Absagen dort bleibt,
    statt immer zum Dashboard zu springen."""
    naechste_seite = request.POST.get("next")
    ziel = naechste_seite if naechste_seite in SEITEN_MIT_TERMIN_KARTEN else "dashboard"
    # Kein #termin-...-Anker hier: der wuerde die Seite zu der Karte hochscrollen. Die
    # Scroll-Position wird stattdessen per JavaScript erhalten (siehe base.html).
    return redirect(f"{reverse(ziel)}?offener_termin={termin_id}")


@login_required
def termin_zusage(request, termin_id, kind_id, status):
    termin = get_object_or_404(Termin, pk=termin_id)
    kind = get_object_or_404(_kinder_fuer_nutzer(request.user), pk=kind_id)

    gueltige_status = {s for s, _ in Zusage.STATUS_CHOICES}
    if status not in gueltige_status:
        messages.error(request, "Ungültiger Status.")
        return redirect("dashboard")

    zusage, _ = Zusage.objects.get_or_create(taenzerin=kind, termin=termin)
    zusage.status = status
    zusage.save()
    messages.success(request, f"Antwort für {kind.vorname} bei '{termin.titel}' gespeichert.")
    return _zurueck_zu_termin_seite(request, termin_id)


@login_required
def alle_trainings_zusagen(request, kind_id):
    kind = get_object_or_404(_kinder_fuer_nutzer(request.user), pk=kind_id)

    if request.method == "POST":
        termine = _fuer_gruppen_relevant(
            Termin.objects.filter(art=Termin.ART_TRAINING, beginn__gte=timezone.now()),
            {kind.gruppe} if kind.gruppe else set(),
        )

        aktualisiert = 0
        for termin in termine:
            zusage, neu = Zusage.objects.get_or_create(taenzerin=kind, termin=termin)
            if neu or zusage.status == Zusage.STATUS_OFFEN:
                zusage.status = Zusage.STATUS_ZUGESAGT
                zusage.save()
                aktualisiert += 1

        messages.success(request, f"{aktualisiert} offene Trainings für {kind.vorname} wurden zugesagt.")

    return redirect("dashboard")


def _redirect_nach_anmeldung(punkt):
    if punkt.termin_id:
        return redirect(f"{reverse('dashboard')}?offener_termin={punkt.termin_id}#termin-{punkt.termin_id}")
    return redirect(f"{reverse('dashboard')}#helferaufgabe-{punkt.id}")


@login_required
def anmeldepunkt_eintragen(request, punkt_id):
    punkt = get_object_or_404(Anmeldepunkt, pk=punkt_id)

    if request.method == "POST":
        if punkt.max_anzahl is not None and punkt.plaetze_frei == 0:
            messages.error(request, f"Für '{punkt.titel}' sind bereits alle Plätze belegt.")
            return _redirect_nach_anmeldung(punkt)

        kommentar = request.POST.get("kommentar", "").strip()
        if punkt.mit_kommentar:
            # Mitbringliste: mehrere Eintraege pro Person erlaubt (z.B. 2x Kuchen).
            Anmeldung.objects.create(anmeldepunkt=punkt, eltern=request.user, kommentar=kommentar)
        else:
            # Reine Helferliste: jede Person nur einmal.
            Anmeldung.objects.get_or_create(anmeldepunkt=punkt, eltern=request.user)
        messages.success(request, f"Du hast dich bei '{punkt.titel}' eingetragen.")
        return _redirect_nach_anmeldung(punkt)

    return redirect("dashboard")


@login_required
def anmeldepunkt_austragen(request, anmeldung_id):
    anmeldung = get_object_or_404(Anmeldung, pk=anmeldung_id, eltern=request.user)
    punkt = anmeldung.anmeldepunkt

    if request.method == "POST":
        anmeldung.delete()
        messages.success(request, f"Du hast dich bei '{punkt.titel}' ausgetragen.")
        _admins_ueber_austragung_benachrichtigen(request.user, punkt)

    return _redirect_nach_anmeldung(punkt)


@login_required
def aufgabe_erledigt(request, aufgabe_id):
    aufgabe = get_object_or_404(Aufgabe, pk=aufgabe_id, zugewiesen_an=request.user)

    if request.method == "POST":
        aufgabe.erledigt = True
        aufgabe.save()
        messages.success(request, f"'{aufgabe.titel}' als erledigt markiert.")

    return redirect("dashboard")


@login_required
def aufgabe_uebernehmen(request, aufgabe_id):
    aufgabe = get_object_or_404(Aufgabe, pk=aufgabe_id, termin__isnull=True)
    zielgruppen = _erlaubte_aufgaben_zielgruppen(request.user)
    if zielgruppen is not None and aufgabe.sichtbar_fuer not in zielgruppen:
        raise PermissionDenied

    if request.method == "POST":
        aktualisiert = Aufgabe.objects.filter(
            pk=aufgabe_id, zugewiesen_an__isnull=True, erledigt=False,
        ).update(zugewiesen_an=request.user)
        if aktualisiert:
            messages.success(request, f"Du hast '{aufgabe.titel}' übernommen.")
        else:
            messages.error(request, "Diese Aufgabe ist bereits vergeben oder existiert nicht mehr.")

    return redirect("dashboard")


@login_required
def aufgabe_erledigt_fuer_kind(request, aufgabe_id, kind_id):
    aufgabe = get_object_or_404(Aufgabe, pk=aufgabe_id, sichtbar_fuer=Aufgabe.ZIELGRUPPE_TAENZERINNEN)
    kind = get_object_or_404(_kinder_fuer_termine(request.user), pk=kind_id)

    if request.method == "POST":
        _, neu_erstellt = AufgabeErledigung.objects.get_or_create(aufgabe=aufgabe, taenzerin=kind)
        if neu_erstellt:
            messages.success(request, f"'{aufgabe.titel}' für {kind.vorname} als erledigt markiert.")
        else:
            messages.info(request, f"'{aufgabe.titel}' war für {kind.vorname} bereits als erledigt markiert.")

    return redirect("dashboard")


def _admin_emails():
    """E-Mails des gesamten Orga-/Admin-Teams (is_staff, umfasst auch is_superuser)."""
    admin_emails = set(User.objects.filter(is_staff=True).exclude(email="").values_list("email", flat=True))
    if settings.ADMIN_BENACHRICHTIGUNGS_EMAIL:
        admin_emails.add(settings.ADMIN_BENACHRICHTIGUNGS_EMAIL)
    return admin_emails


def _admins_benachrichtigen(subject, message):
    admin_emails = _admin_emails()
    if not admin_emails:
        return
    sichere_mail_senden(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=list(admin_emails),
    )


def _admins_ueber_austragung_benachrichtigen(user, punkt):
    kontext = f" bei '{punkt.termin.titel}'" if punkt.termin else ""
    _admins_benachrichtigen(
        subject=f"Helfer ausgetragen: {punkt.titel}",
        message=(
            f"{benutzer_name(user)} hat sich wieder ausgetragen bei:\n\n"
            f"Helferpunkt: {punkt.titel}{kontext}\n\n"
            "Im Admin-Bereich unter Helfer-/Mitbringpunkte einsehbar."
        ),
    )


def _admins_ueber_registrierung_benachrichtigen(user):
    _admins_benachrichtigen(
        subject=f"Neue Registrierung: {user.first_name or user.username}",
        message=(
            f"Es hat sich ein neues Mitglied registriert:\n\n"
            f"Name: {user.first_name} {user.last_name}\n"
            f"Benutzername: {user.username}\n"
            f"E-Mail: {user.email or '(keine angegeben)'}\n\n"
            "Im Admin-Bereich unter Benutzer einsehbar."
        ),
    )


def registrieren(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = RegistrierenForm(request.POST)
        if form.is_valid():
            user = form.save()
            _admins_ueber_registrierung_benachrichtigen(user)
            login(request, user)
            messages.success(request, "Konto erfolgreich erstellt! Leg jetzt dein(e) Kind(er) an.")
            return redirect("kinder_liste")
    else:
        form = RegistrierenForm()

    return render(request, "mitglieder/registrieren.html", {"form": form})


def benutzername_vergessen(request):
    if request.method == "POST":
        form = BenutzernameVergessenForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            benutzernamen = list(
                User.objects.filter(email__iexact=email).values_list("username", flat=True)
            )
            if benutzernamen:
                sichere_mail_senden(
                    subject="Dein Benutzername für die Garde-Tanz-App",
                    message=(
                        "Hallo,\n\n"
                        "zu dieser E-Mail-Adresse ist folgender Benutzername registriert:\n\n"
                        + "\n".join(f"- {name}" for name in benutzernamen)
                        + "\n\nFalls du dein Passwort auch vergessen hast, kannst du es über "
                        "'Passwort vergessen' auf der Login-Seite zurücksetzen."
                    ),
                    from_email=None,
                    recipient_list=[email],
                )
            messages.success(
                request,
                "Falls diese E-Mail-Adresse bei uns registriert ist, wurde der Benutzername soeben dorthin geschickt.",
            )
            return redirect("login")
    else:
        form = BenutzernameVergessenForm()

    return render(request, "mitglieder/benutzername_vergessen.html", {"form": form})


def familie_einladen(request, token):
    einladendes_konto = _einladendes_konto_aus_token(token)
    if einladendes_konto is None:
        messages.error(request, "Dieser Einladungslink ist ungültig.")
        return redirect("login")

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = FamilieEinladenForm(request.POST)
        if form.is_valid():
            user = form.save()
            for kind in _kinder_fuer_nutzer(einladendes_konto):
                kind.mitverwaltet_von.add(user)
            _admins_ueber_registrierung_benachrichtigen(user)
            login(request, user)
            messages.success(
                request,
                f"Konto erfolgreich erstellt! Du siehst jetzt dieselben Kinder wie "
                f"{einladendes_konto.first_name or einladendes_konto.username}.",
            )
            return redirect("dashboard")
    else:
        form = FamilieEinladenForm()

    return render(request, "mitglieder/familie_einladen.html", {
        "form": form, "einladendes_konto": einladendes_konto,
    })


@login_required
def offene_trainings(request):
    """Zeigt alle Trainings (auch vergangene), zu denen mindestens eines der eigenen Kinder noch keine Rückmeldung hat."""
    kinder = _kinder_fuer_termine(request.user)
    kinder_gruppen = {kind.gruppe for kind in kinder if kind.gruppe}

    trainings = _fuer_gruppen_relevant(
        Termin.objects.filter(art=Termin.ART_TRAINING), kinder_gruppen
    ).order_by("-beginn")

    zusagen = {
        (z.termin_id, z.taenzerin_id): z.status
        for z in Zusage.objects.filter(taenzerin__in=kinder, termin__in=trainings)
    }
    zusagen_anzahl = {
        row["termin_id"]: row["anzahl"]
        for row in Zusage.objects.filter(termin__in=trainings, status=Zusage.STATUS_ZUGESAGT)
        .values("termin_id")
        .annotate(anzahl=Count("id"))
    }

    termin_liste = []
    for termin in trainings:
        termin_gruppen_ids = set(termin.gruppen.values_list("id", flat=True))
        kinder_status = []
        hat_offene = False
        for kind in kinder:
            kind_gruppe = kind.gruppe
            if termin_gruppen_ids and (kind_gruppe is None or kind_gruppe.id not in termin_gruppen_ids):
                continue
            status = zusagen.get((termin.id, kind.id), Zusage.STATUS_OFFEN)
            if status == Zusage.STATUS_OFFEN:
                hat_offene = True
            kinder_status.append({"kind": kind, "status": status})

        if hat_offene and kinder_status:
            termin_liste.append({
                "termin": termin,
                "kinder_status": kinder_status,
                "anmeldepunkte": [],
                "anzahl_zusagen": zusagen_anzahl.get(termin.id, 0),
            })

    return render(request, "mitglieder/offene_trainings.html", {"termin_liste": termin_liste})


@login_required
def impersonation_beenden(request):
    echter_admin_id = request.session.get("impersonator_id")
    if not echter_admin_id:
        return redirect("dashboard")

    echter_admin = get_object_or_404(User, pk=echter_admin_id, is_superuser=True)
    login(request, echter_admin, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Zurück in deinem Admin-Konto.")
    return redirect("admin:index")


@login_required
def kinder_liste(request):
    kinder = _kinder_fuer_nutzer(request.user).select_related("nutzer")
    return render(request, "mitglieder/kinder_liste.html", {"kinder": kinder})


@login_required
def kind_bearbeiten(request, kind_id=None):
    kind = None
    if kind_id is not None:
        kind = get_object_or_404(_kinder_fuer_nutzer(request.user), pk=kind_id)

    mitverwalter, einladende = _verbundene_mitglieder(request.user)
    moegliche_nutzer = User.objects.filter(
        Q(id=request.user.id) | Q(id__in=[u.id for u in mitverwalter | einladende])
    ).filter(Q(taenzerin_konto__isnull=True) | Q(taenzerin_konto=kind))

    if request.method == "POST":
        form = TaenzerinForm(request.POST, instance=kind, moegliche_nutzer=moegliche_nutzer)
        if form.is_valid():
            kind = form.save(commit=False)
            if not kind.pk:
                kind.eltern = request.user
            kind.save()
            kind.stammdaten_bestaetigen()
            messages.success(request, f"Daten für {kind.vorname} wurden gespeichert und bestätigt.")
            return redirect("kinder_liste")
    else:
        form = TaenzerinForm(instance=kind, moegliche_nutzer=moegliche_nutzer)

    return render(request, "mitglieder/kind_form.html", {"form": form, "kind": kind})


@login_required
def kind_einverstaendnis_bildaufnahmen(request, kind_id, wert):
    kind = get_object_or_404(_kinder_fuer_nutzer(request.user), pk=kind_id)

    if wert not in ("ja", "nein"):
        messages.error(request, "Ungültiger Wert.")
        return redirect("kinder_liste")

    if request.method == "POST":
        war_erteilt = kind.einverstaendnis_bildaufnahmen is True
        kind.einverstaendnis_bildaufnahmen_setzen(wert == "ja")
        messages.success(request, f"Einverständnis für Bild-/Videoaufnahmen von {kind.vorname} gespeichert.")
        if war_erteilt and wert == "nein":
            _admins_benachrichtigen(
                subject=f"Einverständnis Bild-/Videoaufnahmen entzogen: {kind.vorname} {kind.nachname}",
                message=(
                    "Das Einverständnis für Bild-/Videoaufnahmen (Social Media, Homepage/App, Presse) "
                    "wurde soeben widerrufen für:\n\n"
                    f"{kind.vorname} {kind.nachname}\n"
                    f"Verwaltet von: {request.user.first_name or request.user.username}\n\n"
                    "Bitte ab sofort keine Bilder/Videos dieser Person mehr veröffentlichen."
                ),
            )

    return redirect("kinder_liste")


@login_required
def profil_datennutzung(request, wert):
    if wert not in ("ja", "nein"):
        messages.error(request, "Ungültiger Wert.")
        return redirect("konto_bearbeiten")

    if request.method == "POST":
        profil, _ = Profil.objects.get_or_create(user=request.user)
        war_erteilt = profil.einverstanden_datennutzung is True
        profil.datennutzung_setzen(wert == "ja")
        messages.success(request, "Einverständnis zur Datennutzung gespeichert.")
        if war_erteilt and wert == "nein":
            _admins_benachrichtigen(
                subject=f"Einverständnis Datennutzung entzogen: {request.user.first_name or request.user.username}",
                message=(
                    "Das Einverständnis zur Datennutzung für vereinsinterne Zwecke wurde soeben widerrufen von:\n\n"
                    f"{request.user.first_name} {request.user.last_name} ({request.user.username})"
                ),
            )

    return redirect("konto_bearbeiten")


@login_required
def feedback_senden(request):
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.absender = request.user
            feedback.save()
            messages.success(request, "Danke, deine Nachricht wurde an die Admins geschickt.")
            return redirect("dashboard")
    else:
        form = FeedbackForm()

    return render(request, "mitglieder/feedback_form.html", {"form": form})


VORSTANDSCHAFT = [
    {"amt": "Vorstand", "namen": ["Martin Helmreich"]},
    {"amt": "stellv. Vorsitzende", "namen": ["Maxi Albrecht", "Walter Kohl"]},
    {"amt": "Schatzmeister", "namen": ["Thomas Finger"]},
    {"amt": "Schriftführerin", "namen": ["Christine Friedrich"]},
    {"amt": "Jugendleiter", "namen": ["Christian Krenzer"]},
]


@login_required
def vorstandschaft(request):
    return render(request, "mitglieder/vorstandschaft.html", {"vorstandschaft": VORSTANDSCHAFT})


@login_required
def kontakte_der_abteilungen(request):
    return render(request, "mitglieder/kontakte_der_abteilungen.html")


@login_required
def formulare_liste(request):
    from formulare.models import Formular

    return render(request, "mitglieder/formulare_liste.html", {"formulare": Formular.objects.all()})


@login_required
def news_liste(request):
    news = NewsPost.objects.all()
    return render(request, "mitglieder/news_liste.html", {"news": news})


@login_required
def nachrichten_liste(request):
    nachrichten = list(Nachricht.objects.filter(empfaenger=request.user).select_related("absender"))
    ungelesene_ids = [n.id for n in nachrichten if not n.gelesen]
    if ungelesene_ids:
        Nachricht.objects.filter(id__in=ungelesene_ids).update(gelesen=True)
    return render(request, "mitglieder/nachrichten_liste.html", {
        "nachrichten": nachrichten, "ungelesene_ids": ungelesene_ids,
    })


def _titelbild_zuerst(bilder):
    """Sortiert eine Liste von Galeriebildern so, dass ein markiertes Titelbild (falls vorhanden) zuerst kommt."""
    return sorted(bilder, key=lambda b: not b.titelbild)


def _gruppen_kachel(bilder_liste):
    """Gibt (Titelbild-oder-erstes-Bild, Anzahl) für eine Gruppe von Galeriebildern zurück."""
    bilder_liste = _titelbild_zuerst(bilder_liste)
    titelbild = bilder_liste[0] if bilder_liste else None
    return titelbild, len(bilder_liste)


@login_required
def galerie(request):
    bilder = Galeriebild.objects.select_related("termin", "ordner", "ordner__veranstaltung")

    allgemeine_bilder = [b for b in bilder if b.termin_id is None and b.ordner_id is None]

    nach_veranstaltung = {}
    nach_ordner = {}
    for b in bilder:
        if b.termin_id:
            nach_veranstaltung.setdefault(b.termin, []).append(b)
        elif b.ordner_id:
            if b.ordner.veranstaltung_id:
                nach_veranstaltung.setdefault(b.ordner.veranstaltung, []).append(b)
            else:
                nach_ordner.setdefault(b.ordner, []).append(b)

    veranstaltungs_kacheln = []
    for termin, liste in nach_veranstaltung.items():
        titelbild, anzahl = _gruppen_kachel(liste)
        veranstaltungs_kacheln.append({"termin": termin, "titelbild": titelbild, "anzahl": anzahl})

    ordner_kacheln = []
    for ordner, liste in nach_ordner.items():
        titelbild, anzahl = _gruppen_kachel(liste)
        ordner_kacheln.append({"ordner": ordner, "titelbild": titelbild, "anzahl": anzahl})

    allgemein_titelbild, allgemein_anzahl = _gruppen_kachel(allgemeine_bilder)

    return render(request, "mitglieder/galerie.html", {
        "veranstaltungs_kacheln": veranstaltungs_kacheln,
        "ordner_kacheln": ordner_kacheln,
        "allgemein_titelbild": allgemein_titelbild,
        "allgemein_anzahl": allgemein_anzahl,
    })


@login_required
def galerie_veranstaltung(request, pk):
    termin = get_object_or_404(Termin, pk=pk)
    bilder = _titelbild_zuerst(
        list(Galeriebild.objects.filter(Q(termin=termin) | Q(ordner__veranstaltung=termin)))
    )
    return render(request, "mitglieder/galerie_gruppe.html", {"titel": termin.titel, "bilder": bilder})


@login_required
def galerie_ordner(request, pk):
    ordner = get_object_or_404(Galerieordner, pk=pk)
    if ordner.veranstaltung_id:
        return redirect("galerie_veranstaltung", pk=ordner.veranstaltung_id)
    bilder = _titelbild_zuerst(list(Galeriebild.objects.filter(ordner=ordner)))
    return render(request, "mitglieder/galerie_gruppe.html", {"titel": f"📁 {ordner.name}", "bilder": bilder})


@login_required
def galerie_allgemein(request):
    bilder = _titelbild_zuerst(list(Galeriebild.objects.filter(termin__isnull=True, ordner__isnull=True)))
    return render(request, "mitglieder/galerie_gruppe.html", {"titel": "Allgemein", "bilder": bilder})


@login_required
def konto_bearbeiten(request):
    profil, _ = Profil.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = KontoForm(request.POST, instance=request.user)
        profil_form = ProfilForm(request.POST, instance=profil)
        if form.is_valid() and profil_form.is_valid():
            form.save()
            profil_form.save()
            messages.success(request, "Deine Kontodaten wurden gespeichert.")
            return redirect("konto_bearbeiten")
    else:
        form = KontoForm(instance=request.user)
        profil_form = ProfilForm(instance=profil)

    einladungslink = request.build_absolute_uri(
        reverse("familie_einladen", args=[_familien_einladungs_token(request.user)])
    )
    verbundene_mitverwalter, verbundene_einladende = _verbundene_mitglieder(request.user)

    return render(request, "mitglieder/konto_form.html", {
        "form": form,
        "profil_form": profil_form,
        "profil": profil,
        "einladungslink": einladungslink,
        "verbundene_mitverwalter": verbundene_mitverwalter,
        "verbundene_einladende": verbundene_einladende,
    })


@login_required
def passwort_aendern(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Dein Passwort wurde geändert.")
            return redirect("konto_bearbeiten")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "mitglieder/passwort_form.html", {"form": form})


def cron_training_erinnerung(request, secret):
    """Loest den training_zusage_erinnerung-Command per HTTP aus - fuer externe Scheduler
    (z.B. cron-job.org), falls kein PythonAnywhere-Tarif mit 'Scheduled tasks' gebucht ist.
    Kein @login_required, da der externe Dienst sich nicht einloggen kann - Schutz erfolgt
    ausschliesslich ueber das geheime Token in der URL."""
    if not settings.CRON_SECRET or not secrets.compare_digest(secret, settings.CRON_SECRET):
        raise PermissionDenied
    call_command("training_zusage_erinnerung")
    return HttpResponse("OK")


def cron_veranstaltung_erinnerung(request, secret):
    """Wie cron_training_erinnerung, nur fuer veranstaltung_zusage_erinnerung (Erinnerung
    3 Tage vor einer Veranstaltung)."""
    if not settings.CRON_SECRET or not secrets.compare_digest(secret, settings.CRON_SECRET):
        raise PermissionDenied
    call_command("veranstaltung_zusage_erinnerung")
    return HttpResponse("OK")
