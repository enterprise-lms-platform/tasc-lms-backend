from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "action", "resource", "actor_email", "details", "ip_address", "created_at")
    list_filter = ("action", "resource")
    search_fields = ("actor_name", "actor_email", "details")
    readonly_fields = ("actor", "actor_name", "actor_email", "action", "resource", "resource_id", "details", "ip_address", "organization", "metadata", "created_at")
