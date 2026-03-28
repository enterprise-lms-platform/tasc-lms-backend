from django.urls import path

from .views import AuditLogListView, AuditLogSummaryView

urlpatterns = [
    path("audit-logs/", AuditLogListView.as_view(), name="audit-logs"),
    path("audit-logs/summary/", AuditLogSummaryView.as_view(), name="audit-logs-summary"),
]
