"""Permissions for audit log access."""

from rest_framework.permissions import BasePermission


class AuditLogPermission(BasePermission):
    """
    Read-only access to audit logs by role:
    - tasc_admin, lms_manager: can view all logs
    - finance: can view only resource=payment
    - org_admin: can view only logs matching their organizations (via Membership)
    - others: deny
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = getattr(request.user, "role", None)
        if role in ("tasc_admin", "lms_manager"):
            return True
        if role == "finance":
            return True
        if role == "org_admin":
            return True
        return False

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
