from django.apps import AppConfig

class PaymentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payment'          # ← ZMIEŃ z 'payments' na 'payment'
    verbose_name = 'Payment Service'