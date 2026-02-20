from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import UserMeSerializer, ProfileUpdateSerializer, InviteUserSerializer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_str, force_bytes
from django.contrib.auth.tokens import default_token_generator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .tokens import email_verification_token

from apps.notifications.services import send_tasc_email

User = get_user_model()


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

    # Send invitation email
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

    return Response(
        {"detail": "Invitation sent successfully", "email": user.email},
        status=status.HTTP_201_CREATED,
    )
