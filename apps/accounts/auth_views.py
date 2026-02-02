# apps/accounts/auth_views.py

from drf_spectacular.utils import extend_schema, OpenApiExample
from django.conf import settings
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    RegisterSerializer,
    UserMeSerializer,
    AuthTokensSerializer,
    EmailTokenObtainPairSerializer,
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
                value={"detail": "Email not verified. Please verify your email before logging in."},
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
        if not getattr(user, "email_verified", False) or not getattr(user, "is_active", False):
            return Response(
                {"detail": "Email not verified. Please verify your email before logging in."},
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
        user.save(update_fields=["is_active"] + (["email_verified"] if hasattr(user, "email_verified") else []))

        # Build verification link
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)

        verify_path = reverse("accounts-email-verify", kwargs={"uidb64": uidb64, "token": token})
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


@extend_schema(
    tags=["Accounts"],
    summary="Verify email",
    description="Verify a user's email using the uid and token from the verification link.",
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
            status_codes=["400"],
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
        return Response({"detail": "Invalid verification link."}, status=status.HTTP_400_BAD_REQUEST)

    if email_verification_token.check_token(user, token):
        # Mark verified + activate
        if hasattr(user, "email_verified"):
            user.email_verified = True
        user.is_active = True
        user.save(update_fields=["is_active"] + (["email_verified"] if hasattr(user, "email_verified") else []))

        return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)

    return Response({"detail": "Verification link expired or invalid."}, status=status.HTTP_400_BAD_REQUEST)
