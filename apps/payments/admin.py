from django.contrib import admin
from .models import Subscription, UserSubscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "currency", "billing_cycle", "status")
    list_filter = ("status", "billing_cycle")


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "subscription", "status", "start_date", "end_date")
    list_filter = ("status",)
    raw_id_fields = ("user", "organization", "subscription")
