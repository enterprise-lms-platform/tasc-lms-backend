from django.contrib import admin

from .models import Assignment, BankQuestion, Category, Course, Module, QuestionCategory, Quiz, QuizQuestion, Session, Tag


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


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'assignment_type', 'max_points', 'due_date', 'updated_at')
    list_filter = ('assignment_type',)
    search_fields = ('instructions',)
    raw_id_fields = ('session',)
    ordering = ('-updated_at',)


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


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'parent', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    ordering = ('name',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'category', 'level', 'status', 'created_at')
    list_filter = ('status', 'level', 'category')
    search_fields = ('title', 'slug')
    raw_id_fields = ('category', 'instructor')
    ordering = ('-created_at',)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'course', 'session_type', 'status', 'order')
    list_filter = ('session_type', 'status')
    search_fields = ('title',)
    raw_id_fields = ('course', 'module')
    ordering = ('course', 'order')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'created_at')
    search_fields = ('name', 'slug')
    ordering = ('name',)
