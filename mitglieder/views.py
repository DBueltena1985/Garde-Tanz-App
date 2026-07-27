import calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import KontoForm, TaenzerinForm
from .models import Anmeldepunkt, Anmeldung, NewsPost, Taenzerin, Termin, Zusage

MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _fuer_gruppen_relevant(queryset, gruppen):
    """Schränkt Termine auf 'Beide Gruppen' plus die übergebenen Gruppen ein."""
    return queryset.filter(Q(gruppe=Termin.GRUPPE_BEIDE) | Q(gruppe__in=gruppen))


def _nach_monat_gruppieren(termin_liste):
    """Gruppiert eine Liste von Termin-Einträgen nach Monat (Reihenfolge bleibt erhalten)."""
    gruppen = []
    for eintrag in termin_liste:
        monat_label = f"{MONATSNAMEN[eintrag['termin'].beginn.month - 1]} {eintrag['termin'].beginn.year}"
        if not gruppen or gruppen[-1]["monat_label"] != monat_label:
            gruppen.append({"monat_label": monat_label, "eintraege": []})
        gruppen[-1]["eintraege"].append(eintrag)
    return gruppen


def _kalender_monat(jahr, monat, gruppen):
    """Baut ein Wochenraster (Mo-So) für den Monat, inkl. relevanter Termine pro Tag."""
    termine_im_monat = _fuer_gruppen_relevant(
        Termin.objects.filter(beginn__year=jahr, beginn__month=monat), gruppen
    )
    termine_nach_tag = {}
    for termin in termine_im_monat:
        termine_nach_tag.setdefault(termin.beginn.day, []).append(termin)

    wochen = []
    woche = []
    for tag in calendar.Calendar(firstweekday=0).itermonthdates(jahr, monat):
        if tag.month == monat:
            woche.append({"datum": tag, "termine": termine_nach_tag.get(tag.day, [])})
        else:
            woche.append(None)
        if len(woche) == 7:
            wochen.append(woche)
            woche = []
    return wochen


