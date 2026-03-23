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


class CanEditSessionCourse(BasePermission):
    """
    Object-level: for write methods on a Session, checks that the user can edit
    the session's parent course.  Admin/manager can edit any; instructors only
    sessions belonging to their own courses.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        role = getattr(request.user, 'role', None)
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return True
        if role == User.Role.INSTRUCTOR:
            return obj.course.instructor_id == request.user.id
        return False


class CanEditModuleCourse(BasePermission):
    """
    Object-level: for write methods on a Module, checks that the user can edit
    the module's parent course.  Admin/manager can edit any; instructors only
    modules belonging to their own courses.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        role = getattr(request.user, 'role', None)
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return True
        if role == User.Role.INSTRUCTOR:
            return obj.course.instructor_id == request.user.id
        return False


class IsCategoryManagerOrReadOnly(BasePermission):
    """
    Allows SAFE_METHODS for everyone who reaches the endpoint.
    For write methods (POST, PUT, PATCH, DELETE) allows only LMS_MANAGER, TASC_ADMIN.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        role = getattr(request.user, 'role', None)
        return role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN)


class CanEditQuestionCategory(BasePermission):
    """
    Object-level: instructors can edit own categories; managers/admins can edit any.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        role = getattr(request.user, 'role', None)
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return True
        if role == User.Role.INSTRUCTOR:
            return obj.owner_id == request.user.id
        return False


class CanEditBankQuestion(BasePermission):
    """
    Object-level: instructors can edit own bank questions; managers/admins can edit any.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        role = getattr(request.user, 'role', None)
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return True
        if role == User.Role.INSTRUCTOR:
            return obj.owner_id == request.user.id
        return False


class IsApprovalManager(BasePermission):
    """
    Only LMS Manager and TASC Admin can list and view approval requests.
    """
    def has_permission(self, request, view):
        role = getattr(request.user, 'role', None)
        return role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN)
