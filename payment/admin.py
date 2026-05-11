from django.contrib import admin
from django.utils.html import format_html
from .models import Order, Payment, PaymentStatus, AuditLog


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'appointment_id', 'amount_display', 'status_badge', 'created_at')
    list_filter = ('status', 'created_at', 'currency')
    search_fields = ('id', 'appointment_id', 'patient_id')
    readonly_fields = ('id', 'created_at', 'updated_at')

    fieldsets = (
        ('Identifiers', {
            'fields': ('id', 'appointment_id', 'patient_id'),
        }),
        ('Order Details', {
            'fields': ('amount', 'currency', 'description', 'status'),
        }),
        ('Timeline', {
            'fields': ('created_at', 'updated_at', 'expires_at'),
        }),
    )

    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency}"
    amount_display.short_description = "Amount"

    def status_badge(self, obj):
        colors = {
            'PENDING': '#FFA500',
            'RESERVED': '#3498db',
            'COMPLETED': '#2ecc71',
            'CANCELED': '#e74c3c',
            'EXPIRED': '#95a5a6',
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'payu_order_id', 'amount_display', 'payu_status_badge', 'created_at', 'completed_at')
    list_filter = ('payu_status', 'created_at', 'currency')
    search_fields = ('id', 'payu_order_id', 'order__appointment_id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'payu_response', 'payu_notify_response')

    fieldsets = (
        ('Identifiers', {
            'fields': ('id', 'order', 'payu_order_id'),
        }),
        ('Payment Details', {
            'fields': ('amount', 'currency', 'payu_status', 'payment_method'),
        }),
        ('PayU Data', {
            'fields': ('payu_response', 'payu_notify_response'),
            'classes': ('collapse',),
        }),
        ('Timeline', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
        }),
    )

    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency}"
    amount_display.short_description = "Amount"

    def payu_status_badge(self, obj):
        colors = {
            'PENDING': '#FFA500',
            'COMPLETED': '#2ecc71',
            'FAILED': '#e74c3c',
            'CANCELED': '#e74c3c',
            'REFUNDED': '#9b59b6',
        }
        color = colors.get(obj.payu_status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_payu_status_display()
        )
    payu_status_badge.short_description = "PayU Status"


@admin.register(PaymentStatus)
class PaymentStatusAdmin(admin.ModelAdmin):
    list_display = ('payment_id', 'status_transition', 'reason', 'created_at')
    list_filter = ('created_at', 'new_status')
    search_fields = ('payment__id', 'reason')
    readonly_fields = ('created_at', 'webhook_data')

    def payment_id(self, obj):
        return obj.payment.id
    payment_id.short_description = "Payment"

    def status_transition(self, obj):
        return f"{obj.old_status} → {obj.new_status}"
    status_transition.short_description = "Transition"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'action_display', 'actor_info', 'created_at')
    list_filter = ('action', 'actor_type', 'created_at')
    search_fields = ('id', 'actor_id', 'order__id', 'payment__id')
    readonly_fields = ('id', 'created_at', 'details')

    fieldsets = (
        ('Action Info', {
            'fields': ('id', 'action', 'actor_type', 'actor_id'),
        }),
        ('Related Objects', {
            'fields': ('order', 'payment'),
        }),
        ('Details', {
            'fields': ('details',),
        }),
        ('Timeline', {
            'fields': ('created_at',),
        }),
    )

    def action_display(self, obj):
        return obj.get_action_display()
    action_display.short_description = "Action"

    def actor_info(self, obj):
        if obj.actor_type == 'USER' and obj.actor_id:
            return f"{obj.get_actor_type_display()} ({obj.actor_id})"
        return obj.get_actor_type_display()
    actor_info.short_description = "Actor"

