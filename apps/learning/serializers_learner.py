"""Learner-specific serializers for Learner Flow v1."""

from rest_framework import serializers


class LearnerEnrollmentResponseSerializer(serializers.Serializer):
    """Response shape for POST /learner/courses/<slug>/enroll/."""
    enrollment_id = serializers.IntegerField()
    course_slug = serializers.CharField()
    status = serializers.CharField()
    enrolled_at = serializers.DateTimeField()
    progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    message = serializers.CharField()


class LearnerMyCourseCourseSerializer(serializers.Serializer):
    """Nested course summary for my-courses."""
    slug = serializers.CharField()
    title = serializers.CharField()
    thumbnail = serializers.URLField(allow_null=True)
    category = serializers.DictField(allow_null=True)
    level = serializers.CharField()
    total_sessions = serializers.IntegerField()
    instructor_name = serializers.CharField(allow_null=True)


class LearnerMyCourseSerializer(serializers.Serializer):
    """Response shape for GET /learner/my-courses/."""
    enrollment_id = serializers.IntegerField()
    course = LearnerMyCourseCourseSerializer()
    status = serializers.CharField()
    progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    enrolled_at = serializers.DateTimeField()
    last_accessed_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
