from django.contrib import admin
from .models import LivestreamSession, LivestreamAttendance, LivestreamRecording, LivestreamQuestion

@admin.register(LivestreamSession)
class LivestreamSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'platform', 'status', 'start_time', 'created_at')
    list_filter = ('platform', 'status')
    search_fields = ('title', 'course__title')

@admin.register(LivestreamAttendance)
class LivestreamAttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'learner', 'status', 'joined_at')
    list_filter = ('status',)
    search_fields = ('learner__email', 'session__title')

@admin.register(LivestreamRecording)
class LivestreamRecordingAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'recording_type', 'is_published')
    list_filter = ('is_published', 'recording_type')

@admin.register(LivestreamQuestion)
class LivestreamQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'asked_by', 'is_answered', 'asked_at')
    list_filter = ('is_answered',)
    search_fields = ('question_text', 'asked_by__email')
