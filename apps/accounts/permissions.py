from rest_framework import permissions
from apps.accounts.rbac import is_tasc_admin, is_finance_dashboard_user


class IsTascAdminUser(permissions.BasePermission):
    """
    Allows access only to users with the TASC_ADMIN role.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_tasc_admin(request.user))


class IsFinanceDashboardUser(permissions.BasePermission):
    """
    Allows access to finance, tasc_admin, and lms_manager roles (plus superusers/staff).
    Replaces inline _is_finance_dashboard_user() checks in payments/views.py.
    """

    def has_permission(self, request, view):
        return is_finance_dashboard_user(request.user)
