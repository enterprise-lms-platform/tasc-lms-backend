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
    PaymentAnalyticsViewSet,
    OrganizationSubscriptionListView,
    FinanceDashboardOverviewAPIView,
    FinancePaymentViewSet,
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
router.register(r'analytics', PaymentAnalyticsViewSet, basename='payment-analytics')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'finance/payments', FinancePaymentViewSet, basename='finance-payment')
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'user-subscriptions', UserSubscriptionViewSet, basename='user-subscription')


# ── pesapal routes ─────────────────────────────────────────────────
router.register(r'pesapal', PesapalPaymentViewSet, basename='pesapal-payment')
router.register(r'pesapal/recurring', PesapalRecurringViewSet, basename='pesapal-recurring')
router.register(r'pesapal/ipn-admin', PesapalIPNViewSet, basename='pesapal-ipn')

urlpatterns = [
    path('subscription/me/', SubscriptionMeView.as_view(), name='subscription-me'),
    path('org-subscriptions/', OrganizationSubscriptionListView.as_view(), name='org-subscriptions'),
    path('finance/dashboard-overview/', FinanceDashboardOverviewAPIView.as_view(), name='finance-dashboard-overview'),
    # Backward-compatible alias (older clients used this path; router uses ipn-admin/).
    path(
        'pesapal/ipn/register/',
        PesapalIPNViewSet.as_view({'post': 'register'}),
        name='pesapal-ipn-register-legacy',
    ),
    path('', include(router.urls)),
    # Keep existing webhook routes reachable while Pesapal rollout is in progress.
    path(
        'webhook/<str:provider>/',
        WebhookView.as_view({'post': 'flutterwave_webhook'}),
        name='payment-webhook',
    ),
    path(
        'webhook/flutterwave/',
        WebhookView.as_view({'post': 'flutterwave_webhook'}),
        {'provider': 'flutterwave'},
        name='flutterwave-webhook',
    ),

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