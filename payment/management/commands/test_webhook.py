import json
import hashlib
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from payments.models import Order, Payment
from payments.services import OrderService
import uuid


class Command(BaseCommand):
    help = 'Testowanie webhooka PayU - symuluje webhook z PayU sandbox'

    def add_arguments(self, parser):
        parser.add_argument(
            '--order-id',
            type=str,
            help='ID order do przetestowania',
        )
        parser.add_argument(
            '--status',
            type=str,
            default='COMPLETED',
            choices=['COMPLETED', 'FAILED', 'CANCELED'],
            help='Status do wysłania w webhooku',
        )

    def handle(self, *args, **options):
        order_id = options.get('order_id')
        status = options.get('status')

        if not order_id:
            # Tworzenie test order
            self.stdout.write(self.style.WARNING('Tworzę test order...'))

            order_service = OrderService()
            order = order_service.create_order(
                appointment_id=uuid.uuid4(),
                patient_id=uuid.uuid4(),
                amount=Decimal('100.00'),
                currency='PLN',
                description='Test order via management command',
            )

            try:
                payment = order_service.initiate_payment(order)
                payu_order_id = payment.payu_order_id
                self.stdout.write(self.style.SUCCESS(f'✅ Order created: {order.id}'))
                self.stdout.write(f'   Payment ID: {payment.payu_order_id}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error creating payment: {str(e)}'))
                self.stdout.write('   (Sprawdzić czy PayU credentials są poprawne)')
                return
        else:
            # Znalezienie istniejącego order
            try:
                payment = Payment.objects.get(payu_order_id=order_id)
                payu_order_id = order_id
                self.stdout.write(f'✅ Found payment: {payment.id}')
            except Payment.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ Payment not found: {order_id}'))
                return

        # Symulacja webhooka
        self.stdout.write(self.style.WARNING(f'\n📤 Symulowanie webhooka z statusem: {status}...'))

        webhook_data = {
            'order': {
                'orderId': payu_order_id,
                'orderStatus': status,
                'totalAmount': 10000,  # w groszach
                'extOrderId': str(payment.order.id),
            },
            'localMerchantId': '1234567',
        }

        # Przetworzenie webhooka
        order_service = OrderService()

        try:
            payment.refresh_from_db()

            if status == 'COMPLETED':
                order_service.complete_payment(payment, webhook_data)
                self.stdout.write(self.style.SUCCESS(f'✅ Payment completed!'))

            elif status in ['FAILED', 'CANCELED']:
                order_service.fail_payment(payment, webhook_data, reason=status)
                self.stdout.write(self.style.SUCCESS(f'✅ Payment marked as {status}'))

            payment.refresh_from_db()
            self.stdout.write(f"   Status: {payment.payu_status}")
            self.stdout.write(f"   Order status: {payment.order.status}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error processing webhook: {str(e)}'))
            return

