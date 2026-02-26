# apps/accounts/auth_views.py

import logging

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter
from django.conf import settings
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
#from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings

from rest_framework import status, serializers
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    RegisterSerializer,
    UserMeSerializer,
    AuthTokensSerializer,
    EmailTokenObtainPairSerializer,
    ResendVerificationEmailSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    LogoutSerializer,
    SetPasswordFromInviteSerializer,
    VerifyOTPSerializer,
    ResendOTPSerializer,
)

from .tokens import email_verification_token
from .models import LoginOTPChallenge
from .utils import generate_otp, hash_otp, verify_otp
from .services import send_login_otp_email

from apps.notifications.services import send_tasc_email, send_account_locked_email
from django.utils import timezone
from datetime import timedelta


User = get_user_model()
logger = logging.getLogger(__name__)


def _log_otp_send_failure(user, request, reason: str) -> None:
    try:
        from apps.audit.services import log_event

        log_event(
            actor=user,
            action="failed",
            resource="otp",
            resource_id=str(getattr(user, "id", "")),
            request=request,
            details=f"OTP email send failed for {getattr(user, 'email', '')}: {reason}",
        )
    except Exception:
        logger.exception(
            "Failed to write OTP failure audit log",
            extra={"user_id": getattr(user, "id", None), "email": getattr(user, "email", "")},
        )


