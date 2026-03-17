from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import viewsets, status
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
        CSV format: email,first_name,last_name,role,department,phone_number
        """
        import csv
        import random
        import string
        from django.db import transaction
        from django.contrib.auth.hashers import make_password
        
        if 'file' not in request.FILES:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        csv_file = request.FILES['file']
        
        if not csv_file.name.endswith('.csv'):
            return Response(
                {"error": "File must be a CSV file"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if csv_file.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File size exceeds 10 MB limit"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.DictReader(decoded_file.splitlines())
        except Exception as e:
            return Response(
                {"error": f"Failed to parse CSV file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_roles = ['learner', 'instructor', 'manager']
        
        total_rows = 0
        imported = 0
        errors = []
        
        users_to_create = []
        
        for row_num, row in enumerate(reader, start=2):
            total_rows += 1
            
            email = row.get('email', '').strip()
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            role = row.get('role', 'learner').strip().lower()
            department = row.get('department', '').strip()
            phone_number = row.get('phone_number', '').strip()
            
            if not email:
                errors.append({
                    "row": row_num,
                    "email": "",
                    "error": "Email is required"
                })
                continue
            
            import re
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": "Invalid email format"
                })
                continue
            
            if User.objects.filter(email=email).exists():
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": "User already exists"
                })
                continue
            
            if role not in valid_roles:
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": f"Invalid role: '{role}'. Must be one of: {', '.join(valid_roles)}"
                })
                continue
            
            if total_rows > 5000:
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": "Max 5000 records per file exceeded"
                })
                break
            
            random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                department=department,
                phone_number=phone_number,
                password=make_password(random_password),
                is_active=True,
            )
            users_to_create.append(user)
        
        if users_to_create:
            try:
                with transaction.atomic():
                    User.objects.bulk_create(users_to_create)
                    imported = len(users_to_create)
            except Exception as e:
                errors.append({
                    "row": 0,
                    "email": "",
                    "error": f"Database error: {str(e)}"
                })
                imported = 0
        
        return Response({
            "message": "Bulk import completed.",
            "total_rows": total_rows,
            "imported": imported,
            "failed": len(errors),
            "errors": errors[:100]
        })

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
