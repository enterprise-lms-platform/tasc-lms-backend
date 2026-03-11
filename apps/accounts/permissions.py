from rest_framework import permissions
from apps.accounts.rbac import is_tasc_admin


class IsTascAdminUser(permissions.BasePermission):
    """
    Allows access only to users with the TASC_ADMIN role.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_tasc_admin(request.user))
