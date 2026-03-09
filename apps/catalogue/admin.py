from django.contrib import admin

from .models import Module


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'course', 'order', 'status', 'created_at')
    list_filter = ('status', 'course')
    search_fields = ('title',)
    ordering = ('course', 'order')
