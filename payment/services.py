import logging
import json
import hashlib
import requests
import boto3
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.conf import settings
from .models import Order, Payment, PaymentStatus, AuditLog
import hmac

logger = logging.getLogger(__name__)


class PayUService:
    """Serwis do integracji z PayU API"""

    def __init__(self):
        self.merchant_id = settings.PAYU_MERCHANT_ID
        self.api_key = settings.PAYU_API_KEY
        self.oauth_client_id = settings.PAYU_OAUTH_CLIENT_ID
        self.oauth_client_secret = settings.PAYU_OAUTH_CLIENT_SECRET
        self.base_url = settings.PAYU_BASE_URL
        self.access_token = None
        self.token_expires_at = None

    def get_access_token(self):
        """Pobranie tokenu OAuth2 z PayU"""
        if self.access_token and timezone.now() < self.token_expires_at:
            return self.access_token

        url = f"{self.base_url}/pl/standard/user/oauth/authorize"
        auth = (self.oauth_client_id, self.oauth_client_secret)
        data = {'grant_type': 'client_credentials'}

        try:
            response = requests.post(url, auth=auth, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data['access_token']
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = timezone.now() + timedelta(seconds=expires_in - 60)

            logger.info(f"PayU token obtained, expires in {expires_in}s")
            return self.access_token

        except requests.RequestException as e:
            logger.error(f"Failed to get PayU access token: {str(e)}")
            raise Exception(f"PayU authentication failed: {str(e)}")

    def create_order(self, order: Order, customer_ip: str = "127.0.0.1"):
        """Stworzenie zamówienia w PayU"""
        access_token = self.get_access_token()

        url = f"{self.base_url}/api/v2_1/orders"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

        payload = {
            "notifyUrl": f"{settings.BASE_URL}/api/payments/webhook",
            "customerIp": customer_ip,
            "merchantPosId": self.merchant_id,
            "description": order.description,
            "currencyCode": order.currency,
            "totalAmount": int(order.amount * 100),  # PayU oczekuje kwoty w groszach
            "buyer": {
                "customerId": str(order.patient_id),
            },
            "products": [
                {
                    "name": order.description,
                    "unitPrice": int(order.amount * 100),
                    "quantity": 1,
                }
            ],
            "extOrderId": str(order.id),  # Unikalny ID zamówienia w naszym systemie
        }

        try:
            # PayU returns 302 redirect — do not follow it, the JSON body contains orderId + redirectUri
            response = requests.post(url, json=payload, headers=headers, timeout=10, allow_redirects=False)

            if response.status_code not in (200, 201, 302):
                response.raise_for_status()

            payu_response = response.json()
            logger.info(f"PayU order created: {payu_response}")

            return payu_response

        except requests.RequestException as e:
            logger.error(f"Failed to create PayU order for {order.id}: {str(e)}")
            raise Exception(f"PayU order creation failed: {str(e)}")

    def verify_webhook_signature(self, request_body: str, signature_header: str):
        """Weryfikacja sygnatury webhooka z PayU.

        Nagłówek OpenPayU-Signature ma format:
        sender=checkout;signature=<md5>;algorithm=MD5;content=DOCUMENT
        """
        sig_value = None
        for part in signature_header.split(';'):
            if part.startswith('signature='):
                sig_value = part.split('=', 1)[1]
                break
        if not sig_value:
            return False
        message = request_body + self.api_key
        computed_sig = hashlib.md5(message.encode()).hexdigest()
        return hmac.compare_digest(computed_sig, sig_value)

    def refund_order(self, payment: Payment):
        """Zwrot pieniędzy w PayU"""
        access_token = self.get_access_token()

        url = f"{self.base_url}/api/v2_1/orders/{payment.payu_order_id}/refunds"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

        payload = {
            "refund": {
                "description": f"Refund for order {payment.order.id}",
            }
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            refund_response = response.json()
            logger.info(f"PayU refund initiated: {refund_response}")

            return refund_response

        except requests.RequestException as e:
            logger.error(f"Failed to refund PayU payment {payment.id}: {str(e)}")
            raise Exception(f"PayU refund failed: {str(e)}")


class SQSService:
    """Serwis do publikacji wiadomości na AWS SQS.
    Jeżeli brak wymaganych zmiennych środowiskowych, serwis działa w trybie disabled (no-op).
    """

    def __init__(self):
        self.enabled = bool(
            settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.SQS_PAYMENT_SUCCESS_QUEUE_URL and settings.SQS_PAYMENT_FAILED_QUEUE_URL
        )
        if not self.enabled:
            logger.warning("SQSService disabled: missing AWS credentials or queue URLs. Messages will not be published to SQS.")
            self.sqs_client = None
            self.success_queue_url = None
            self.failed_queue_url = None
            return

        # Jeśli mamy creds, zainicjalizuj klienta boto3
        self.sqs_client = boto3.client(
            'sqs',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self.success_queue_url = settings.SQS_PAYMENT_SUCCESS_QUEUE_URL
        self.failed_queue_url = settings.SQS_PAYMENT_FAILED_QUEUE_URL

    def publish_payment_success(self, payment: Payment):
        """Publikacja wiadomości o udanej płatności"""
        message = {
            'event': 'payment.success',
            'payment_id': str(payment.id),
            'order_id': str(payment.order.id),
            'appointment_id': str(payment.order.appointment_id),
            'patient_id': str(payment.order.patient_id),
            'amount': str(payment.amount),
            'currency': payment.currency,
            'completed_at': payment.completed_at.isoformat(),
        }

        if not self.enabled:
            logger.info(f"SQS disabled — skipping publish payment.success for payment {payment.id}")
            return None

        return self._publish_message(self.success_queue_url, message)

    def publish_payment_failed(self, payment: Payment, reason: str = ""):
        """Publikacja wiadomości o nie powiodłej płatności"""
        message = {
            'event': 'payment.failed',
            'payment_id': str(payment.id),
            'order_id': str(payment.order.id),
            'appointment_id': str(payment.order.appointment_id),
            'patient_id': str(payment.order.patient_id),
            'amount': str(payment.amount),
            'currency': payment.currency,
            'reason': reason,
            'failed_at': timezone.now().isoformat(),
        }

        if not self.enabled:
            logger.info(f"SQS disabled — skipping publish payment.failed for payment {payment.id}")
            return None

        return self._publish_message(self.failed_queue_url, message)

    def _publish_message(self, queue_url: str, message: dict):
        """Wewnętrzna metoda do publikacji wiadomości"""
        try:
            response = self.sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'event_type': {
                        'StringValue': message.get('event', 'unknown'),
                        'DataType': 'String',
                    }
                }
            )
            logger.info(f"Message published to SQS: {response.get('MessageId')}")
            return response

        except Exception as e:
            # Logujemy szczegóły, nie przerywamy przetwarzania webhooka w środowisku lokalnym
            logger.error(f"Failed to publish message to SQS (queue_url={queue_url}): {e}")
            logger.debug("SQS message payload: %s", json.dumps(message))
            return None


class OrderService:
    """Serwis do zarządzania zamówieniami"""

    def __init__(self):
        self.payu_service = PayUService()
        self.sqs_service = SQSService()

    def create_order(self, appointment_id, patient_id, amount, currency='PLN', description=''):
        """Tworzenie nowego zamówienia"""
        expires_at = timezone.now() + timedelta(minutes=15)  # 15 minut na płatność

        order = Order.objects.create(
            appointment_id=appointment_id,
            patient_id=patient_id,
            amount=amount,
            currency=currency,
            status='PENDING',
            description=description,
            expires_at=expires_at,
        )

        # Audit log
        AuditLog.objects.create(
            action='ORDER_CREATED',
            actor_type='SYSTEM',
            order=order,
            details={
                'amount': str(amount),
                'currency': currency,
                'description': description,
            }
        )

        logger.info(f"Order created: {order.id}")
        return order

    def initiate_payment(self, order: Order, customer_ip: str = "127.0.0.1"):
        """Inicjacja płatności w PayU"""
        try:
            payu_response = self.payu_service.create_order(order, customer_ip=customer_ip)

            payment = Payment.objects.create(
                order=order,
                payu_order_id=payu_response['orderId'],
                amount=order.amount,
                currency=order.currency,
                payu_status='PENDING',
                payu_response=payu_response,
            )

            order.status = 'RESERVED'
            order.save()

            # Audit log
            AuditLog.objects.create(
                action='PAYMENT_INITIATED',
                actor_type='SYSTEM',
                order=order,
                payment=payment,
                details={'payu_order_id': payu_response['orderId']},
            )

            logger.info(f"Payment initiated for order {order.id}: {payment.id}")
            return payment

        except Exception as e:
            logger.error(f"Failed to initiate payment for order {order.id}: {str(e)}")

            AuditLog.objects.create(
                action='PAYMENT_INITIATED',
                actor_type='SYSTEM',
                order=order,
                details={'error': str(e)},
            )
            raise

    def complete_payment(self, payment: Payment, webhook_data: dict):
        """Zakończenie płatności"""
        old_status = payment.payu_status
        payment.payu_status = 'COMPLETED'
        payment.completed_at = timezone.now()
        payment.payu_notify_response = webhook_data
        payment.save()

        # Historia statusów
        PaymentStatus.objects.create(
            payment=payment,
            old_status=old_status,
            new_status='COMPLETED',
            reason='Webhook z PayU',
            webhook_data=webhook_data,
        )

        # Zmiana statusu zamówienia
        payment.order.status = 'COMPLETED'
        payment.order.save()

        # Audit log
        AuditLog.objects.create(
            action='PAYMENT_COMPLETED',
            actor_type='WEBHOOK',
            payment=payment,
            order=payment.order,
            details={'webhook_data': webhook_data},
        )

        # Publikacja zdarzenia
        self.sqs_service.publish_payment_success(payment)

        logger.info(f"Payment completed: {payment.id}")

    def fail_payment(self, payment: Payment, webhook_data: dict, reason: str = ""):
        """Nieudana płatność"""
        old_status = payment.payu_status
        payment.payu_status = 'FAILED'
        payment.payu_notify_response = webhook_data
        payment.save()

        # Historia statusów
        PaymentStatus.objects.create(
            payment=payment,
            old_status=old_status,
            new_status='FAILED',
            reason=reason or 'Webhook z PayU',
            webhook_data=webhook_data,
        )

        # Zmiana statusu zamówienia
        payment.order.status = 'EXPIRED'
        payment.order.save()

        # Audit log
        AuditLog.objects.create(
            action='PAYMENT_FAILED',
            actor_type='WEBHOOK',
            payment=payment,
            order=payment.order,
            details={'webhook_data': webhook_data, 'reason': reason},
        )

        # Publikacja zdarzenia
        self.sqs_service.publish_payment_failed(payment, reason)

        logger.info(f"Payment failed: {payment.id} - {reason}")

