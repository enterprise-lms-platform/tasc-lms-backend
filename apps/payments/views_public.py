# apps/payments/views_public.py
"""
Public (unauthenticated) read-only views for subscription plans.
Used by landing page pricing display.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Subscription
from .serializers import PublicSubscriptionPlanSerializer


@extend_schema(
    tags=['Public - Subscription Plans'],
    description='Public read-only access to active subscription plans for landing page pricing',
)
class PublicSubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public ViewSet for listing active subscription plans.
    - No authentication required
    - Returns only active plans
    - Minimal fields for public display
    """
    permission_classes = [AllowAny]
    serializer_class = PublicSubscriptionPlanSerializer
    queryset = Subscription.objects.filter(status=Subscription.Status.ACTIVE).order_by('price', 'name')

    @extend_schema(
        summary='List active subscription plans',
        description='Returns all active subscription plans for public pricing display. No authentication required.',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
