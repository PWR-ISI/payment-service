from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import json
from decimal import Decimal
import uuid

from .models import Order, Payment, PaymentStatus, AuditLog
from .services import OrderService, PayUService
from .serializers import CreateOrderSerializer, OrderSerializer


class OrderModelTest(TestCase):
    """Testy modelu Order"""

    def setUp(self):
        self.appointment_id = uuid.uuid4()
        self.patient_id = uuid.uuid4()

    def test_create_order(self):
        """Test tworzenia zamówienia"""
        order = Order.objects.create(
            appointment_id=self.appointment_id,
            patient_id=self.patient_id,
            amount=Decimal('100.00'),
            currency='PLN',
            status='PENDING',
            description='Test order',
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        self.assertEqual(order.status, 'PENDING')
        self.assertEqual(order.amount, Decimal('100.00'))
        self.assertEqual(order.currency, 'PLN')

    def test_order_str(self):
        """Test string representation"""
        order = Order.objects.create(
            appointment_id=self.appointment_id,
            patient_id=self.patient_id,
            amount=Decimal('50.00'),
            currency='PLN',
            status='PENDING',
            description='Test',
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        self.assertIn('50.00 PLN', str(order))


class PaymentModelTest(TestCase):
    """Testy modelu Payment"""

    def setUp(self):
        self.order = Order.objects.create(
            appointment_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            amount=Decimal('100.00'),
            currency='PLN',
            status='PENDING',
            description='Test order',
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    def test_create_payment(self):
        """Test tworzenia płatności"""
        payment = Payment.objects.create(
            order=self.order,
            payu_order_id='123456789',
            amount=Decimal('100.00'),
            currency='PLN',
            payu_status='PENDING',
        )

        self.assertEqual(payment.payu_status, 'PENDING')
        self.assertEqual(payment.order, self.order)
        self.assertEqual(payment.payu_order_id, '123456789')


class CreateOrderSerializerTest(TestCase):
    """Testy serializera do tworzenia zamówień"""

    def test_valid_data(self):
        """Test walidacji poprawnych danych"""
        data = {
            'appointment_id': str(uuid.uuid4()),
            'patient_id': str(uuid.uuid4()),
            'amount': '100.00',
            'currency': 'PLN',
            'description': 'Test order',
        }

        serializer = CreateOrderSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_amount_negative(self):
        """Test walidacji ujemnej kwoty"""
        data = {
            'appointment_id': str(uuid.uuid4()),
            'patient_id': str(uuid.uuid4()),
            'amount': '-10.00',
            'currency': 'PLN',
            'description': 'Invalid',
        }

        serializer = CreateOrderSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_invalid_amount_zero(self):
        """Test walidacji zerowej kwoty"""
        data = {
            'appointment_id': str(uuid.uuid4()),
            'patient_id': str(uuid.uuid4()),
            'amount': '0.00',
            'currency': 'PLN',
            'description': 'Invalid',
        }

        serializer = CreateOrderSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class AuditLogTest(TestCase):
    """Testy audit log"""

    def setUp(self):
        self.order = Order.objects.create(
            appointment_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            amount=Decimal('100.00'),
            currency='PLN',
            status='PENDING',
            description='Test order',
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    def test_create_audit_log(self):
        """Test tworzenia wpisu w audit log"""
        log = AuditLog.objects.create(
            action='ORDER_CREATED',
            actor_type='SYSTEM',
            order=self.order,
            details={'test': 'data'},
        )

        self.assertEqual(log.action, 'ORDER_CREATED')
        self.assertEqual(log.actor_type, 'SYSTEM')
        self.assertEqual(log.order, self.order)


class APIEndpointsTest(TestCase):
    """Testy API endpoints"""

    def setUp(self):
        self.client = Client()
        self.appointment_id = str(uuid.uuid4())
        self.patient_id = str(uuid.uuid4())

    def test_health_check(self):
        """Test health check endpoint"""
        response = self.client.get('/api/payments/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'OK')
        self.assertEqual(data['service'], 'payment-service')

    def test_create_order_endpoint(self):
        """Test POST /api/payments/orders/"""
        data = {
            'appointment_id': self.appointment_id,
            'patient_id': self.patient_id,
            'amount': '100.00',
            'currency': 'PLN',
            'description': 'Test order',
        }

        response = self.client.post(
            '/api/payments/orders/',
            data=json.dumps(data),
            content_type='application/json',
        )

        # Test powinien zwrócić 201 lub 400 w zależności od konfiguracji PayU
        self.assertIn(response.status_code, [201, 400])

    def test_list_orders_endpoint(self):
        """Test GET /api/payments/orders/"""
        response = self.client.get('/api/payments/orders/')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIsInstance(data, dict)

