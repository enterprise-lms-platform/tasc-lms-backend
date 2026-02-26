from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.contrib.auth import get_user_model
from rest_framework import permissions

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

class IsLMSManager(permissions.BasePermission):
    """
    Permission to only allow LMS Managers and Admins.
    """
    
    def has_permission(self, request, view):
        # Check if user is authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check user role - adjust based on your User model
        # This assumes your User model has a 'role' field
        allowed_roles = ['lms_manager', 'tasc_admin', 'super_admin']
        user_role = getattr(request.user, 'role', '').lower()
        
        return user_role in allowed_roles
    
    def has_object_permission(self, request, view, obj):
        # Same permission for object-level
        allowed_roles = ['lms_manager', 'tasc_admin', 'super_admin']
        user_role = getattr(request.user, 'role', '').lower()
        
        return user_role in allowed_roles


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to edit.
    """
    
    def has_permission(self, request, view):
        # Allow read-only for everyone
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for authenticated users with proper role
        if not request.user or not request.user.is_authenticated:
            return False
        
        allowed_roles = ['lms_manager', 'super_admin']
        user_role = getattr(request.user, 'role', '').lower()
        
        return user_role in allowed_roles