class LoginView(TokenObtainPairView):
    """
    Login step 1: email + password.
    On success, sends OTP email and returns challenge_id for verify-otp step.
    """

    serializer_class = EmailTokenObtainPairSerializer

    @extend_schema(
        tags=["Accounts"],
        summary="Login",
        description=(
            "Step 1: Submit email + password. On success, an OTP is sent to your email. "
            "Use the challenge_id with POST /auth/login/verify-otp/ to complete login."
        ),
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
        responses={
            200: {
                "type": "object",
                "properties": {
                    "mfa_required": {"type": "boolean"},
                    "method": {"type": "string"},
                    "challenge_id": {"type": "string", "format": "uuid"},
                    "expires_in": {"type": "integer"},
                },
            },
        },
        examples=[
            OpenApiExample(
                "MFA required",
                value={
                    "mfa_required": True,
                    "method": "email_otp",
                    "challenge_id": "550e8400-e29b-41d4-a716-446655440000",
                    "expires_in": 300,
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
        email = (request.data.get("email") or "").strip().lower()
        user_by_email = User.objects.filter(email__iexact=email).first() if email else None

        # B) If user exists and is locked, return 403 (avoid revealing valid email)
        if user_by_email and getattr(user_by_email, "account_locked_until", None):
            if timezone.now() < user_by_email.account_locked_until:
                return Response(
                    {"detail": "Account locked. Try again later or reset your password."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError:
            # C) Invalid credentials: increment and possibly lock (only if we have a user)
            if user_by_email:
                user_by_email.failed_login_attempts = (getattr(user_by_email, "failed_login_attempts", 0) or 0) + 1
                max_attempts = getattr(settings, "MAX_LOGIN_ATTEMPTS", 5)
                if user_by_email.failed_login_attempts >= max_attempts:
                    lock_minutes = getattr(settings, "ACCOUNT_LOCK_MINUTES", 15)
                    user_by_email.account_locked_until = timezone.now() + timedelta(minutes=lock_minutes)
                    user_by_email.failed_login_attempts = 0
                    user_by_email.save(update_fields=["failed_login_attempts", "account_locked_until"])
                    send_account_locked_email(user_by_email)
                else:
                    user_by_email.save(update_fields=["failed_login_attempts"])
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

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

        # D) Successful password validation: clear lockout fields
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.save(update_fields=["failed_login_attempts", "account_locked_until"])

        # E) Create OTP challenge instead of issuing tokens
        ttl_seconds = getattr(settings, "LOGIN_OTP_TTL_SECONDS", 300)
        try:
            with transaction.atomic():
                now = timezone.now()
                otp = generate_otp()
                challenge = LoginOTPChallenge.objects.create(
                    user=user,
                    otp_hash=hash_otp(otp),
                    expires_at=now + timedelta(seconds=ttl_seconds),
                    attempts=0,
                    send_count=1,
                    last_sent_at=now,
                    is_used=False,
                )
                send_login_otp_email(user, otp)
        except Exception as exc:
            logger.exception(
                "Login OTP email send failed",
                extra={"user_id": user.id, "email": user.email},
            )
            _log_otp_send_failure(user, request, str(exc))
            return Response(
                {"detail": "Failed to send OTP email. Please try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "mfa_required": True,
                "method": "email_otp",
                "challenge_id": str(challenge.id),
                "expires_in": ttl_seconds,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Accounts"],
    summary="Verify OTP",
    description="Step 2: Submit challenge_id and OTP code to complete login and receive JWT tokens.",
    request=VerifyOTPSerializer,
    responses={
        200: AuthTokensSerializer,
        400: {"description": "Invalid or expired code"},
        403: {"description": "Too many attempts"},
    },
)
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp_verify"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge_id = serializer.validated_data["challenge_id"]
        otp = serializer.validated_data["otp"]

        try:
            challenge = LoginOTPChallenge.objects.get(
                id=challenge_id,
                is_used=False,
                expires_at__gt=timezone.now(),
            )
        except LoginOTPChallenge.DoesNotExist:
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_attempts = getattr(settings, "LOGIN_OTP_MAX_ATTEMPTS", 5)
        if challenge.attempts >= max_attempts:
            challenge.is_used = True
            challenge.save(update_fields=["is_used"])
            return Response(
                {"detail": "Too many attempts. Please request a new code."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not verify_otp(otp, challenge.otp_hash):
            challenge.attempts += 1
            challenge.save(update_fields=["attempts"])
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenge.is_used = True
        challenge.save(update_fields=["is_used"])

        user = challenge.user
        # US-027: Log successful login (post-OTP verification)
        from apps.audit.services import log_event

        log_event(
            actor=user,
            action="login",
            resource="user",
            details="Logged in via email",
            request=request,
            resource_id=str(user.id),
        )

        refresh = RefreshToken.for_user(user)
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserMeSerializer(user).data,
        }
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Accounts"],
    summary="Resend OTP",
    description="Resend the login OTP email. Max 3 sends per challenge.",
    request=ResendOTPSerializer,
    responses={
        200: {
            "type": "object",
            "properties": {
                "detail": {"type": "string"},
                "expires_in": {"type": "integer"},
            },
        },
        429: {"description": "Max resends exceeded"},
    },
)
class ResendOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp_resend"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge_id = serializer.validated_data["challenge_id"]

        try:
            challenge = LoginOTPChallenge.objects.get(
                id=challenge_id,
                is_used=False,
                expires_at__gt=timezone.now(),
            )
        except LoginOTPChallenge.DoesNotExist:
            return Response(
                {"detail": "Invalid or expired challenge."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_resends = getattr(settings, "LOGIN_OTP_MAX_RESENDS", 3)
        if challenge.send_count >= max_resends:
            return Response(
                {"detail": "Maximum resend limit reached. Please start a new login."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ttl_seconds = getattr(settings, "LOGIN_OTP_TTL_SECONDS", 300)
        try:
            with transaction.atomic():
                challenge = LoginOTPChallenge.objects.select_for_update().get(
                    id=challenge_id,
                    is_used=False,
                    expires_at__gt=timezone.now(),
                )
                if challenge.send_count >= max_resends:
                    return Response(
                        {
                            "detail": "Maximum resend limit reached. Please start a new login."
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                now = timezone.now()
                otp = generate_otp()
                challenge.otp_hash = hash_otp(otp)
                challenge.last_sent_at = now
                challenge.expires_at = now + timedelta(seconds=ttl_seconds)
                challenge.send_count += 1
                challenge.save(
                    update_fields=["otp_hash", "last_sent_at", "expires_at", "send_count"]
                )

                send_login_otp_email(challenge.user, otp)
        except LoginOTPChallenge.DoesNotExist:
            return Response(
                {"detail": "Invalid or expired challenge."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception(
                "Resend OTP email send failed",
                extra={"user_id": challenge.user.id, "email": challenge.user.email},
            )
            _log_otp_send_failure(challenge.user, request, str(exc))
            return Response(
                {"detail": "Failed to send OTP email. Please try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"detail": "OTP sent.", "expires_in": ttl_seconds},
            status=status.HTTP_200_OK,
        )


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
        with transaction.atomic():
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

            frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
            verify_url = f"{frontend_base}/verify-email/{uidb64}/{token}"

            def _send_verification_email():
                send_tasc_email(
                    subject="Verify your TASC LMS account",
                    to=[user.email],
                    template="emails/auth/verify_email.html",
                    context={
                        "user": user,
                        "verify_url": verify_url,
                    },
                )

            transaction.on_commit(_send_verification_email)


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
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
        reset_link = f"{frontend_base}/reset-password/{uidb64}/{token}"

        # subject = "Reset your password"
        # message = (
        #     f"Hello {user.first_name or ''},\n\n"
        #     f"You requested a password reset.\n"
        #     f"Use the link below to set a new password:\n\n"
        #     f"{reset_link}\n\n"
        #     f"If you did not request this, ignore this email.\n"
        # )
        # user.email_user(subject, message)

        send_tasc_email(
            subject="Reset your password",
            to=[user.email],
            template="emails/auth/password_reset.html",
            context={
                "user": user,
                "reset_url": reset_link,
            },
        )


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
        # uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        # token = default_token_generator.make_token(user)

        # frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000")
        # verify_link = f"{frontend_base}/verify-email/{uidb64}/{token}/"

        # subject = "Verify your email"
        # message = (
        #     f"Hello {user.first_name or ''},\n\n"
        #     f"Please verify your email address using the link below:\n\n"
        #     f"{verify_link}\n\n"
        #     f"If you did not request this, ignore this email.\n"
        # )
        # user.email_user(subject, message)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)

        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
        verify_url = f"{frontend_base}/verify-email/{uidb64}/{token}"

        send_tasc_email(
            subject="Verify your TASC LMS account",
            to=[user.email],
            template="emails/auth/verify_email.html",
            context={
                "user": user,
                "verify_url": verify_url,
            },
        )


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
    serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
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

@extend_schema(
    tags=["Accounts"],
    summary="Logout (blacklist refresh token)",
    description=(
        "Logs out the current user by blacklisting the provided refresh token.\n\n"
        "After this, the refresh token can no longer be used to get new access tokens."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "refresh": {"type": "string", "example": "your.refresh.token.here"}
            },
            "required": ["refresh"],
        }
    },
    responses={
        200: {"type": "object", "properties": {"detail": {"type": "string", "example": "Logged out successfully."}}},
        400: {"description": "Invalid refresh token"},
        401: {"description": "Unauthorized"},
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    serializer = LogoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        token = RefreshToken(serializer.validated_data["refresh"])
        token.blacklist()
    except Exception:
        return Response({"refresh": ["Invalid or expired refresh token."]}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Accounts"],
    summary="Set password from invite",
    description="Invited user sets their password using the invitation link token.",
    parameters=[
        OpenApiParameter(name="uidb64", type=str, location=OpenApiParameter.PATH),
        OpenApiParameter(name="token", type=str, location=OpenApiParameter.PATH),
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
    responses={
        200: {"type": "object", "properties": {"detail": {"type": "string"}}},
        400: {"description": "Invalid token or validation error"},
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def set_password_from_invite(request, uidb64, token):
    """
    Set password for invited user using uid + token.
    """
    payload = {
        **request.data,
        "uidb64": uidb64,
        "token": token,
    }
    serializer = SetPasswordFromInviteSerializer(data=payload)
    serializer.is_valid(raise_exception=True)

    user = serializer.validated_data["user"]
    user.set_password(serializer.validated_data["new_password"])
    user.must_set_password = False
    user.save(update_fields=["password", "must_set_password"])

    return Response(
        {"detail": "Password set successfully. You can now login."},
        status=status.HTTP_200_OK,
    )
