from django.apps import AppConfig


class PayguardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payguard"
    verbose_name = "Payment fraud guard"
