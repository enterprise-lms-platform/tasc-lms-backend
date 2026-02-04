from django.contrib.auth import get_user_model
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
            "marketing_opt_in",
            "terms_accepted_at",
            "email_verified",
            "is_active",
            "is_staff",
            "is_superuser",
        ]

    def get_name(self, obj) -> str:
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

# Organization and Membership Serializers

from .models import Organization, Membership


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""
    member_count = serializers.SerializerMethodField()
    active_enrollments = serializers.SerializerMethodField()
    
    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'description', 'logo', 'website',
            'contact_email', 'contact_phone', 'address', 'city', 'country',
            'is_active', 'max_seats',
            'billing_email', 'billing_address', 'tax_id',
            'member_count', 'active_enrollments',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_member_count(self, obj):
        return obj.memberships.filter(is_active=True).count()
    
    def get_active_enrollments(self, obj):
        return obj.enrollments.filter(status='active').count()


class OrganizationCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating organizations."""
    
    class Meta:
        model = Organization
        fields = [
            'name', 'slug', 'description', 'logo', 'website',
            'contact_email', 'contact_phone', 'address', 'city', 'country',
            'is_active', 'max_seats',
            'billing_email', 'billing_address', 'tax_id'
        ]


class MembershipSerializer(serializers.ModelSerializer):
    """Serializer for Membership model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    organization_logo = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = Membership
        fields = [
            'id', 'user', 'user_name', 'user_email', 'user_avatar',
            'organization', 'organization_name', 'organization_logo',
            'role', 'role_display', 'is_active', 'joined_at',
            'job_title', 'department', 'manager'
        ]
        read_only_fields = ['id', 'joined_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_user_avatar(self, obj):
        return obj.user.avatar
    
    def get_organization_name(self, obj):
        return obj.organization.name
    
    def get_organization_logo(self, obj):
        return obj.organization.logo


class MembershipCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating memberships."""
    
    class Meta:
        model = Membership
        fields = [
            'user', 'organization', 'role', 'is_active',
            'job_title', 'department', 'manager'
        ]
