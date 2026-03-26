import logging

from drf_spectacular.utils import extend_schema, OpenApiExample, extend_schema_view, OpenApiParameter
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response as RestResponse

from .serializers import (
    UserMeSerializer,
    ProfileUpdateSerializer,
    InviteUserSerializer,
    UserListSerializer,
    UserDetailSerializer,
    UserUpdateSerializer,
)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_str, force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import get_object_or_404
from django.db import models, IntegrityError, transaction

from .tokens import email_verification_token
from .rbac import is_admin_like

from apps.notifications.services import send_tasc_email

User = get_user_model()
logger = logging.getLogger(__name__)


@extend_schema(
    tags=["Accounts"],
    summary="Get current user",
    description="Returns basic profile info for the authenticated user.",
    responses={200: UserMeSerializer},
    examples=[
        OpenApiExample(
            "Authenticated",
            value={
                "id": 1,
                "name": "Peter Parker",
                "email": "user@example.com",
                "username": "parker",
                "is_active": True,
            },
            response_only=True,
        ),
        OpenApiExample(
            "Unauthorized",
            value={"detail": "Authentication credentials were not provided."},
            status_codes=["401"],
            response_only=True,
        ),
    ],
)
@extend_schema(
    methods=["PATCH"],
    request=ProfileUpdateSerializer,
    responses={200: UserMeSerializer},
    summary="Update profile",
    description="Partially update the authenticated user's profile.",
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "GET":
        return Response(UserMeSerializer(request.user).data)
    # PATCH
    serializer = ProfileUpdateSerializer(
        instance=request.user, data=request.data, partial=True
    )
    serializer.is_valid(raise_exception=True)
    from apps.audit.services import log_event
    serializer.save()
    log_event(
        action="updated",
        resource="user",
        resource_id=str(request.user.id),
        actor=request.user,
        request=request,
        details=f"User profile updated via /me endpoint: {request.user.email}",
    )
    return Response(UserMeSerializer(request.user).data)


@extend_schema(
tags=["Accounts"],
summary="Verify email",
description="Verify a user's email using the uid and token from the verification link.",
examples=[
    OpenApiExample(
        "Verified OK",
        value={"message": "Email verified successfully."},
        response_only=True,
    ),
    OpenApiExample(
        "Invalid/Expired",
        value={"detail": "Verification link expired or invalid."},
        response_only=True,
    ),
],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response(
            {"detail": "Invalid verification link."}, status=status.HTTP_400_BAD_REQUEST
        )

    if email_verification_token.check_token(user, token):
        user.email_verified = True
        user.is_active = True  # Activate account upon email verification
        user.save(update_fields=["email_verified", "is_active"])
        from apps.audit.services import log_event

        log_event(
            action="updated",
            resource="user",
            resource_id=str(user.id),
            actor=None,
            request=request,
            details=f"Email verified: {user.email} | is_active=True",
        )
        return Response(
            {"message": "Email verified successfully."}, status=status.HTTP_200_OK
        )

    return Response(
        {"detail": "Verification link expired or invalid."},
        status=status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(
    tags=["Admin"],
    summary="Invite user",
    description="Super Admin invites a user by email. Creates or updates user account and sends invitation email.",
    request=InviteUserSerializer,
    responses={
        201: {"type": "object", "properties": {"detail": {"type": "string"}, "email": {"type": "string"}}},
        400: {"type": "object", "properties": {"detail": {"type": "string"}}},
        403: {"type": "object", "properties": {"detail": {"type": "string"}}},
    },
    examples=[
        OpenApiExample(
            "Success",
            value={"detail": "Invitation sent successfully", "email": "user@example.com"},
            response_only=True,
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_user(request):
    # Check if user is tasc_admin
    if not hasattr(request.user, "role") or request.user.role != "tasc_admin":
        return Response(
            {"detail": "Only TASC Admins can invite users."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = InviteUserSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    from apps.audit.services import log_event

    email = serializer.validated_data["email"]
    first_name = serializer.validated_data["first_name"]
    last_name = serializer.validated_data["last_name"]
    role = serializer.validated_data["role"]

    try:
        with transaction.atomic():
            # Create or update user - find by case-insensitive email
            try:
                user = User.objects.get(email__iexact=email)
                created = False
            except User.DoesNotExist:
                # Generate unique username
                base_username = email.split("@")[0][:25]
                username = base_username
                i = 1
                while User.objects.filter(username=username).exists():
                    i += 1
                    username = f"{base_username}{i}"

                user = User.objects.create(
                    email=email,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    email_verified=True,
                    must_set_password=True,
                    is_active=True,
                )
                created = True

            if not created:
                # Update existing user
                user.first_name = first_name
                user.last_name = last_name
                user.role = role
                user.email_verified = True
                user.must_set_password = True
                user.is_active = True
                user.save(update_fields=["first_name", "last_name", "role", "email_verified", "must_set_password", "is_active"])

            # Generate token
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            # Build frontend set-password URL
            frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
            set_password_url = f"{frontend_base}/set-password/{uidb64}/{token}"

            def _send_invite_email() -> None:
                try:
                    send_tasc_email(
                        subject="You've been invited to TASC LMS",
                        to=[user.email],
                        template="emails/auth/user_invitation.html",
                        context={
                            "user": user,
                            "inviter": request.user,
                            "set_password_url": set_password_url,
                        },
                    )
                except Exception:
                    logger.exception("Failed to send invite email", extra={"email": user.email})

            transaction.on_commit(_send_invite_email)

            if created:
                log_event(
                    action="created",
                    resource="user",
                    resource_id=str(user.id),
                    actor=request.user,
                    request=request,
                    details=f"Invited user created: {user.email} (role={user.role}) | email_verified=True | must_set_password=True | is_active=True",
                )
            else:
                log_event(
                    action="updated",
                    resource="user",
                    resource_id=str(user.id),
                    actor=request.user,
                    request=request,
                    details=f"Invited user updated: {user.email} (role={user.role}) | email_verified=True | must_set_password=True | is_active=True",
                )
    except IntegrityError:
        return Response(
            {"email": ["A user with this email already exists."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {"detail": "Invitation sent successfully", "email": user.email},
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    tags=["Admin"],
    summary="Promote user to instructor",
    description="Promote a target user to instructor. Allowed for TASC Admin and LMS Manager.",
    responses={
        200: {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "user_id": {"type": "integer"},
                "new_role": {"type": "string"},
            },
        },
        403: {"type": "object", "properties": {"detail": {"type": "string"}}},
        404: {"type": "object", "properties": {"detail": {"type": "string"}}},
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def promote_user_role(request, user_id: int):
    if not is_admin_like(request.user):
        return Response(
            {"detail": "Only TASC Admins and LMS Managers can promote users."},
            status=status.HTTP_403_FORBIDDEN,
        )

    target_user = get_object_or_404(User, pk=user_id)
    old_role = target_user.role
    new_role = User.Role.INSTRUCTOR

    if old_role != new_role:
        target_user.role = new_role
        target_user.save(update_fields=["role"])

    from apps.audit.services import log_event

    log_event(
        action="updated",
        resource="user",
        resource_id=str(target_user.id),
        actor=request.user,
        request=request,
        details=(
            f"User role promoted via admin endpoint: {target_user.email} "
            f"(role={old_role} -> {new_role}) by {request.user.email}"
        ),
    )

    message = (
        "User is already an instructor."
        if old_role == new_role
        else "User promoted to instructor successfully."
    )
    return Response(
        {
            "message": message,
            "user_id": target_user.id,
            "new_role": User.Role.INSTRUCTOR,
        },
        status=status.HTTP_200_OK,
    )


# ============================================
# Admin/Manager User Management Views
# ============================================

@extend_schema_view(
    list=extend_schema(
        tags=["Accounts - Admin Users"],
        summary="List users",
        description="Returns paginated list of users. Supports filtering by role, is_active, and search by email/name.",
        parameters=[
            OpenApiParameter(
                name="role",
                description="Filter by user role (learner, instructor, org_admin, finance, tasc_admin, lms_manager)",
                type=str,
            ),
            OpenApiParameter(
                name="is_active",
                description="Filter by active status (true/false)",
                type=bool,
            ),
            OpenApiParameter(
                name="search",
                description="Search by email or name",
                type=str,
            ),
        ],
    ),
    retrieve=extend_schema(
        tags=["Accounts - Admin Users"],
        summary="Get user detail",
        description="Returns detailed information about a specific user.",
    ),
    partial_update=extend_schema(
        tags=["Accounts - Admin Users"],
        summary="Update user",
        description="Update user fields (role, active status, profile).",
        request=UserUpdateSerializer,
    ),
)
class UserAdminViewSet(viewsets.ModelViewSet):
    """
    ViewSet for admin/manager user management.
    
    Supports:
    - Listing users with filtering (role, is_active, search)
    - Retrieving user details
    - Partial updating user fields
    
    Requires TASC_ADMIN or LMS_MANAGER role.
    """
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [IsAuthenticated]
    
    def check_admin_permission(self, request):
        """Check if user has admin-like role."""
        if not is_admin_like(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only TASC Admins and LMS Managers can access this endpoint.")
        return True
    
    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated()]
        # For update actions, check admin role
        return super().get_permissions()
    
    def get_serializer_class(self):
        if self.action == "list":
            return UserListSerializer
        elif self.action in ["retrieve"]:
            return UserDetailSerializer
        return UserUpdateSerializer
    
    def get_queryset(self):
        # Check admin permission for list action
        self.check_admin_permission(self.request)
        
        queryset = User.objects.all().order_by("-date_joined")
        
        # Filter by role
        role = self.request.query_params.get("role", None)
        if role:
            queryset = queryset.filter(role=role)
        
        # Filter by is_active
        is_active = self.request.query_params.get("is_active", None)
        if is_active is not None:
            is_active_bool = is_active.lower() in ("true", "1", "yes")
            queryset = queryset.filter(is_active=is_active_bool)
        
        # Search by email or name
        search = self.request.query_params.get("search", None)
        if search:
            queryset = queryset.filter(
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search) |
                models.Q(username__icontains=search)
            )
        
        return queryset
    
    def perform_update(self, serializer):
        user = serializer.save()
        # Log the update
        from apps.audit.services import log_event
        log_event(
            action="updated",
            resource="user",
            resource_id=str(user.id),
            actor=self.request.user,
            request=self.request,
            details=f"User updated via admin API: {user.email}",
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
        
        self.check_admin_permission(request)

        if 'file' not in request.FILES:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        csv_file = request.FILES['file']
        
        if not csv_file.name.endswith('.csv'):
            return Response({"error": "File must be a CSV file"}, status=status.HTTP_400_BAD_REQUEST)
        
        if csv_file.size > 10 * 1024 * 1024:
            return Response({"error": "File size exceeds 10 MB limit"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.DictReader(decoded_file.splitlines())
        except Exception as e:
            return Response({"error": f"Failed to parse CSV file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Managers can import learners and instructors. Superadmins can also import managers.
        if getattr(request.user, 'role', '') == 'lms_manager':
            valid_roles = ['learner', 'instructor']
        else:
            valid_roles = ['learner', 'instructor', 'manager', 'lms_manager']
        
        total_rows = 0
        imported = 0
        errors = []
        users_to_create = []
        
        for row_num, row in enumerate(reader, start=2):
            total_rows += 1
            
            # Map frontend export columns to backend expected columns
            email = (row.get('email') or row.get('email_address') or '').strip()
            role = (row.get('role') or row.get('user_role') or 'learner').strip().lower()
            department = row.get('department', '').strip()
            phone_number = row.get('phone_number', '').strip()
            
            # Handle full_name splitting if first_name/last_name are missing
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            full_name = row.get('full_name', '').strip()
            
            if not first_name and not last_name and full_name:
                parts = full_name.split(' ', 1)
                first_name = parts[0]
                if len(parts) > 1:
                    last_name = parts[1]
            
            if not email:
                errors.append({"row": row_num, "email": "", "error": "Email is required"})
                continue
            
            import re
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                errors.append({"row": row_num, "email": email, "error": "Invalid email format"})
                continue
            
            if User.objects.filter(email=email).exists():
                errors.append({"row": row_num, "email": email, "error": "User already exists"})
                continue
            
            if role not in valid_roles:
                errors.append({"row": row_num, "email": email, "error": f"Invalid role: '{role}'. Must be one of: {', '.join(valid_roles)}"})
                continue
            
            if total_rows > 5000:
                errors.append({"row": row_num, "email": email, "error": "Max 5000 records per file exceeded"})
                break
            
            random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            
            user = User(
                email=email,
                username=email.split("@")[0] + ''.join(random.choices(string.digits, k=4)),
                first_name=first_name,
                last_name=last_name,
                role=role,
                department=department,
                phone_number=phone_number,
                password=make_password(random_password),
                is_active=True,
                organization=getattr(request.user, 'organization', None) if getattr(request.user, 'role', '') == 'lms_manager' else None
            )
            users_to_create.append(user)
        
        if users_to_create:
            try:
                with transaction.atomic():
                    User.objects.bulk_create(users_to_create)
                    imported = len(users_to_create)
            except Exception as e:
                errors.append({"row": 0, "email": "", "error": f"Database error: {str(e)}"})
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

        self.check_admin_permission(request)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_import_template.csv"'

        writer = csv.writer(response)
        writer.writerow(['email', 'first_name', 'last_name', 'role', 'department', 'phone_number'])
        writer.writerow(['example@domain.com', 'John', 'Doe', 'learner', 'Engineering', '+1234567890'])

        return response
