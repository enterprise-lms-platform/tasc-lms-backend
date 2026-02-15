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
    
    # FIXED: Add actions mapping for WebhookView
    path('webhook/<str:provider>/', 
         WebhookView.as_view({'post': 'webhook'}),  # Map POST to webhook action
         name='payment-webhook'),
    
    # FIXED: Flutterwave specific webhook - use the same approach
    path('webhook/flutterwave/', 
         WebhookView.as_view({'post': 'webhook'}),  # Map POST to webhook action
         {'provider': 'flutterwave'},  # This passes provider as a kwarg to the view
         name='flutterwave-webhook'),
]