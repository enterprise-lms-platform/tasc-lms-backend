from django.contrib import admin
from .models import Subscription, UserSubscription
from .models import PesapalIPN, Payment


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "currency", "billing_cycle", "status")
    list_filter = ("status", "billing_cycle")


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "subscription", "status", "start_date", "end_date")
    list_filter = ("status",)
    raw_id_fields = ("user", "organization", "subscription")

# Pesapal IPN Admin

@admin.register(PesapalIPN)
class PesapalIPNAdmin(admin.ModelAdmin):
    list_display = [
        "ipn_id",
        "environment_badge",
        "url",
        "notification_type",
        "is_active",
        "registered_at",
    ]
    list_filter = ["environment", "is_active"]
    search_fields = ["ipn_id", "url"]
    readonly_fields = ["ipn_id", "registered_at"]
    ordering = ["-registered_at"]
 
    fieldsets = (
        ("IPN Details", {
            "fields": ("ipn_id", "url", "notification_type", "environment", "is_active"),
        }),
        ("Meta", {
            "fields": ("registered_at", "notes"),
        }),
    )
 
    def environment_badge(self, obj):
        color = "#e74c3c" if obj.environment == "live" else "#f39c12"
        label = obj.environment.upper()
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color, label
        )
    environment_badge.short_description = "Environment"
 
    def has_add_permission(self, request):
        # IPNs should be registered via the API endpoint, not manually
        # Remove this method if you want to allow manual creation
        return False
 
 
# ─────────────────────────────────────────────────────────────────────────────
# Pesapal Payment filter on existing Payment admin
# ─────────────────────────────────────────────────────────────────────────────
# If you already have a PaymentAdmin registered, add this inline filter to it.
# If not, here's a minimal one scoped to Pesapal payments:
 
# class PesapalPaymentAdmin(admin.ModelAdmin):
#     """
#     Optional: register this instead of (or alongside) your existing PaymentAdmin
#     if you want a dedicated Pesapal payments view in admin.
 
#     To use alongside existing PaymentAdmin, add a Pesapal proxy model:
 
#         class PesapalPayment(Payment):
#             class Meta:
#                 proxy = True
#                 verbose_name = "Pesapal Payment"
#                 verbose_name_plural = "Pesapal Payments"
 
#     Then register: admin.site.register(PesapalPayment, PesapalPaymentAdmin)
#     """
 
#     list_display = [
#         "id",
#         "user",
#         "amount",
#         "currency",
#         "status",
#         "provider_order_id",
#         "provider_payment_id",
#         "created_at",
#         "completed_at",
#     ]
#     list_filter = ["status", "currency", "created_at"]
#     search_fields = [
#         "user__email",
#         "provider_order_id",
#         "provider_payment_id",
#         "id",
#     ]
#     readonly_fields = [
#         "id", "created_at", "updated_at", "completed_at",
#         "provider_order_id", "provider_payment_id", "metadata",
#     ]
#     ordering = ["-created_at"]
 
#     def get_queryset(self, request):
#         return super().get_queryset(request).filter(payment_method="pesapal")
 
#     fieldsets = (
#         ("Payment Info", {
#             "fields": ("id", "user", "course", "amount", "currency", "status", "description"),
#         }),
#         ("Pesapal References", {
#             "fields": ("provider_order_id", "provider_payment_id", "metadata"),
#         }),
#         ("Timestamps", {
#             "fields": ("created_at", "updated_at", "completed_at"),
#         }),
#     )
 