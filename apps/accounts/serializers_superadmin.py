from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Organization, DemoRequest

User = get_user_model()


class OrganizationSuperadminSerializer(serializers.ModelSerializer):
    """
    Superadmin view of Organization. Includes all fields and stats.
    Annotation fields (users_count, courses_count) are injected by the viewset queryset.
    """

    users_count = serializers.IntegerField(read_only=True)
    courses_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "website",
            "contact_email",
            "contact_phone",
            "address",
            "city",
            "country",
            "is_active",
            "max_seats",
            "billing_email",
            "billing_address",
            "tax_id",
            "users_count",
            "courses_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "users_count", "courses_count"]

class UserSuperadminSerializer(serializers.ModelSerializer):
    """
    Superadmin view of User. Includes all fields, lockout info, and roles.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "country",
            "timezone",
            "role",
            "avatar",
            "bio",
            "date_of_birth",
            "google_id",
            "google_picture",
            "marketing_opt_in",
            "terms_accepted_at",
            "email_verified",
            "must_set_password",
            "failed_login_attempts",
            "account_locked_until",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "date_joined",
            "last_login",
            "google_id",
            "google_picture",
            "failed_login_attempts",
            "account_locked_until",
        ]


class DemoRequestSerializer(serializers.ModelSerializer):
    """Full representation of a demo request for superadmin."""

    class Meta:
        model = DemoRequest
        fields = [
            'id', 'first_name', 'last_name', 'email', 'company',
            'team_size', 'phone', 'status', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DemoRequestCreateSerializer(serializers.ModelSerializer):
    """Public-facing serializer for submitting a demo request (no auth)."""

    class Meta:
        model = DemoRequest
        fields = ['first_name', 'last_name', 'email', 'company', 'team_size', 'phone']
