from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .models import Membership
from .rbac import get_active_membership_organization
from .serializers import ManagerOrganizationSerializer, UserListSerializer
from apps.payments.models import UserSubscription
from apps.learning.models import Enrollment, Submission

User = get_user_model()

class ManagerOrganizationSettingsView(APIView):
    """
    View for Organization Managers to manage their organization's profile and settings.
    """
    permission_classes = [IsAuthenticated]

    def _get_organization(self, user):
        membership = user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER]
        ).first()
        if membership:
            return membership.organization
        return None

    @extend_schema(
        summary="Get organization settings",
        description="Returns the organization profile and settings for the current manager's organization.",
        responses={200: ManagerOrganizationSerializer}
    )
    def get(self, request):
        organization = self._get_organization(request.user)
        if not organization:
            return Response(
                {"detail": "No organization found or you do not have manager permissions."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = ManagerOrganizationSerializer(organization)
        return Response(serializer.data)

    @extend_schema(
        summary="Update organization settings",
        description="Updates the organization profile and settings for the current manager's organization.",
        request=ManagerOrganizationSerializer,
        responses={200: ManagerOrganizationSerializer}
    )
    def patch(self, request):
        organization = self._get_organization(request.user)
        if not organization:
            return Response(
                {"detail": "No organization found or you do not have manager permissions."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = ManagerOrganizationSerializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        summary="Update organization settings (PUT)",
        description="Updates the organization profile and settings for the current manager's organization.",
        request=ManagerOrganizationSerializer,
        responses={200: ManagerOrganizationSerializer}
    )
    def put(self, request):
        return self.patch(request)


class ManagerBillingPlanView(APIView):
    """
    Returns the active subscription plan for the manager's organization.
    GET /api/v1/auth/manager/billing/plan/
    """
    permission_classes = [IsAuthenticated]

    def _get_organization(self, user):
        membership = user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER],
            is_active=True,
        ).select_related('organization').first()
        return membership.organization if membership else None

    def get(self, request):
        org = self._get_organization(request.user)
        if not org:
            return Response(
                {'detail': 'No organization found or insufficient permissions.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        sub = UserSubscription.objects.filter(
            organization=org, status=UserSubscription.Status.ACTIVE
        ).select_related('subscription').first()

        if sub:
            return Response({
                'plan_name': sub.subscription.name,
                'price': str(sub.price),
                'currency': sub.currency,
                'billing_cycle': sub.subscription.billing_cycle,
                'renewal_date': sub.end_date,
                'user_limit': org.max_seats,
            })

        return Response({
            'plan_name': None,
            'price': '0',
            'currency': 'USD',
            'billing_cycle': None,
            'renewal_date': None,
            'user_limit': org.max_seats,
        })


class ManagerBillingUsageView(APIView):
    """
    Returns active user and course counts for the manager's organization.
    GET /api/v1/auth/manager/billing/usage/
    """
    permission_classes = [IsAuthenticated]

    def _get_organization(self, user):
        membership = user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER],
            is_active=True,
        ).select_related('organization').first()
        return membership.organization if membership else None

    def get(self, request):
        org = self._get_organization(request.user)
        if not org:
            return Response(
                {'detail': 'No organization found or insufficient permissions.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        active_users = Membership.objects.filter(
            organization=org, is_active=True
        ).count()

        active_courses = Enrollment.objects.filter(
            organization=org, status=Enrollment.Status.ACTIVE
        ).values('course').distinct().count()

        return Response({
            'active_users': active_users,
            'active_courses': active_courses,
        })


class ManagerActivityView(APIView):
    """
    Returns a recent activity feed for the manager's organization.
    GET /api/v1/auth/manager/activity/?range=7days
    range options: today | 7days | 30days  (default: 7days)
    """
    permission_classes = [IsAuthenticated]

    def _get_organization(self, user):
        membership = user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER],
            is_active=True,
        ).select_related('organization').first()
        return membership.organization if membership else None

    def get(self, request):
        org = self._get_organization(request.user)
        if not org:
            return Response(
                {'detail': 'No organization found or insufficient permissions.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        range_param = request.query_params.get('range', '7days')
        now = timezone.now()
        if range_param == 'today':
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif range_param == '30days':
            since = now - timedelta(days=30)
        else:  # default 7days
            since = now - timedelta(days=7)

        limit = 50

        # Recent enrollments in range
        enrollments = (
            Enrollment.objects
            .filter(organization=org, enrolled_at__gte=since)
            .select_related('user', 'course')
            .order_by('-enrolled_at')[:limit]
        )

        # Recent completions in range
        completions = (
            Enrollment.objects
            .filter(organization=org, status='completed', completed_at__gte=since)
            .select_related('user', 'course')
            .order_by('-completed_at')[:limit]
        )

        # Recent submissions in range
        submissions = (
            Submission.objects
            .filter(enrollment__organization=org, submitted_at__gte=since)
            .select_related('enrollment__user', 'assignment__session')
            .order_by('-submitted_at')[:limit]
        )

        def relative_time(dt):
            if not dt:
                return '—'
            diff = now - dt
            mins = int(diff.total_seconds() / 60)
            if mins < 2:
                return 'Just now'
            if mins < 60:
                return f'{mins} min ago'
            hours = mins // 60
            if hours < 24:
                return f'{hours} hour{"s" if hours > 1 else ""} ago'
            days = hours // 24
            return f'{days} day{"s" if days > 1 else ""} ago'

        def user_name(u):
            full = f'{u.first_name} {u.last_name}'.strip()
            return full or u.email

        events = []

        for e in enrollments:
            events.append({
                'type': 'Enrollment',
                'user_name': user_name(e.user),
                'description': f'enrolled in {e.course.title}',
                'timestamp': e.enrolled_at.isoformat(),
                'relative_time': relative_time(e.enrolled_at),
            })

        for c in completions:
            if c.completed_at:
                events.append({
                    'type': 'Completion',
                    'user_name': user_name(c.user),
                    'description': f'completed Course: {c.course.title}',
                    'timestamp': c.completed_at.isoformat(),
                    'relative_time': relative_time(c.completed_at),
                })

        for s in submissions:
            if s.submitted_at:
                try:
                    session_title = s.assignment.session.title
                except AttributeError:
                    session_title = 'an assignment'
                events.append({
                    'type': 'Submission',
                    'user_name': user_name(s.enrollment.user),
                    'description': f'submitted Assignment: {session_title}',
                    'timestamp': s.submitted_at.isoformat(),
                    'relative_time': relative_time(s.submitted_at),
                })

        # Sort merged list by timestamp descending, take top limit
        events.sort(key=lambda x: x['timestamp'], reverse=True)
        events = events[:limit]

        # Summary counts for the selected range
        summary = {
            'enrollments': Enrollment.objects.filter(
                organization=org, enrolled_at__gte=since
            ).count(),
            'completions': Enrollment.objects.filter(
                organization=org, status='completed', completed_at__gte=since
            ).count(),
            'submissions': Submission.objects.filter(
                enrollment__organization=org, submitted_at__gte=since
            ).count(),
        }

        return Response({'events': events, 'summary': summary})


class ManagerMembersView(APIView):
    """
    List users belonging to the requester's organization (via Membership).
    GET /api/v1/auth/manager/members/?search=&role=
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List organization members",
        description="Returns users linked to the requester's active organization via Membership.",
        parameters=[
            OpenApiParameter(name="search", description="Filter by email or name", type=str),
            OpenApiParameter(name="role", description="Filter by platform role", type=str),
        ],
        responses={200: UserListSerializer(many=True)},
    )
    def get(self, request):
        org = get_active_membership_organization(request.user)
        if not org:
            return Response(
                {"detail": "No organization found or insufficient permissions."},
                status=status.HTTP_404_NOT_FOUND,
            )

        users = (
            User.objects.filter(
                memberships__organization=org,
                memberships__is_active=True,
            )
            .distinct()
            .order_by("-date_joined")
        )

        role = request.query_params.get("role")
        if role:
            users = users.filter(role=role)

        search = request.query_params.get("search")
        if search:
            users = users.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        serializer = UserListSerializer(users, many=True)
        return Response(serializer.data)
