# apps/accounts/auth_views.py

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter

from django.conf import settings
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings

from rest_framework import status, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    RegisterSerializer,
    UserMeSerializer,
    AuthTokensSerializer,
    EmailTokenObtainPairSerializer,
    ResendVerificationEmailSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)

from .tokens import email_verification_token


User = get_user_model()


class LoginView(TokenObtainPairView):
    """
    Login using email + password.
    Returns JWT tokens plus user payload so frontend can bootstrap immediately.
    """

    serializer_class = EmailTokenObtainPairSerializer

    @extend_schema(
        tags=["Accounts"],
        summary="Login",
        description="Obtain access/refresh tokens and basic user profile using email + password.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "example": "peter@test.com"},
                    "password": {"type": "string", "example": "peter"},
                },
                "required": ["email", "password"],
            }
        },
        responses={200: AuthTokensSerializer},
        examples=[
            OpenApiExample(
                "Login OK",
                value={
                    "access": "jwt-access-token",
                    "refresh": "jwt-refresh-token",
                    "user": {
                        "id": 1,
                        "name": "Full Name",
                        "email": "example@email.com",
                        "username": "username",
                        "email_verified": True,
                        "is_active": True,
                        "is_staff": False,
                        "is_superuser": False,
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Email not verified",
                value={
                    "detail": "Email not verified. Please verify your email before logging in."
                },
                response_only=True,
                status_codes=["403"],
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.user

        # Block login until email verified / activated
        if not getattr(user, "email_verified", False) or not getattr(
            user, "is_active", False
        ):
            return Response(
                {
                    "detail": "Email not verified. Please verify your email before logging in."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = serializer.validated_data  # {"refresh": "...", "access": "..."}

        data = {
            "refresh": tokens["refresh"],
            "access": tokens["access"],
            "user": UserMeSerializer(user).data,
        }
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Accounts"],
    summary="Refresh token",
    description="Exchange refresh token for a new access token.",
    examples=[
        OpenApiExample(
            "Refresh OK",
            value={"access": "new-jwt-access-token"},
            response_only=True,
        )
    ],
)
class RefreshView(TokenRefreshView):
    """
    Wrapper around SimpleJWT refresh view so Swagger tagging works.
    """

    pass


class RegisterView(APIView):
    """
    Register user (inactive), send email verification link.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Accounts"],
        summary="Register",
        description="Create a new user account and send an email verification link. User cannot login until verified.",
        request=RegisterSerializer,
        responses={201: dict},
        examples=[
            OpenApiExample(
                "Register OK",
                value={
                    "message": "Account created successfully. Verification email sent.",
                    "user": {
                        "id": 2,
                        "name": "Peter Kakuru",
                        "email": "peter@test.com",
                        "username": "peter2",
                        "first_name": "Peter",
                        "last_name": "Kakuru",
                        "phone_number": "+256784512457",
                        "country": "Uganda",
                        "timezone": "Nairobi",
                        "marketing_opt_in": False,
                        "terms_accepted_at": "2026-02-02T04:12:35Z",
                        "email_verified": False,
                        "is_active": False,
                        "is_staff": False,
                        "is_superuser": False,
                    },
                },
                response_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        # Force unverified + inactive until verified
        if hasattr(user, "email_verified"):
            user.email_verified = False
        user.is_active = False
        user.save(
            update_fields=["is_active"]
            + (["email_verified"] if hasattr(user, "email_verified") else [])
        )

        # Build verification link
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)

        verify_path = reverse(
            "accounts-email-verify", kwargs={"uidb64": uidb64, "token": token}
        )
        verify_url = request.build_absolute_uri(verify_path)

        send_mail(
            subject="Verify your TASC LMS account",
            message=f"Click the link to verify your email: {verify_url}",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[user.email],
            fail_silently=False,
        )

        return Response(
            {
                "message": "Account created successfully. Verification email sent.",
                "user": UserMeSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class VerifyEmailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


@extend_schema(
    tags=["Accounts"],
    summary="Verify email",
    description="Verify a user's email using the uid and token from the verification link.",
    parameters=[
        OpenApiParameter(name="uidb64", type=str, location=OpenApiParameter.PATH),
        OpenApiParameter(name="token", type=str, location=OpenApiParameter.PATH),
    ],
    responses={
        200: VerifyEmailResponseSerializer,
        400: VerifyEmailErrorSerializer,
    },
    examples=[
        OpenApiExample(
            "Verified",
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
        # Mark verified + activate
        if hasattr(user, "email_verified"):
            user.email_verified = True
        user.is_active = True
        user.save(
            update_fields=["is_active"]
            + (["email_verified"] if hasattr(user, "email_verified") else [])
        )

        return Response(
            {"message": "Email verified successfully."}, status=status.HTTP_200_OK
        )

    return Response(
        {"detail": "Verification link expired or invalid."},
        status=status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(
    tags=["Accounts"],
    summary="Request password reset",
    description=(
        "Request a password reset email.\n\n"
        "If the email exists, a reset link will be sent.\n"
        "For security reasons, the response is always the same "
        "whether the email exists or not."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {"email": {"type": "string", "example": "user@example.com"}},
            "required": ["email"],
        }
    },
    responses={
        200: {
            "type": "object",
            "properties": {
                "detail": {
                    "type": "string",
                    "example": (
                        "If an account with that email exists, "
                        "a password reset link has been sent."
                    ),
                }
            },
        }
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    Sends a password reset email (always returns success message to avoid email enumeration).
    """
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"].lower().strip()
    user = User.objects.filter(email__iexact=email).first()

    # Always respond with success, even if user doesn't exist
    if user:
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # Use env-configurable frontend base URL if you have it; fallback to a sane default
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000")
        reset_link = f"{frontend_base}/reset-password/{uidb64}/{token}/"

        subject = "Reset your password"
        message = (
            f"Hello {user.first_name or ''},\n\n"
            f"You requested a password reset.\n"
            f"Use the link below to set a new password:\n\n"
            f"{reset_link}\n\n"
            f"If you did not request this, ignore this email.\n"
        )
        user.email_user(subject, message)

    return Response(
        {
            "detail": "If an account with that email exists, a password reset link has been sent."
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Accounts"],
    summary="Confirm password reset",
    description=(
        "Confirm a password reset using the link sent by email.\n\n"
        "The link contains a user identifier (uidb64) and a reset token."
    ),
    parameters=[
        OpenApiParameter(
            name="uidb64",
            type=str,
            location=OpenApiParameter.PATH,
            description="Base64 encoded user ID",
        ),
        OpenApiParameter(
            name="token",
            type=str,
            location=OpenApiParameter.PATH,
            description="Password reset token",
        ),
    ],
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "new_password": {"type": "string"},
                "confirm_password": {"type": "string"},
            },
            "required": ["new_password", "confirm_password"],
        }
    },
    responses={200: {"description": "Password reset successful"}},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request, uidb64, token):
    """
    Confirms reset using uid + token and sets new password.
    """
    payload = {
        **request.data,
        "uidb64": uidb64,
        "token": token,
    }
    serializer = PasswordResetConfirmSerializer(data=payload)
    serializer.is_valid(raise_exception=True)

    user = serializer.validated_data["user"]
    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])

    return Response(
        {"detail": "Password has been reset successfully."}, status=status.HTTP_200_OK
    )


@extend_schema(
    tags=["Accounts"],
    summary="Resend verification email",
    description=(
        "Resend the email verification link.\n\n"
        "For security reasons, the response is always the same whether the email exists or not."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "example": "user@example.com"},
            },
            "required": ["email"],
        }
    },
    responses={
        200: {
            "type": "object",
            "properties": {
                "detail": {
                    "type": "string",
                    "example": "If an account with that email exists, a verification link has been sent.",
                }
            },
        }
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def resend_verification_email(request):
    serializer = ResendVerificationEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"].strip().lower()
    user = User.objects.filter(email__iexact=email).first()

    # Always return generic response
    if user and not getattr(user, "email_verified", False):
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000")
        verify_link = f"{frontend_base}/verify-email/{uidb64}/{token}/"

        subject = "Verify your email"
        message = (
            f"Hello {user.first_name or ''},\n\n"
            f"Please verify your email address using the link below:\n\n"
            f"{verify_link}\n\n"
            f"If you did not request this, ignore this email.\n"
        )
        user.email_user(subject, message)

    return Response(
        {
            "detail": "If an account with that email exists, a verification link has been sent."
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Accounts"],
    summary="Change password",
    description=(
        "Change the current user's password.\n\n"
        "Requires authentication (Bearer access token)."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "old_password": {"type": "string", "example": "OldPass123!"},
                "new_password": {"type": "string", "example": "NewStrongPass123!"},
                "confirm_password": {"type": "string", "example": "NewStrongPass123!"},
            },
            "required": ["old_password", "new_password", "confirm_password"],
        }
    },
    responses={
        200: {
            "type": "object",
            "properties": {
                "detail": {
                    "type": "string",
                    "example": "Password updated successfully.",
                }
            },
        },
        400: {"description": "Old password incorrect or validation error"},
        401: {"description": "Unauthorized"},
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = request.user

    old_password = serializer.validated_data["old_password"]
    if not user.check_password(old_password):
        return Response(
            {"old_password": ["Old password is incorrect."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])

    return Response(
        {"detail": "Password updated successfully."}, status=status.HTTP_200_OK
    )
