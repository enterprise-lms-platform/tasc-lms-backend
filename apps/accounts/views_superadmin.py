from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

User = get_user_model()
from .models import Organization
from .serializers_superadmin import OrganizationSuperadminSerializer, UserSuperadminSerializer
from .permissions import IsTascAdminUser


class OrganizationSuperadminViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Organizations intended for Superadmins (TASC_ADMIN).
    """

    queryset = Organization.objects.all().order_by("-created_at")
    serializer_class = OrganizationSuperadminSerializer
    permission_classes = [IsTascAdminUser]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Returns high-level KPI counts for organizations.
        """
        qs = self.get_queryset()
        total = qs.count()
        active = qs.filter(is_active=True).count()
        suspended = qs.filter(is_active=False).count()
        
        # In a real app 'pending' might refer to something else, 
        # but matching the request requirements with active/suspended.
        
        return Response(
            {
                "total": total,
                "active": active,
                "suspended": suspended,
            }
        )


class UserSuperadminViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Users intended for Superadmins (TASC_ADMIN).
    """

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSuperadminSerializer
    permission_classes = [IsTascAdminUser]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Returns high-level KPI counts for users.
        """
        qs = self.get_queryset()
        
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total = qs.count()
        active = qs.filter(is_active=True).count()
        new_this_month = qs.filter(date_joined__gte=start_of_month).count()
        suspended = qs.filter(is_active=False).count()

        return Response(
            {
                "total": total,
                "active": active,
                "new_this_month": new_this_month,
                "suspended": suspended,
            }
        )

    @action(detail=False, methods=["post"])
    def bulk_import(self, request):
        """
        Accepts a CSV file of users and imports them.
        (Stub implementation for now)
        """
        # TODO: Implement actual CSV parsing and user creation
        return Response({"message": "Bulk import started.", "imported": 0})

    @action(detail=False, methods=["get"])
    def csv_template(self, request):
        """
        Returns a CSV template for bulk user import.
        """
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_import_template.csv"'

        writer = csv.writer(response)
        writer.writerow(['email', 'first_name', 'last_name', 'role', 'phone_number'])
        writer.writerow(['example@domain.com', 'John', 'Doe', 'learner', '+1234567890'])

        return response
