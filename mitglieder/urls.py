from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("termine/<int:termin_id>/<str:status>/", views.termin_zusage, name="termin_zusage"),
    path("profil/", views.profil_bearbeiten, name="profil_bearbeiten"),
    path("news/", views.news_liste, name="news_liste"),
]
