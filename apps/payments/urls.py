from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    WebhookView,
    SubscriptionMeView,
    InvoiceViewSet,
    TransactionViewSet,
    PaymentMethodViewSet,
    SubscriptionViewSet,
    UserSubscriptionViewSet,
)

from .views_pesapal import (
        PesapalPaymentViewSet,
        PesapalRecurringViewSet,
        PesapalWebhookView,
        PesapalCallbackView,
        PesapalIPNViewSet,
    )
    # from .views_public import PublicSubscriptionPlanViewSet

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'user-subscriptions', UserSubscriptionViewSet, basename='user-subscription')


urlpatterns = [
    path('subscription/me/', SubscriptionMeView.as_view(), name='subscription-me'),
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

 # ── pesapal routes ─────────────────────────────────────────────────
router.register(r'pesapal', PesapalPaymentViewSet, basename='pesapal-payment')
router.register(r'pesapal/recurring', PesapalRecurringViewSet, basename='pesapal-recurring')
router.register(r'pesapal/ipn-admin', PesapalIPNViewSet, basename='pesapal-ipn')

urlpatterns = [
    path('', include(router.urls)),

    # These two are standalone views (not ViewSets) because Pesapal
    # calls them directly — no DRF router wrapping needed.
    path(
        'pesapal/webhook/ipn/',
        PesapalWebhookView.as_view(),
        name='pesapal-webhook-ipn',
    ),
    path(
        'pesapal/callback/',
        PesapalCallbackView.as_view(),
        name='pesapal-callback',
    ),
]