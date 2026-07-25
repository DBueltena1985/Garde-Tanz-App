from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ProfilForm
from .models import NewsPost, Profil, Termin, Zusage


@login_required
def dashboard(request):
    termine = Termin.objects.filter(beginn__gte=timezone.now()).order_by("beginn")
    eigene_zusagen = {
        z.termin_id: z for z in Zusage.objects.filter(mitglied=request.user, termin__in=termine)
    }

    termin_liste = []
    for termin in termine:
        zusage = eigene_zusagen.get(termin.id)
        termin_liste.append({
            "termin": termin,
            "status": zusage.status if zusage else Zusage.STATUS_OFFEN,
        })

    profil, _ = Profil.objects.get_or_create(user=request.user)

    return render(request, "mitglieder/dashboard.html", {
        "termin_liste": termin_liste,
        "profil": profil,
        "status_choices": Zusage.STATUS_CHOICES,
    })


@login_required
def termin_zusage(request, termin_id, status):
    termin = get_object_or_404(Termin, pk=termin_id)
    gueltige_status = {s for s, _ in Zusage.STATUS_CHOICES}
    if status not in gueltige_status:
        messages.error(request, "Ungültiger Status.")
        return redirect("dashboard")

    zusage, _ = Zusage.objects.get_or_create(mitglied=request.user, termin=termin)
    zusage.status = status
    zusage.save()
    messages.success(request, f"Antwort für '{termin.titel}' gespeichert.")
    return redirect("dashboard")


@login_required
def profil_bearbeiten(request):
    profil, _ = Profil.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfilForm(request.POST, instance=profil)
        if form.is_valid():
            form.save()
            profil.stammdaten_bestaetigen()
            messages.success(request, "Stammdaten wurden gespeichert und bestätigt.")
            return redirect("dashboard")
    else:
        form = ProfilForm(instance=profil)

    return render(request, "mitglieder/profil_form.html", {"form": form, "profil": profil})


@login_required
def news_liste(request):
    news = NewsPost.objects.all()
    return render(request, "mitglieder/news_liste.html", {"news": news})
