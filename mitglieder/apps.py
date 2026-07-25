from django.apps import AppConfig


class MitgliederConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mitglieder"

    def ready(self):
        import mitglieder.signals  # noqa: F401
