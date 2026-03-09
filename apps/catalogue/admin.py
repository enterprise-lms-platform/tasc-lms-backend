from django.contrib import admin

from .models import Module, Quiz, QuizQuestion


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'updated_at')
    raw_id_fields = ('session',)


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'quiz', 'order', 'question_type', 'question_text', 'points', 'updated_at')
    list_filter = ('question_type',)
    raw_id_fields = ('quiz',)
    ordering = ('quiz', 'order', 'id')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'course', 'order', 'status', 'created_at')
    list_filter = ('status', 'course')
    search_fields = ('title',)
    ordering = ('course', 'order')
