from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from .models import Membership
from .serializers import ManagerOrganizationSerializer
from apps.payments.models import UserSubscription
from apps.learning.models import Enrollment

class ManagerOrganizationSettingsView(APIView):
    """
    View for Organization Managers to manage their organization's profile and settings.
    """
    permission_classes = [IsAuthenticated]

    def _get_organization(self, user):
        membership = user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER]
        ).first()
        if membership:
            return membership.organization
        return None

    @extend_schema(
        summary="Get organization settings",
        description="Returns the organization profile and settings for the current manager's organization.",
        responses={200: ManagerOrganizationSerializer}
    )
    def get(self, request):
        organization = self._get_organization(request.user)
        if not organization:
            return Response(
                {"detail": "No organization found or you do not have manager permissions."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = ManagerOrganizationSerializer(organization)
        return Response(serializer.data)

    @extend_schema(
        summary="Update organization settings",
        description="Updates the organization profile and settings for the current manager's organization.",
        request=ManagerOrganizationSerializer,
        responses={200: ManagerOrganizationSerializer}
    )
    def patch(self, request):
        organization = self._get_organization(request.user)
        if not organization:
            return Response(
                {"detail": "No organization found or you do not have manager permissions."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = ManagerOrganizationSerializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        summary="Update organization settings (PUT)",
        description="Updates the organization profile and settings for the current manager's organization.",
        request=ManagerOrganizationSerializer,
        responses={200: ManagerOrganizationSerializer}
    )
    def put(self, request):
        return self.patch(request)


class ManagerBillingPlanView(APIView):
    """
    Returns the active subscription plan for the manager's organization.
    GET /api/v1/auth/manager/billing/plan/
    """
    permission_classes = [IsAuthenticated]

    def _get_organization(self, user):
        membership = user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER],
            is_active=True,
        ).select_related('organization').first()
        return membership.organization if membership else None

    def get(self, request):
        org = self._get_organization(request.user)
        if not org:
            return Response(
                {'detail': 'No organization found or insufficient permissions.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        sub = UserSubscription.objects.filter(
            organization=org, status=UserSubscription.Status.ACTIVE
        ).select_related('subscription').first()

        if sub:
            return Response({
                'plan_name': sub.subscription.name,
                'price': str(sub.price),
                'currency': sub.currency,
                'billing_cycle': sub.subscription.billing_cycle,
                'renewal_date': sub.end_date,
                'user_limit': org.max_seats,
            })

        return Response({
            'plan_name': None,
            'price': '0',
            'currency': 'USD',
            'billing_cycle': None,
            'renewal_date': None,
            'user_limit': org.max_seats,
        })


class ManagerBillingUsageView(APIView):
    """
    Returns active user and course counts for the manager's organization.
    GET /api/v1/auth/manager/billing/usage/
    """
    permission_classes = [IsAuthenticated]

    def _get_organization(self, user):
        membership = user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER],
            is_active=True,
        ).select_related('organization').first()
        return membership.organization if membership else None

    def get(self, request):
        org = self._get_organization(request.user)
        if not org:
            return Response(
                {'detail': 'No organization found or insufficient permissions.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        active_users = Membership.objects.filter(
            organization=org, is_active=True
        ).count()

        active_courses = Enrollment.objects.filter(
            organization=org, status=Enrollment.Status.ACTIVE
        ).values('course').distinct().count()

        return Response({
            'active_users': active_users,
            'active_courses': active_courses,
        })
