from django.contrib import admin
from .models import Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'enrollment', 'assignment', 'status', 'grade', 'submitted_at', 'graded_at')
    list_filter = ('status',)
    search_fields = ('enrollment__user__email', 'assignment__session__title')
    raw_id_fields = ('enrollment', 'assignment', 'graded_by')
