from django.apps import AppConfig


class HelpdeskConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "helpdesk"
    verbose_name = "ServiceDesk ПМ"

    def ready(self):
        from helpdesk import signals  # noqa: F401
