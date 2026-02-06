from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import UserMeSerializer
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
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
                "is_staff": False,
                "is_superuser": False,
                "is_authenticated": True,
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
@api_view(["GET"])
def me(request):
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
        user.save(update_fields=["email_verified"])
        return Response(
            {"message": "Email verified successfully."}, status=status.HTTP_200_OK
        )

    return Response(
        {"detail": "Verification link expired or invalid."},
        status=status.HTTP_400_BAD_REQUEST,
    )