@login_required
def dashboard(request):
    kinder = Taenzerin.objects.filter(eltern=request.user)
    kinder_gruppen = {kind.gruppe for kind in kinder if kind.gruppe}

    termine = _fuer_gruppen_relevant(
        Termin.objects.filter(beginn__gte=timezone.now()).prefetch_related("anmeldepunkte__anmeldungen__eltern"),
        kinder_gruppen,
    ).order_by("beginn")

    zusagen = {
        (z.termin_id, z.taenzerin_id): z
        for z in Zusage.objects.filter(taenzerin__in=kinder, termin__in=termine)
    }

    termin_liste = []
    for termin in termine:
        kinder_status = []
        for kind in kinder:
            if termin.gruppe != Termin.GRUPPE_BEIDE and kind.gruppe != termin.gruppe:
                continue
            zusage = zusagen.get((termin.id, kind.id))
            kinder_status.append({
                "kind": kind,
                "status": zusage.status if zusage else Zusage.STATUS_OFFEN,
            })

        anmeldepunkte_info = []
        for punkt in termin.anmeldepunkte.all():
            anmeldungen = list(punkt.anmeldungen.all())
            eigene_anmeldung = next((a for a in anmeldungen if a.eltern_id == request.user.id), None)
            anmeldepunkte_info.append({
                "punkt": punkt,
                "anmeldungen": anmeldungen,
                "eigene_anmeldung": eigene_anmeldung,
            })

        termin_liste.append({
            "termin": termin,
            "kinder_status": kinder_status,
            "anmeldepunkte": anmeldepunkte_info,
        })

    veranstaltungen_gruppen = _nach_monat_gruppieren(
        [e for e in termin_liste if e["termin"].art == Termin.ART_VERANSTALTUNG]
    )
    training_gruppen = _nach_monat_gruppieren(
        [e for e in termin_liste if e["termin"].art == Termin.ART_TRAINING]
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

    return render(request, "mitglieder/dashboard.html", {
        "kinder": kinder,
        "veranstaltungen_gruppen": veranstaltungen_gruppen,
        "training_gruppen": training_gruppen,
        "faellige_kinder": faellige_kinder,
        "kalender_wochen": _kalender_monat(jahr, monat, kinder_gruppen),
        "kalender_monat_name": MONATSNAMEN[monat - 1],
        "kalender_jahr": jahr,
        "kalender_heute": heute,
        "vorheriger_monat": vorheriger_monat,
        "naechster_monat": naechster_monat,
    })


@login_required
def termin_zusage(request, termin_id, kind_id, status):
    termin = get_object_or_404(Termin, pk=termin_id)
    kind = get_object_or_404(Taenzerin, pk=kind_id, eltern=request.user)

    gueltige_status = {s for s, _ in Zusage.STATUS_CHOICES}
    if status not in gueltige_status:
        messages.error(request, "Ungültiger Status.")
        return redirect("dashboard")

    zusage, _ = Zusage.objects.get_or_create(taenzerin=kind, termin=termin)
    zusage.status = status
    zusage.save()
    messages.success(request, f"Antwort für {kind.vorname} bei '{termin.titel}' gespeichert.")
    return redirect("dashboard")


@login_required
def anmeldepunkt_eintragen(request, punkt_id):
    punkt = get_object_or_404(Anmeldepunkt, pk=punkt_id)

    if request.method == "POST":
        bereits_angemeldet = Anmeldung.objects.filter(anmeldepunkt=punkt, eltern=request.user).exists()
        if not bereits_angemeldet and punkt.max_anzahl is not None and punkt.plaetze_frei == 0:
            messages.error(request, f"Für '{punkt.titel}' sind bereits alle Plätze belegt.")
            return redirect("dashboard")

        kommentar = request.POST.get("kommentar", "").strip()
        Anmeldung.objects.update_or_create(
            anmeldepunkt=punkt, eltern=request.user,
            defaults={"kommentar": kommentar},
        )
        messages.success(request, f"Du hast dich bei '{punkt.titel}' eingetragen.")

    return redirect("dashboard")


@login_required
def anmeldepunkt_austragen(request, punkt_id):
    punkt = get_object_or_404(Anmeldepunkt, pk=punkt_id)

    if request.method == "POST":
        Anmeldung.objects.filter(anmeldepunkt=punkt, eltern=request.user).delete()
        messages.success(request, f"Du hast dich bei '{punkt.titel}' ausgetragen.")

    return redirect("dashboard")


@login_required
def kinder_liste(request):
    kinder = Taenzerin.objects.filter(eltern=request.user)
    return render(request, "mitglieder/kinder_liste.html", {"kinder": kinder})


@login_required
def kind_bearbeiten(request, kind_id=None):
    kind = None
    if kind_id is not None:
        kind = get_object_or_404(Taenzerin, pk=kind_id, eltern=request.user)

    if request.method == "POST":
        form = TaenzerinForm(request.POST, instance=kind)
        if form.is_valid():
            kind = form.save(commit=False)
            kind.eltern = request.user
            kind.save()
            kind.stammdaten_bestaetigen()
            messages.success(request, f"Daten für {kind.vorname} wurden gespeichert und bestätigt.")
            return redirect("kinder_liste")
    else:
        form = TaenzerinForm(instance=kind)

    return render(request, "mitglieder/kind_form.html", {"form": form, "kind": kind})


@login_required
def news_liste(request):
    news = NewsPost.objects.all()
    return render(request, "mitglieder/news_liste.html", {"news": news})


@login_required
def konto_bearbeiten(request):
    if request.method == "POST":
        form = KontoForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Deine Kontodaten wurden gespeichert.")
            return redirect("konto_bearbeiten")
    else:
        form = KontoForm(instance=request.user)

    return render(request, "mitglieder/konto_form.html", {"form": form})


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
