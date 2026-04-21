from django.contrib import admin
from .models import (
    Enrollment, SessionProgress, Certificate, Submission,
    QuizSubmission, QuizAnswer, Discussion, DiscussionReply,
    Badge, UserBadge, SavedCourse, Report,
)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'course', 'status', 'progress_percentage', 'enrolled_at')
    list_filter = ('status',)
    search_fields = ('user__email', 'course__title')
    raw_id_fields = ('user', 'course', 'last_accessed_session')


@admin.register(SessionProgress)
class SessionProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'enrollment', 'session', 'is_completed', 'time_spent_seconds')
    list_filter = ('is_completed',)
    raw_id_fields = ('enrollment', 'session')


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('id', 'certificate_number', 'enrollment', 'issued_at', 'is_valid')
    list_filter = ('is_valid',)
    search_fields = ('certificate_number', 'enrollment__user__email')
    raw_id_fields = ('enrollment',)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'enrollment', 'assignment', 'status', 'grade', 'submitted_at', 'graded_at')
    list_filter = ('status',)
    search_fields = ('enrollment__user__email', 'assignment__session__title')
    raw_id_fields = ('enrollment', 'assignment', 'graded_by')


@admin.register(QuizSubmission)
class QuizSubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'enrollment', 'quiz', 'score', 'passed', 'submitted_at')
    list_filter = ('passed',)
    raw_id_fields = ('enrollment', 'quiz')


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'course', 'title', 'is_pinned', 'created_at')
    list_filter = ('is_pinned', 'is_locked')
    search_fields = ('title', 'user__email')
    raw_id_fields = ('user', 'course', 'session')


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'category', 'criteria_type', 'criteria_value')
    list_filter = ('category', 'criteria_type')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'badge', 'earned_at')
    raw_id_fields = ('user', 'badge')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'report_type', 'status', 'generated_at')
    list_filter = ('report_type', 'status')
