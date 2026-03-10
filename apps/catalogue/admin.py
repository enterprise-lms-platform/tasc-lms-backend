from django.contrib import admin

from .models import BankQuestion, Module, QuestionCategory, Quiz, QuizQuestion


@admin.register(QuestionCategory)
class QuestionCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'owner', 'order', 'created_at')
    list_filter = ('owner',)
    search_fields = ('name',)
    ordering = ('order', 'name', 'id')
    raw_id_fields = ('owner',)


@admin.register(BankQuestion)
class BankQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'question_type', 'question_text', 'owner', 'category', 'points', 'difficulty', 'created_at')
    list_filter = ('question_type', 'difficulty', 'owner')
    search_fields = ('question_text',)
    raw_id_fields = ('owner', 'category')
    ordering = ('-created_at',)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'updated_at')
    raw_id_fields = ('session',)


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'quiz', 'order', 'question_type', 'question_text', 'points', 'source_bank_question', 'updated_at')
    list_filter = ('question_type',)
    raw_id_fields = ('quiz', 'source_bank_question')
    ordering = ('quiz', 'order', 'id')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'course', 'order', 'status', 'created_at')
    list_filter = ('status', 'course')
    search_fields = ('title',)
    ordering = ('course', 'order')
