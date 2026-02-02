from django.contrib.auth import get_user_model
from django.utils import timezone as dj_timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


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
            "marketing_opt_in",
            "terms_accepted_at",
            "email_verified",
            "is_active",
            "is_staff",
            "is_superuser",
        ]

    def get_name(self, obj):
        full = (obj.get_full_name() or "").strip()
        if full:
            return full
        return getattr(obj, "username", obj.email)


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
    phone_number = serializers.CharField(max_length=32, required=False, allow_blank=True)
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
