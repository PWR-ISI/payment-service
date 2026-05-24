from django.db import models
from django.utils import timezone

class PaymentOrder(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    )

    PAYMENT_METHODS = (
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('payu', 'PayU'),
        ('paypal', 'PayPal'),
    )

    appointment_id = models.IntegerField(db_index=True)
    patient_id = models.IntegerField(db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='PLN')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True)
    external_order_id = models.CharField(max_length=100, blank=True, null=True)
    reference_number = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payment_orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['appointment_id']),
            models.Index(fields=['patient_id']),
            models.Index(fields=['status']),
            models.Index(fields=['reference_number']),
        ]

    def __str__(self):
        return f"Order {self.reference_number} - {self.amount} {self.currency}"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            import uuid
            self.reference_number = str(uuid.uuid4())[:12].upper()
        super().save(*args, **kwargs)


class PaymentTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('adjustment', 'Adjustment'),
    )

    order = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='PLN')
    external_transaction_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default='pending')
    payment_method = models.CharField(max_length=20, blank=True)
    error_message = models.TextField(blank=True)
    response_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} {self.currency}"


class Invoice(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    )

    order = models.OneToOneField(PaymentOrder, on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    issued_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    notes = models.TextField(blank=True)
    file_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoices'
        ordering = ['-issued_date']

    def __str__(self):
        return self.invoice_number


class PaymentRefund(models.Model):
    REFUND_REASONS = (
        ('customer_request', 'Customer Request'),
        ('system_error', 'System Error'),
        ('duplicate_charge', 'Duplicate Charge'),
        ('cancellation', 'Appointment Cancellation'),
        ('other', 'Other'),
    )

    order = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=20, choices=REFUND_REASONS)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='pending')
    external_refund_id = models.CharField(max_length=100, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payment_refunds'
        ordering = ['-requested_at']

    def __str__(self):
        return f"Refund for Order {self.order.reference_number} - {self.amount}"
