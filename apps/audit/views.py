"""Views for audit log API."""

from datetime import datetime

from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog
from .permissions import AuditLogPermission
from .serializers import AuditLogListSerializer


class AuditLogPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema(
    tags=["Superadmin - Audit Logs"],
    summary="List audit logs",
    description="Read-only list of audit logs. Access controlled by role: tasc_admin/lms_manager see all; finance sees payment only; org_admin sees their org's logs.",
    parameters=[
        OpenApiParameter(name="search", type=str, description="Match actor_name or actor_email (icontains)"),
        OpenApiParameter(name="from", type=str, description="From date YYYY-MM-DD"),
        OpenApiParameter(name="to", type=str, description="To date YYYY-MM-DD"),
        OpenApiParameter(name="action", type=str, description="created, updated, deleted, login, logout, or All"),
        OpenApiParameter(name="resource", type=str, description="user, course, organization, payment, or All"),
        OpenApiParameter(name="page", type=int, description="Page number"),
        OpenApiParameter(name="page_size", type=int, description="Page size (default 20)"),
    ],
    responses={200: AuditLogListSerializer(many=True), 403: {"description": "Forbidden"}},
)
class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated, AuditLogPermission]
    pagination_class = AuditLogPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)

        if role in ("tasc_admin", "lms_manager"):
            return AuditLog.objects.all()

        if role == "finance":
            return AuditLog.objects.filter(resource=AuditLog.Resource.PAYMENT)

        if role == "org_admin":
            org_ids = user.memberships.values_list("organization_id", flat=True)
            return AuditLog.objects.filter(organization_id__in=org_ids)

        return AuditLog.objects.none()

    def get(self, request):
        queryset = self.get_queryset()

        # search: actor_name or actor_email icontains
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(actor_name__icontains=search) | Q(actor_email__icontains=search)
            )

        # from: created_at >= start of day
        from_date = request.query_params.get("from", "").strip()
        if from_date:
            try:
                dt = datetime.strptime(from_date, "%Y-%m-%d")
                start = timezone.make_aware(datetime.combine(dt.date(), datetime.min.time()))
                queryset = queryset.filter(created_at__gte=start)
            except ValueError:
                pass

        # to: created_at <= end of day
        to_date = request.query_params.get("to", "").strip()
        if to_date:
            try:
                dt = datetime.strptime(to_date, "%Y-%m-%d")
                end = timezone.make_aware(datetime.combine(dt.date(), datetime.max.time()))
                queryset = queryset.filter(created_at__lte=end)
            except ValueError:
                pass

        # action filter
        action_param = request.query_params.get("action", "all").strip().lower()
        if action_param and action_param != "all":
            valid_actions = ("login", "logout", "created", "updated", "deleted")
            if action_param in valid_actions:
                queryset = queryset.filter(action=action_param)

        # resource filter
        resource_param = request.query_params.get("resource", "all").strip().lower()
        if resource_param and resource_param != "all":
            valid_resources = ("user", "course", "organization", "payment")
            if resource_param in valid_resources:
                queryset = queryset.filter(resource=resource_param)

        queryset = queryset.order_by("-created_at")

        # pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = AuditLogListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = AuditLogListSerializer(queryset, many=True)
        return Response(serializer.data)
