from rest_framework import serializers
from .models import Order, Payment, AuditLog
from decimal import Decimal
import json


class CreateOrderSerializer(serializers.Serializer):
    """Serializer do tworzenia zamówienia"""
    appointment_id = serializers.UUIDField()
    patient_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    currency = serializers.CharField(max_length=3, default='PLN')
    description = serializers.CharField(max_length=255)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Kwota musi być większa od 0")
        if value > Decimal('99999.99'):
            raise serializers.ValidationError("Kwota nie może przekroczyć 99999.99")
        return value


class OrderSerializer(serializers.ModelSerializer):
    payment = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'appointment_id', 'patient_id', 'amount', 'currency', 'status', 'description', 'payment', 'created_at', 'updated_at', 'expires_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_payment(self, obj):
        if hasattr(obj, 'payment') and obj.payment:
            return PaymentSerializer(obj.payment).data
        return None


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.CharField(source='order.id', read_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'order_id', 'payu_order_id', 'payu_status', 'amount', 'currency', 'payment_method', 'created_at', 'updated_at', 'completed_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class PayUWebhookSerializer(serializers.Serializer):
    """Żądanie webhooka z PayU"""
    order = serializers.JSONField()
    localMerchantId = serializers.CharField(required=False)
    customerIp = serializers.CharField(required=False)

    def validate(self, data):
        """Walidacja struktury żądania z PayU"""
        order = data.get('order', {})

        required_fields = ['orderId', 'orderStatus', 'totalAmount']
        for field in required_fields:
            if field not in order:
                raise serializers.ValidationError(f"Brakuje pola: {field}")

        return data


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    actor_type_display = serializers.CharField(source='get_actor_type_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'action_display', 'actor_id', 'actor_type', 'actor_type_display', 'order', 'payment', 'details', 'created_at']
        read_only_fields = ['id', 'created_at']

