import logging
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
import json

from .models import Order, Payment, AuditLog
from .serializers import (
    CreateOrderSerializer,
    OrderSerializer,
    PaymentSerializer,
    PayUWebhookSerializer,
    AuditLogSerializer,
)
from .services import OrderService, PayUService

logger = logging.getLogger(__name__)


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet do zarządzania zamówieniami"""

    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateOrderSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        """POST /api/orders/ - Tworzenie nowego zamówienia"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            customer_ip = forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR', '127.0.0.1')

            order_service = OrderService()
            order = order_service.create_order(
                appointment_id=serializer.validated_data['appointment_id'],
                patient_id=serializer.validated_data['patient_id'],
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data.get('currency', 'PLN'),
                description=serializer.validated_data['description'],
            )

            payment = order_service.initiate_payment(order, customer_ip=customer_ip)

            response_serializer = OrderSerializer(order)
            data = response_serializer.data
            # Dołącz URL przekierowania do PayU, żeby frontend wiedział gdzie wysłać użytkownika
            payu_resp = payment.payu_response or {}
            data['redirect_url'] = payu_resp.get('redirectUri')
            return Response(data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def retrieve(self, request, *args, **kwargs):
        """GET /api/orders/{id}/ - Pobieranie szczegółów zamówienia"""
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """GET /api/orders/ - Lista zamówień"""
        patient_id = request.query_params.get('patient_id')

        queryset = self.get_queryset()
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def audit_logs(self, request, pk=None):
        """GET /api/orders/{id}/audit_logs/ - Historia zmian zamówienia"""
        try:
            order = self.get_object()
            audit_logs = order.audit_logs.all()
            serializer = AuditLogSerializer(audit_logs, many=True)
            return Response(serializer.data)
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet do zarządzania płatościami"""

    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

    def retrieve(self, request, *args, **kwargs):
        """GET /api/payments/{id}/ - Pobieranie szczegółów płatności"""
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """GET /api/payments/ - Lista płatności"""
        status_filter = request.query_params.get('status')

        queryset = self.get_queryset()
        if status_filter:
            queryset = queryset.filter(payu_status=status_filter)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """POST /api/payments/payments/{id}/refund/ - Zwrot płatności"""
        payment = self.get_object()

        if payment.payu_status != 'COMPLETED':
            return Response(
                {'error': f'Nie można zwrócić płatności o statusie {payment.payu_status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payu_service = PayUService()
            payu_service.refund_order(payment)

            old_status = payment.payu_status
            payment.payu_status = 'REFUNDED'
            payment.save()

            from .models import PaymentStatus, AuditLog
            PaymentStatus.objects.create(
                payment=payment,
                old_status=old_status,
                new_status='REFUNDED',
                reason='Zwrot zainicjowany przez system',
            )
            AuditLog.objects.create(
                action='PAYMENT_REFUND_INITIATED',
                actor_type='SYSTEM',
                payment=payment,
                order=payment.order,
                details={'initiated_by': str(request.user) if request.user.is_authenticated else 'api'},
            )

            return Response({'status': 'refund initiated'})

        except Exception as e:
            logger.error(f"Refund failed for payment {pk}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=['get'])
    def audit_logs(self, request, pk=None):
        """GET /api/payments/{id}/audit_logs/ - Historia zmian płatności"""
        try:
            payment = self.get_object()
            audit_logs = payment.audit_logs.all()
            serializer = AuditLogSerializer(audit_logs, many=True)
            return Response(serializer.data)
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Payment not found'},
                status=status.HTTP_404_NOT_FOUND
            )


@csrf_exempt
@require_http_methods(["POST"])
def payu_webhook(request):
    """POST /api/payments/webhook - Webhook z PayU do potwierdzenia płatności"""

    logger.info("PayU webhook received")

    try:
        # Parsowanie żądania
        request_body = request.body.decode('utf-8')
        webhook_data = json.loads(request_body)

        # Weryfikacja sygnatury
        signature = request.headers.get('OpenPayU-Signature', '')
        payu_service = PayUService()

        if not payu_service.verify_webhook_signature(request_body, signature):
            logger.warning("Invalid webhook signature")
            return JsonResponse({'status': 'ERROR'}, status=status.HTTP_401_UNAUTHORIZED)

        # Walidacja struktury
        serializer = PayUWebhookSerializer(data=webhook_data)
        serializer.is_valid(raise_exception=True)

        # Pobranie zamówienia z PayU
        payu_order = webhook_data.get('order', {})
        payu_order_id = payu_order.get('orderId')
        order_status = payu_order.get('orderStatus')

        logger.info(f"Processing webhook for PayU order: {payu_order_id}, status: {order_status}")

        # Znalezienie płatności w naszej bazie
        try:
            payment = Payment.objects.get(payu_order_id=payu_order_id)
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for PayU order: {payu_order_id}")
            return JsonResponse({'status': 'ERROR'}, status=status.HTTP_404_NOT_FOUND)

        # Przetworzenie statusu
        order_service = OrderService()

        if order_status == 'COMPLETED':
            order_service.complete_payment(payment, webhook_data)
            return JsonResponse({'status': 'OK'})

        elif order_status in ['FAILED', 'CANCELED']:
            order_service.fail_payment(payment, webhook_data, reason=order_status)
            return JsonResponse({'status': 'OK'})

        else:
            logger.info(f"Unhandled order status: {order_status}")
            return JsonResponse({'status': 'OK'})

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook: {str(e)}")
        return JsonResponse({'status': 'ERROR'}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return JsonResponse({'status': 'ERROR'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@require_http_methods(["GET"])
def health_check(request):
    """GET /api/health - Health check endpoint"""
    return JsonResponse({'status': 'OK', 'service': 'payment-service'})

