from django.db import models
from django.utils import timezone
import uuid


class Order(models.Model):
    """Reprezentuje zamówienie/rezerwację wizyty do opłacenia"""

    ORDER_STATUS_CHOICES = [
        ('PENDING', 'Oczekujące'),
        ('RESERVED', 'Zarezerwowane'),
        ('COMPLETED', 'Ukończone'),
        ('CANCELED', 'Anulowane'),
        ('EXPIRED', 'Wygasłe'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment_id = models.UUIDField(unique=True, help_text="ID wizyty z Appointment-Service")
    patient_id = models.UUIDField(help_text="ID pacjenta z Identity-Service")
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Kwota w PLN")
    currency = models.CharField(max_length=3, default='PLN')
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='PENDING')
    description = models.CharField(max_length=255, help_text="Opis zamówienia dla PayU")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(help_text="Czas wygaśnięcia rezerwacji")

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['appointment_id']),
            models.Index(fields=['patient_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Order {self.id} - {self.amount} PLN ({self.get_status_display()})"


class Payment(models.Model):
    """Reprezentuje transakcję płatniczą w PayU"""

    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Oczekująca'),
        ('COMPLETED', 'Ukończona'),
        ('FAILED', 'Nie powiodła się'),
        ('CANCELED', 'Anulowana'),
        ('REFUNDED', 'Zwrócona'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    payu_order_id = models.CharField(max_length=100, unique=True, help_text="ID zamówienia w PayU")
    payu_status = models.CharField(
        max_length=50,
        choices=PAYMENT_STATUS_CHOICES,
        default='PENDING',
        help_text="Status z API PayU"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='PLN')

    # Dane z PayU
    payu_response = models.JSONField(null=True, blank=True, help_text="Pełna odpowiedź z PayU")
    payu_notify_response = models.JSONField(null=True, blank=True, help_text="Dane z webhooka IPN")

    # Rezultat
    payment_method = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Czas potwierdzenia płatności")

    class Meta:
        db_table = 'payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payu_order_id']),
            models.Index(fields=['payu_status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Payment {self.id} - {self.amount} PLN ({self.payu_status})"


class PaymentStatus(models.Model):
    """Historia zmian statusu płatności (audit trail)"""

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=50)
    new_status = models.CharField(max_length=50)
    reason = models.CharField(max_length=255, blank=True, help_text="Powód zmiany")
    webhook_data = models.JSONField(null=True, blank=True, help_text="Dane z webhooka, jeśli zmianę wyzwolił webhook")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payment_statuses'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payment.id}: {self.old_status} → {self.new_status}"


class AuditLog(models.Model):
    """Ślad audytowy operacji płatniczych"""

    ACTION_CHOICES = [
        ('ORDER_CREATED', 'Zamówienie utworzone'),
        ('ORDER_EXPIRED', 'Zamówienie wygasłe'),
        ('PAYMENT_INITIATED', 'Płatność zainicjowana'),
        ('PAYMENT_COMPLETED', 'Płatność ukończona'),
        ('PAYMENT_FAILED', 'Płatność nie powiodła się'),
        ('PAYMENT_REFUND_INITIATED', 'Zwrot zainicjowany'),
        ('PAYMENT_REFUND_COMPLETED', 'Zwrot ukończony'),
        ('WEBHOOK_RECEIVED', 'Webhook odebrany'),
        ('WEBHOOK_PROCESSED', 'Webhook przetworzony'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    actor_id = models.UUIDField(null=True, blank=True, help_text="Użytkownik/system który wykonał akcję")
    actor_type = models.CharField(
        max_length=20,
        choices=[
            ('USER', 'Użytkownik'),
            ('SYSTEM', 'System'),
            ('WEBHOOK', 'Webhook'),
        ],
        default='SYSTEM'
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')

    details = models.JSONField(help_text="Szczegóły akcji")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['actor_id']),
            models.Index(fields=['action']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.created_at}"

