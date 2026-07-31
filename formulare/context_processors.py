from .models import Formular


def formulare(request):
    return {"admin_formulare": Formular.objects.all()}
