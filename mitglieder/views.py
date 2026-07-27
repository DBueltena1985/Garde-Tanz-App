import calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import TaenzerinForm
from .models import NewsPost, Taenzerin, Termin, Zusage

MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _kalender_monat(jahr, monat):
    """Baut ein Wochenraster (Mo-So) für den Monat, inkl. Termine pro Tag."""
    termine_im_monat = Termin.objects.filter(beginn__year=jahr, beginn__month=monat)
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
    termine = Termin.objects.filter(beginn__gte=timezone.now()).order_by("beginn")

    zusagen = {
        (z.termin_id, z.taenzerin_id): z
        for z in Zusage.objects.filter(taenzerin__in=kinder, termin__in=termine)
    }

    termin_liste = []
    for termin in termine:
        kinder_status = []
        for kind in kinder:
            zusage = zusagen.get((termin.id, kind.id))
            kinder_status.append({
                "kind": kind,
                "status": zusage.status if zusage else Zusage.STATUS_OFFEN,
            })
        termin_liste.append({"termin": termin, "kinder_status": kinder_status})

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
        "termin_liste": termin_liste,
        "faellige_kinder": faellige_kinder,
        "kalender_wochen": _kalender_monat(jahr, monat),
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
