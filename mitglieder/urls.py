from django.conf import settings
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(f"{settings.REGISTRIERUNGS_SLUG}/", views.registrieren, name="registrieren"),
    path("familie/<str:token>/", views.familie_einladen, name="familie_einladen"),
    path("termine/<int:termin_id>/<int:kind_id>/<str:status>/", views.termin_zusage, name="termin_zusage"),
    path("kinder/<int:kind_id>/alle-trainings-zusagen/", views.alle_trainings_zusagen, name="alle_trainings_zusagen"),
    path("anmeldepunkte/<int:punkt_id>/eintragen/", views.anmeldepunkt_eintragen, name="anmeldepunkt_eintragen"),
    path("anmeldungen/<int:anmeldung_id>/austragen/", views.anmeldepunkt_austragen, name="anmeldepunkt_austragen"),
    path("aufgaben/<int:aufgabe_id>/erledigt/", views.aufgabe_erledigt, name="aufgabe_erledigt"),
    path("aufgaben/<int:aufgabe_id>/uebernehmen/", views.aufgabe_uebernehmen, name="aufgabe_uebernehmen"),
    path(
        "aufgaben/<int:aufgabe_id>/erledigt/<int:kind_id>/",
        views.aufgabe_erledigt_fuer_kind,
        name="aufgabe_erledigt_fuer_kind",
    ),
    path("trainings/offen/", views.offene_trainings, name="offene_trainings"),
    path("veranstaltungen/", views.veranstaltungen, name="veranstaltungen"),
    path("impersonation/beenden/", views.impersonation_beenden, name="impersonation_beenden"),
    path("kinder/", views.kinder_liste, name="kinder_liste"),
    path("kinder/neu/", views.kind_bearbeiten, name="kind_neu"),
    path("kinder/<int:kind_id>/", views.kind_bearbeiten, name="kind_bearbeiten"),
    path(
        "kinder/<int:kind_id>/einverstaendnis/<str:wert>/",
        views.kind_einverstaendnis_bildaufnahmen,
        name="kind_einverstaendnis_bildaufnahmen",
    ),
    path("news/", views.news_liste, name="news_liste"),
    path("galerie/", views.galerie, name="galerie"),
    path("galerie/veranstaltung/<int:pk>/", views.galerie_veranstaltung, name="galerie_veranstaltung"),
    path("galerie/ordner/<int:pk>/", views.galerie_ordner, name="galerie_ordner"),
    path("galerie/allgemein/", views.galerie_allgemein, name="galerie_allgemein"),
    path("konto/", views.konto_bearbeiten, name="konto_bearbeiten"),
    path("konto/passwort/", views.passwort_aendern, name="passwort_aendern"),
    path("konto/datennutzung/<str:wert>/", views.profil_datennutzung, name="profil_datennutzung"),
    path("feedback/", views.feedback_senden, name="feedback_senden"),
    path("vorstandschaft/", views.vorstandschaft, name="vorstandschaft"),
    path("formulare/", views.formulare_liste, name="formulare_liste"),
    path("benutzername-vergessen/", views.benutzername_vergessen, name="benutzername_vergessen"),
]
