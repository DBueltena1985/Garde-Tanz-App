from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import TaenzerinForm
from .models import NewsPost, Taenzerin, Termin, Zusage


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

    return render(request, "mitglieder/dashboard.html", {
        "kinder": kinder,
        "termin_liste": termin_liste,
        "faellige_kinder": faellige_kinder,
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
