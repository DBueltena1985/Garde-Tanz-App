from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("termine/<int:termin_id>/<int:kind_id>/<str:status>/", views.termin_zusage, name="termin_zusage"),
    path("kinder/", views.kinder_liste, name="kinder_liste"),
    path("kinder/neu/", views.kind_bearbeiten, name="kind_neu"),
    path("kinder/<int:kind_id>/", views.kind_bearbeiten, name="kind_bearbeiten"),
    path("news/", views.news_liste, name="news_liste"),
    path("konto/", views.konto_bearbeiten, name="konto_bearbeiten"),
    path("konto/passwort/", views.passwort_aendern, name="passwort_aendern"),
]
