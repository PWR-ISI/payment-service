from django.contrib import admin
from .models import PaymentOrder, PaymentTransaction, Invoice, PaymentRefund


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'appointment_id', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('reference_number', 'appointment_id', 'patient_id')
    readonly_fields = ('reference_number', 'created_at', 'updated_at', 'completed_at')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('order', 'transaction_type', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'order', 'status', 'issued_date', 'due_date')
    list_filter = ('status', 'issued_date')
    search_fields = ('invoice_number',)
    readonly_fields = ('issued_date', 'created_at', 'updated_at')


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = ('order', 'amount', 'reason', 'status', 'requested_at')
    list_filter = ('reason', 'status', 'requested_at')
    readonly_fields = ('requested_at', 'processed_at')
