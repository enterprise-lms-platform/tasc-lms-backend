from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.contrib.auth import get_user_model

User = get_user_model()


class IsCourseWriter(BasePermission):
    """
    Allows SAFE_METHODS for all authenticated users.
    For write methods (POST, PUT, PATCH, DELETE) allows only INSTRUCTOR, LMS_MANAGER, TASC_ADMIN.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        role = getattr(request.user, 'role', None)
        return role in (User.Role.INSTRUCTOR, User.Role.LMS_MANAGER, User.Role.TASC_ADMIN)


class CanEditCourse(BasePermission):
    """
    Object-level: managers/admin can edit any course; instructors only if obj.instructor_id == request.user.id.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        role = getattr(request.user, 'role', None)
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return True
        if role == User.Role.INSTRUCTOR:
            return obj.instructor_id == request.user.id
        return False


class CanDeleteCourse(BasePermission):
    """
    Object-level: only LMS_MANAGER and TASC_ADMIN can delete a course.
    """
    def has_object_permission(self, request, view, obj):
        if request.method != 'DELETE':
            return True
        role = getattr(request.user, 'role', None)
        return role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN)
