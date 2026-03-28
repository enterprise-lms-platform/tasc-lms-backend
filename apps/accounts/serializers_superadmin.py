from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Organization

User = get_user_model()


class OrganizationSuperadminSerializer(serializers.ModelSerializer):
    """
    Superadmin view of Organization. Includes all fields and stats.
    """

    user_count = serializers.SerializerMethodField()

    def get_user_count(self, obj):
        # Membership.organization -> related_name "memberships" on Organization
        return obj.memberships.filter(is_active=True).count()

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
            "user_count",
            "courses_count",
            "created_at",
            "updated_at",
            "user_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user_count"]

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
