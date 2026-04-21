"""
Celery configuration for TASC LMS.
"""
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("tasc_lms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "check-and-notify-expiring-subscriptions-daily": {
        "task": "apps.payments.tasks.check_and_notify_expiring_subscriptions",
        "schedule": crontab(hour=8, minute=0),
    },
    "expire-overdue-subscriptions-hourly": {
        "task": "apps.payments.tasks.expire_overdue_subscriptions",
        "schedule": crontab(minute=30),
    },
    "reconcile-stale-pesapal-payments": {
        "task": "apps.payments.tasks.reconcile_stale_pesapal_payments",
        "schedule": crontab(minute=15),
    },
}
