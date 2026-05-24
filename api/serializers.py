from rest_framework import serializers
from .models import PaymentOrder, PaymentTransaction, Invoice, PaymentRefund


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ('id', 'transaction_type', 'amount', 'currency', 'external_transaction_id', 'status', 'payment_method', 'error_message', 'created_at')
        read_only_fields = ('id', 'created_at')


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ('id', 'invoice_number', 'status', 'issued_date', 'due_date', 'notes', 'file_url', 'created_at')
        read_only_fields = ('id', 'invoice_number', 'issued_date', 'created_at')


class PaymentRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRefund
        fields = ('id', 'amount', 'reason', 'description', 'status', 'requested_at', 'processed_at')
        read_only_fields = ('id', 'requested_at', 'processed_at')


class PaymentOrderListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = ('id', 'appointment_id', 'patient_id', 'amount', 'currency', 'status', 'reference_number', 'created_at')
        read_only_fields = ('id', 'reference_number', 'created_at')


class PaymentOrderDetailSerializer(serializers.ModelSerializer):
    transactions = PaymentTransactionSerializer(many=True, read_only=True)
    invoice = InvoiceSerializer(read_only=True)
    refunds = PaymentRefundSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentOrder
        fields = ('id', 'appointment_id', 'patient_id', 'amount', 'currency', 'status', 'payment_method', 'external_order_id', 'reference_number', 'description', 'notes', 'transactions', 'invoice', 'refunds', 'created_at', 'updated_at', 'completed_at')
        read_only_fields = ('id', 'reference_number', 'created_at', 'updated_at', 'completed_at', 'transactions', 'invoice', 'refunds')


class PaymentOrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = ('appointment_id', 'patient_id', 'amount', 'currency', 'description')

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Amount must be greater than 0')
        return value


class PaymentOrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = ('status', 'payment_method', 'external_order_id', 'notes')


class PaymentProcessSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=['credit_card', 'debit_card', 'bank_transfer', 'payu', 'paypal'])
    external_order_id = serializers.CharField(required=False, allow_blank=True)
    additional_data = serializers.JSONField(required=False)


class RefundSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    reason = serializers.ChoiceField(choices=['customer_request', 'system_error', 'duplicate_charge', 'cancellation', 'other'])
    description = serializers.CharField(required=False, allow_blank=True)
