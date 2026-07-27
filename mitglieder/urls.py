from django.conf import settings
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(f"{settings.REGISTRIERUNGS_SLUG}/", views.registrieren, name="registrieren"),
    path("termine/<int:termin_id>/<int:kind_id>/<str:status>/", views.termin_zusage, name="termin_zusage"),
    path("kinder/<int:kind_id>/alle-trainings-zusagen/", views.alle_trainings_zusagen, name="alle_trainings_zusagen"),
    path("anmeldepunkte/<int:punkt_id>/eintragen/", views.anmeldepunkt_eintragen, name="anmeldepunkt_eintragen"),
    path("anmeldepunkte/<int:punkt_id>/austragen/", views.anmeldepunkt_austragen, name="anmeldepunkt_austragen"),
    path("kinder/", views.kinder_liste, name="kinder_liste"),
    path("kinder/neu/", views.kind_bearbeiten, name="kind_neu"),
    path("kinder/<int:kind_id>/", views.kind_bearbeiten, name="kind_bearbeiten"),
    path("news/", views.news_liste, name="news_liste"),
    path("konto/", views.konto_bearbeiten, name="konto_bearbeiten"),
    path("konto/passwort/", views.passwort_aendern, name="passwort_aendern"),
]
