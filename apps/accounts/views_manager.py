from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from .models import Membership
from .serializers import ManagerOrganizationSerializer

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
