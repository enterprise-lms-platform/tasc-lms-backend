from rest_framework import permissions
from apps.accounts.rbac import is_admin_like


class IsInstructorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow instructors to edit their sessions.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to the instructor or platform admins
        return obj.instructor == request.user or is_admin_like(request.user)


class IsEnrolledOrInstructor(permissions.BasePermission):
    """
    Permission to allow access only to enrolled learners or instructor.
    """
    
    def has_object_permission(self, request, view, obj):
        # Instructor always has access
        if obj.instructor == request.user:
            return True
        
        # Check if user is enrolled in the course
        if hasattr(obj, 'course'):
            return request.user.course_enrollments.filter(
                course=obj.course,
                status='active'
            ).exists()
        
        return False