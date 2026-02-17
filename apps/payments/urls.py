from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    WebhookView,
    InvoiceViewSet,
    TransactionViewSet,
    PaymentMethodViewSet,
    SubscriptionViewSet,
    UserSubscriptionViewSet,
)

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'user-subscriptions', UserSubscriptionViewSet, basename='user-subscription')


urlpatterns = [
    path('', include(router.urls)),
    # FIX: Updated action mapping to 'flutterwave_webhook'
    # Reason: The ViewSet defines flutterwave_webhook() as the @action method.
    # Previous mapping to 'webhook' caused schema generation failure.
    path('webhook/<str:provider>/',
         WebhookView.as_view({'post': 'flutterwave_webhook'}),
         name='payment-webhook'),
    path('webhook/flutterwave/',
         WebhookView.as_view({'post': 'flutterwave_webhook'}),
         {'provider': 'flutterwave'},
         name='flutterwave-webhook'),
]