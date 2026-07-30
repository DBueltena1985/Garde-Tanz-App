"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy

from mitglieder.forms import SicherePasswordResetForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='mitglieder/login.html'),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path(
        'passwort-vergessen/',
        auth_views.PasswordResetView.as_view(
            template_name='mitglieder/passwort_vergessen.html',
            email_template_name='mitglieder/email/passwort_reset_email.txt',
            subject_template_name='mitglieder/email/passwort_reset_subject.txt',
            form_class=SicherePasswordResetForm,
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'passwort-vergessen/gesendet/',
        auth_views.PasswordResetDoneView.as_view(template_name='mitglieder/passwort_vergessen_gesendet.html'),
        name='password_reset_done',
    ),
    path(
        'passwort-zuruecksetzen/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='mitglieder/passwort_zuruecksetzen.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'passwort-zuruecksetzen/fertig/',
        auth_views.PasswordResetCompleteView.as_view(template_name='mitglieder/passwort_zuruecksetzen_fertig.html'),
        name='password_reset_complete',
    ),
    path('', include('mitglieder.urls')),
]

# Lokal hochgeladene Galeriebilder ausliefern (nur ohne Cloudinary-Zugangsdaten,
# z.B. in der lokalen Entwicklung). In Produktion (DEBUG=False) sollen Bilder
# ueber Cloudinary kommen, nicht ueber Django selbst.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
