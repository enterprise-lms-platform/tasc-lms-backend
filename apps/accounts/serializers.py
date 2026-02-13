from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils import timezone as dj_timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()

from .models import Organization, Membership


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login using email + password (without relying on username auth backend).
    Returns {refresh, access}.
    """

    username_field = "email"

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip().lower()
        password = attrs.get("password")

        if not email or not password:
            raise serializers.ValidationError("Email and password are required.")

        # Find user by email (case-insensitive)
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        # Password check
        if not user.check_password(password):
            raise serializers.ValidationError("Invalid email or password.")

        # Enforce verification + active status
        if hasattr(user, "email_verified") and not user.email_verified:
            raise serializers.ValidationError(
                "Email not verified. Please verify your email."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "Account is inactive. Please verify your email."
            )

        refresh = RefreshToken.for_user(user)

        # TokenObtainPairView expects serializer.user to be set
        self.user = user

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class UserMeSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "country",
            "timezone",
            "role",
            "google_picture",
            "marketing_opt_in",
            "terms_accepted_at",
            "email_verified",
            "is_active",
        ]

    def get_name(self, obj) -> str:
        full = (obj.get_full_name() or "").strip()
        if full:
            return full
        return getattr(obj, "username", obj.email)


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Editable profile fields only; used for PATCH /api/v1/auth/me/."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
            "country",
            "timezone",
            "date_of_birth",
            "avatar",
            "bio",
            "marketing_opt_in",
        ]
        extra_kwargs = {
            "first_name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
            "phone_number": {"required": False, "allow_blank": True, "max_length": 32},
            "country": {"required": False, "allow_blank": True, "max_length": 80},
            "timezone": {"required": False, "allow_blank": True, "max_length": 80},
            "date_of_birth": {"required": False, "allow_null": True},
            "avatar": {"required": False, "allow_blank": True, "allow_null": True},
            "bio": {"required": False, "allow_blank": True},
            "marketing_opt_in": {"required": False},
        }


class AuthTokensSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()
    user = UserMeSerializer()


class RegisterSerializer(serializers.Serializer):
    # Step 1
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=5)
    confirm_password = serializers.CharField(write_only=True, min_length=5)

    # Step 2
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(
        max_length=32, required=False, allow_blank=True
    )
    country = serializers.CharField(max_length=80, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=80, required=False, allow_blank=True)

    # Step 3
    accept_terms = serializers.BooleanField()
    marketing_opt_in = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        if not attrs.get("accept_terms"):
            raise serializers.ValidationError(
                {"accept_terms": "You must accept the Terms and Privacy Policy."}
            )

        if User.objects.filter(email__iexact=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Email is already registered."})

        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password", None)
        password = validated_data.pop("password")
        accept_terms = validated_data.pop("accept_terms")

        # IMPORTANT: remove email from validated_data so it isn't passed twice
        email = validated_data.pop("email").strip().lower()

        # Generate username (since UI doesn't capture it)
        base_username = email.split("@")[0][:25]
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            i += 1
            username = f"{base_username}{i}"

        user = User(
            username=username,
            email=email,
            terms_accepted_at=dj_timezone.now() if accept_terms else None,
            **validated_data,  # now safe: email is not inside here
        )
        user.set_password(password)

        # Your model already defaults role=learner, so no need to set it here.
        # But leaving this in is harmless if role is blank for any reason:
        if hasattr(user, "role") and not getattr(user, "role", None):
            user.role = "learner"

        user.save()
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Don’t reveal whether the email exists (security best practice)
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        # Validate strength using Django validators
        validate_password(attrs["new_password"])

        # Resolve user
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uidb64"]))
            user = User.objects.get(pk=uid)
        except Exception:
            raise serializers.ValidationError({"uidb64": "Invalid user identifier."})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Invalid or expired token."})

        attrs["user"] = user
        return attrs


class ResendVerificationEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Don't reveal whether email exists (avoid account enumeration)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        # Django's built-in password strength validators
        validate_password(attrs["new_password"])

        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class InviteUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=User.Role.choices)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_role(self, value):
        """Prevent inviting users as learner or tasc_admin."""
        if value in ["learner", "tasc_admin"]:
            raise serializers.ValidationError(
                f"Cannot invite users with role '{value}'. "
                "Learners should self-register, and TASC Admins require superuser privileges."
            )
        return value


class SetPasswordFromInviteSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        # Validate password strength
        validate_password(attrs["new_password"])

        # Resolve user
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uidb64"]))
            user = User.objects.get(pk=uid)
        except Exception:
            raise serializers.ValidationError({"uidb64": "Invalid user identifier."})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Invalid or expired token."})

        attrs["user"] = user
        return attrs
