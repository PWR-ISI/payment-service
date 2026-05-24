from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.conf import settings
import requests
from datetime import datetime, timedelta
from .models import PaymentOrder, PaymentTransaction, Invoice, PaymentRefund
from .serializers import (
    PaymentOrderListSerializer, PaymentOrderDetailSerializer,
    PaymentOrderCreateSerializer, PaymentOrderUpdateSerializer,
    PaymentProcessSerializer, RefundSerializer, PaymentTransactionSerializer
)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({'status': 'healthy'}, status=status.HTTP_200_OK)


class PaymentOrderViewSet(viewsets.ModelViewSet):
    queryset = PaymentOrder.objects.all()
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'appointment_id', 'patient_id']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentOrderCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PaymentOrderUpdateSerializer
        elif self.action == 'retrieve':
            return PaymentOrderDetailSerializer
        return PaymentOrderListSerializer

    def get_queryset(self):
        queryset = PaymentOrder.objects.all()
        appointment_id = self.request.query_params.get('appointment_id')
        patient_id = self.request.query_params.get('patient_id')
        status_param = self.request.query_params.get('status')

        if appointment_id:
            queryset = queryset.filter(appointment_id=appointment_id)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        order = self.get_object()
        if order.status == 'completed':
            return Response({'error': 'Order is already paid'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PaymentProcessSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment_method = serializer.validated_data['payment_method']
        order.payment_method = payment_method
        order.status = 'processing'
        order.save()

        # Create transaction
        transaction = PaymentTransaction.objects.create(
            order=order,
            transaction_type='payment',
            amount=order.amount,
            currency=order.currency,
            payment_method=payment_method,
            status='processing'
        )

        # For demo purposes, we'll just mark as completed
        # In production, this would call PayU API or actual payment processor
        if payment_method == 'payu':
            success = self._process_payu_payment(order, transaction, request.data)
        else:
            success = True

        if success:
            order.status = 'completed'
            order.completed_at = timezone.now()
            transaction.status = 'completed'
            order.save()
            transaction.save()

            # Create invoice
            Invoice.objects.get_or_create(
                order=order,
                defaults={
                    'invoice_number': f"INV-{order.reference_number}",
                    'due_date': timezone.now().date() + timedelta(days=30)
                }
            )

            return Response(PaymentOrderDetailSerializer(order).data, status=status.HTTP_200_OK)
        else:
            order.status = 'failed'
            transaction.status = 'failed'
            order.save()
            transaction.save()
            return Response({'error': 'Payment processing failed'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        order = self.get_object()
        if order.status != 'completed':
            return Response({'error': 'Cannot refund non-completed orders'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RefundSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        refund_amount = serializer.validated_data.get('amount', order.amount)
        reason = serializer.validated_data['reason']

        refund = PaymentRefund.objects.create(
            order=order,
            amount=refund_amount,
            reason=reason,
            description=serializer.validated_data.get('description', ''),
            status='processing'
        )

        # Process refund (demo - just mark as processed)
        refund.status = 'completed'
        refund.processed_at = timezone.now()
        refund.save()

        # Create refund transaction
        PaymentTransaction.objects.create(
            order=order,
            transaction_type='refund',
            amount=refund_amount,
            currency=order.currency,
            status='completed'
        )

        return Response(RefundSerializer(refund).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        pending_orders = PaymentOrder.objects.filter(status='pending')
        serializer = PaymentOrderListSerializer(pending_orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _process_payu_payment(self, order, transaction, request_data):
        try:
            # PayU sandbox/production endpoint
            payu_merchant_id = getattr(settings, 'PAYU_MERCHANT_ID', None)
            payu_api_key = getattr(settings, 'PAYU_API_KEY', None)

            if not payu_merchant_id or not payu_api_key:
                return False

            external_order_id = request_data.get('external_order_id')
            if not external_order_id:
                return False

            order.external_order_id = external_order_id
            order.save()

            transaction.external_transaction_id = external_order_id
            transaction.save()

            return True
        except Exception as e:
            transaction.error_message = str(e)
            transaction.save()
            return False


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PaymentTransaction.objects.all()
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['order', 'transaction_type', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        order_id = self.request.query_params.get('order_id')
        if order_id:
            return PaymentTransaction.objects.filter(order_id=order_id)
        return PaymentTransaction.objects.all()


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'order__appointment_id']
    ordering = ['-issued_date']


class PaymentRefundViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PaymentRefund.objects.all()
    serializer_class = RefundSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['order', 'reason', 'status']
    ordering = ['-requested_at']

    def get_queryset(self):
        order_id = self.request.query_params.get('order_id')
        if order_id:
            return PaymentRefund.objects.filter(order_id=order_id)
        return PaymentRefund.objects.all()
