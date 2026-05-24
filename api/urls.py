from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PaymentOrderViewSet, PaymentTransactionViewSet,
    InvoiceViewSet, PaymentRefundViewSet, health_check
)

router = DefaultRouter()
router.register(r'orders', PaymentOrderViewSet, basename='orders')
router.register(r'transactions', PaymentTransactionViewSet, basename='transactions')
router.register(r'invoices', InvoiceViewSet, basename='invoices')
router.register(r'refunds', PaymentRefundViewSet, basename='refunds')

urlpatterns = [
    path('health/', health_check, name='health'),
    path('', include(router.urls)),
]
