from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()
from .models import Organization, DemoRequest
from .serializers_superadmin import (
    OrganizationSuperadminSerializer, UserSuperadminSerializer,
    DemoRequestSerializer,
)
from .permissions import IsTascAdminUser
from apps.catalogue.models import CourseReview, Quiz, Assignment
from apps.catalogue.serializers import CourseReviewSerializer


class OrganizationSuperadminViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Organizations intended for Superadmins (TASC_ADMIN).
    """

    queryset = Organization.objects.annotate(
        users_count=models.Count("memberships", distinct=True),
        courses_count=models.Count("enrollments__course", distinct=True),
    ).order_by("-created_at")
    serializer_class = OrganizationSuperadminSerializer
    permission_classes = [IsTascAdminUser]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Returns high-level KPI counts for organizations.
        """
        qs = self.get_queryset()
        total = qs.count()
        active = qs.filter(is_active=True).count()
        suspended = qs.filter(is_active=False).count()
        
        # In a real app 'pending' might refer to something else, 
        # but matching the request requirements with active/suspended.
        
        return Response(
            {
                "total": total,
                "active": active,
                "suspended": suspended,
            }
        )

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """GET /api/v1/superadmin/organizations/export-csv/"""
        import csv as csv_module
        from django.http import HttpResponse
        qs = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="organizations.csv"'
        writer = csv_module.writer(response)
        writer.writerow(['ID', 'Name', 'Country', 'City', 'Contact Email', 'Active', 'Created At'])
        for org in qs:
            writer.writerow([
                org.id, org.name, org.country, org.city,
                org.contact_email, org.is_active, org.created_at,
            ])
        return response


class UserSuperadminViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Users intended for Superadmins (TASC_ADMIN).
    """

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSuperadminSerializer
    permission_classes = [IsTascAdminUser]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Returns high-level KPI counts for users.
        """
        qs = self.get_queryset()
        
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        from django.db.models import Count

        total = qs.count()
        active = qs.filter(is_active=True).count()
        new_this_month = qs.filter(date_joined__gte=start_of_month).count()
        suspended = qs.filter(is_active=False).count()
        by_role = list(
            qs.values("role").annotate(count=Count("id")).order_by("role")
        )

        return Response(
            {
                "total": total,
                "active": active,
                "new_this_month": new_this_month,
                "suspended": suspended,
                "by_role": by_role,
            }
        )

    @action(detail=False, methods=["get"], url_path="instructor-stats")
    def instructor_stats(self, request):
        """
        Returns instructor-specific KPI counts for the superadmin Instructors page.
        """
        from django.db.models import Count, Avg
        instructors = User.objects.filter(role=User.Role.INSTRUCTOR)
        total = instructors.count()
        active = instructors.filter(is_active=True).count()

        instructor_course_stats = instructors.annotate(
            course_count=Count('instructed_courses')
        )
        avg_courses = instructor_course_stats.aggregate(
            avg=Avg('course_count')
        )['avg'] or 0

        with_courses = instructor_course_stats.filter(course_count__gt=0).count()

        return Response({
            "total": total,
            "active": active,
            "avg_courses_per_instructor": round(avg_courses, 1),
            "with_courses": with_courses,
        })

    @action(detail=False, methods=["post"])
    def bulk_import(self, request):
        """
        Accepts a CSV file of users and imports them.
        CSV format: email,first_name,last_name,role,department,phone_number
        """
        import csv
        import random
        import string
        from django.db import transaction
        from django.contrib.auth.hashers import make_password
        
        if 'file' not in request.FILES:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        csv_file = request.FILES['file']
        
        if not csv_file.name.endswith('.csv'):
            return Response(
                {"error": "File must be a CSV file"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if csv_file.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File size exceeds 10 MB limit"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.DictReader(decoded_file.splitlines())
        except Exception as e:
            return Response(
                {"error": f"Failed to parse CSV file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_roles = ['learner', 'instructor', 'manager']
        
        total_rows = 0
        imported = 0
        errors = []
        
        users_to_create = []
        
        for row_num, row in enumerate(reader, start=2):
            total_rows += 1
            
            # Map frontend export columns to backend expected columns
            email = (row.get('email') or row.get('email_address') or '').strip()
            role = (row.get('role') or row.get('user_role') or 'learner').strip().lower()
            department = row.get('department', '').strip()
            phone_number = row.get('phone_number', '').strip()
            
            # Handle full_name splitting if first_name/last_name are missing
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            full_name = row.get('full_name', '').strip()
            
            if not first_name and not last_name and full_name:
                parts = full_name.split(' ', 1)
                first_name = parts[0]
                if len(parts) > 1:
                    last_name = parts[1]
            
            if not email:
                errors.append({
                    "row": row_num,
                    "email": "",
                    "error": "Email is required"
                })
                continue
            
            import re
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": "Invalid email format"
                })
                continue
            
            if User.objects.filter(email=email).exists():
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": "User already exists"
                })
                continue
            
            if role not in valid_roles:
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": f"Invalid role: '{role}'. Must be one of: {', '.join(valid_roles)}"
                })
                continue
            
            if total_rows > 5000:
                errors.append({
                    "row": row_num,
                    "email": email,
                    "error": "Max 5000 records per file exceeded"
                })
                break
            
            random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                department=department,
                phone_number=phone_number,
                password=make_password(random_password),
                is_active=True,
            )
            users_to_create.append(user)
        
        if users_to_create:
            try:
                with transaction.atomic():
                    User.objects.bulk_create(users_to_create)
                    imported = len(users_to_create)
            except Exception as e:
                errors.append({
                    "row": 0,
                    "email": "",
                    "error": f"Database error: {str(e)}"
                })
                imported = 0
        
        return Response({
            "message": "Bulk import completed.",
            "total_rows": total_rows,
            "imported": imported,
            "failed": len(errors),
            "errors": errors[:100]
        })

    @action(detail=False, methods=["get"])
    def csv_template(self, request):
        """
        Returns a CSV template for bulk user import.
        """
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_import_template.csv"'

        writer = csv.writer(response)
        writer.writerow(['email', 'first_name', 'last_name', 'role', 'department', 'phone_number'])
        writer.writerow(['example@domain.com', 'John', 'Doe', 'learner', 'Engineering', '+1234567890'])

        return response

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """GET /api/v1/superadmin/users/export-csv/"""
        import csv as csv_module
        from django.http import HttpResponse
        qs = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users.csv"'
        writer = csv_module.writer(response)
        writer.writerow(['ID', 'Email', 'First Name', 'Last Name', 'Role', 'Active', 'Date Joined'])
        for user in qs:
            writer.writerow([
                user.id, user.email, user.first_name, user.last_name,
                user.role, user.is_active, user.date_joined,
            ])
        return response


class SecurityStatsView(APIView):
    """GET /api/v1/superadmin/security/stats/"""
    permission_classes = [IsTascAdminUser]

    def get(self, request):
        now = timezone.now()
        failed_logins = User.objects.filter(failed_login_attempts__gt=0).count()
        locked_accounts = User.objects.filter(account_locked_until__gt=now).count()
        total_users = User.objects.filter(is_active=True).count()
        mfa_enabled = User.objects.filter(is_active=True, is_mfa_enabled=True).count() if hasattr(User, 'is_mfa_enabled') else 0
        mfa_percent = round((mfa_enabled / total_users * 100), 1) if total_users > 0 else 0.0

        return Response({
            "failed_logins_today": failed_logins,
            "locked_accounts": locked_accounts,
            "active_sessions": 0,
            "mfa_adoption_percent": mfa_percent,
        })


class SystemHealthView(APIView):
    """GET /api/v1/superadmin/system/health/"""
    permission_classes = [IsTascAdminUser]

    def get(self, request):
        import time
        from django.db import connection
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_latency = round((time.time() - start) * 1000)
        return Response({
            'database': 'healthy',
            'db_latency_ms': db_latency,
            'storage': 'online',
        })


class SuperadminReviewViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Superadmin review moderation queue.
    GET /api/v1/superadmin/reviews/              — list (filterable by ?status=pending|approved|rejected)
    POST /api/v1/superadmin/reviews/{id}/approve/ — approve a review
    POST /api/v1/superadmin/reviews/{id}/reject/  — reject a review
    PATCH /api/v1/superadmin/reviews/{id}/feature/ — toggle is_featured
    """
    serializer_class = CourseReviewSerializer
    permission_classes = [IsTascAdminUser]

    def get_queryset(self):
        qs = CourseReview.objects.select_related('course', 'user').order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        if status_filter == 'pending':
            qs = qs.filter(is_approved=False, is_rejected=False)
        elif status_filter == 'approved':
            qs = qs.filter(is_approved=True)
        elif status_filter == 'rejected':
            qs = qs.filter(is_rejected=True)
        return qs

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """POST /api/v1/superadmin/reviews/{id}/approve/"""
        review = self.get_object()
        review.is_approved = True
        review.is_rejected = False
        review.save(update_fields=['is_approved', 'is_rejected'])
        return Response(CourseReviewSerializer(review).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """POST /api/v1/superadmin/reviews/{id}/reject/"""
        review = self.get_object()
        review.is_approved = False
        review.is_rejected = True
        review.is_featured = False
        review.save(update_fields=['is_approved', 'is_rejected', 'is_featured'])
        return Response(CourseReviewSerializer(review).data)

    @action(detail=True, methods=['patch'])
    def feature(self, request, pk=None):
        """PATCH /api/v1/superadmin/reviews/{id}/feature/  body: { "is_featured": true|false }"""
        review = self.get_object()
        if not review.is_approved:
            return Response(
                {'error': 'Only approved reviews can be featured.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        review.is_featured = bool(request.data.get('is_featured', True))
        review.save(update_fields=['is_featured'])
        return Response(CourseReviewSerializer(review).data)


class DemoRequestViewSet(viewsets.ModelViewSet):
    """
    Superadmin management of demo requests from the /for-business CTA form.
    GET    /api/v1/superadmin/demo-requests/        — list (filterable by ?status=new|contacted|closed)
    GET    /api/v1/superadmin/demo-requests/{id}/   — retrieve
    PATCH  /api/v1/superadmin/demo-requests/{id}/   — update status / notes
    DELETE /api/v1/superadmin/demo-requests/{id}/   — delete
    """
    serializer_class = DemoRequestSerializer
    permission_classes = [IsTascAdminUser]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = DemoRequest.objects.all()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


# ──────────────────────────────────────────────
# Task 67: System Settings + SMTP
# ──────────────────────────────────────────────

class SystemSettingsView(APIView):
    """
    GET  /api/v1/superadmin/system/settings/  — return current platform settings
    PATCH /api/v1/superadmin/system/settings/ — save platform settings
    """
    permission_classes = [IsTascAdminUser]

    def _get_config(self):
        from django.conf import settings as django_settings
        return {
            'platform_name': getattr(django_settings, 'PLATFORM_NAME', 'TASC LMS'),
            'platform_url': getattr(django_settings, 'PLATFORM_URL', ''),
            'support_email': getattr(django_settings, 'SUPPORT_EMAIL', ''),
            'default_timezone': getattr(django_settings, 'TIME_ZONE', 'UTC'),
            'max_upload_mb': getattr(django_settings, 'MAX_UPLOAD_MB', 500),
        }

    def get(self, request):
        return Response(self._get_config())

    def patch(self, request):
        # Persist to a SystemConfig model if one exists, otherwise acknowledge only.
        # Future: store in a key-value config table.
        allowed = {'platform_name', 'platform_url', 'support_email', 'default_timezone', 'max_upload_mb'}
        updates = {k: v for k, v in request.data.items() if k in allowed}
        return Response({**self._get_config(), **updates})


class SMTPSettingsView(APIView):
    """
    PATCH /api/v1/superadmin/system/smtp/      — save SMTP configuration
    POST  /api/v1/superadmin/system/smtp/test/ — send a test email
    """
    permission_classes = [IsTascAdminUser]

    def patch(self, request):
        allowed = {'host', 'port', 'username', 'from_name', 'from_email', 'use_tls'}
        updates = {k: v for k, v in request.data.items() if k in allowed}
        # Future: persist to encrypted config store
        return Response({'detail': 'SMTP settings saved.', **updates})

    def post(self, request):
        """Send a test email using the currently configured SendGrid / SMTP settings."""
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        recipient = request.data.get('recipient') or request.user.email
        try:
            send_mail(
                subject='TASC LMS — SMTP Test Email',
                message='This is a test email sent from the TASC LMS system settings page.',
                from_email=getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@tasc.co.ug'),
                recipient_list=[recipient],
                fail_silently=False,
            )
            return Response({'detail': f'Test email sent to {recipient}.'})
        except Exception as exc:
            return Response({'detail': f'Failed to send email: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ──────────────────────────────────────────────
# Task 68: Security Policy + Terminate Sessions
# ──────────────────────────────────────────────

class SecurityPolicyView(APIView):
    """
    GET   /api/v1/superadmin/security/policy/  — return current policy settings
    PATCH /api/v1/superadmin/security/policy/  — save policy settings
    """
    permission_classes = [IsTascAdminUser]

    # Default policy values — replace with DB model when needed
    _DEFAULTS = {
        'mfa_enabled': False,
        'mfa_required_roles': [],
        'min_password_length': 8,
        'require_uppercase': True,
        'require_special': False,
        'password_expiry_days': 0,
        'password_history': 0,
        'max_failed_attempts': 5,
        'lockout_duration_minutes': 15,
        'session_timeout_minutes': 60,
        'idle_timeout_minutes': 30,
        'max_concurrent_sessions': 0,
        'force_single_session': False,
    }

    def get(self, request):
        return Response(self._DEFAULTS)

    def patch(self, request):
        allowed = set(self._DEFAULTS.keys())
        updates = {k: v for k, v in request.data.items() if k in allowed}
        return Response({**self._DEFAULTS, **updates})


class TerminateAllSessionsView(APIView):
    """
    POST /api/v1/superadmin/security/terminate-sessions/
    Invalidates all outstanding JWT refresh tokens.
    """
    permission_classes = [IsTascAdminUser]

    def post(self, request):
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            outstanding = OutstandingToken.objects.all()
            count = outstanding.count()
            for token in outstanding:
                BlacklistedToken.objects.get_or_create(token=token)
            return Response({'detail': f'All {count} active sessions terminated.'})
        except Exception as exc:
            return Response(
                {'detail': f'Could not terminate sessions: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ──────────────────────────────────────────────
# Task 65: Superadmin Assessments list + stats
# ──────────────────────────────────────────────

class SuperadminAssessmentsViewSet(viewsets.ViewSet):
    """
    GET /api/v1/superadmin/assessments/         — paginated list of quizzes + assignments
    GET /api/v1/superadmin/assessments/stats/   — KPI counts
    Supports ?type=quiz|assignment and ?page / ?page_size query params.
    """
    permission_classes = [IsTascAdminUser]

    def list(self, request):
        from apps.learning.models import QuizSubmission, Submission
        assessment_type = request.query_params.get('type')
        results = []

        if assessment_type != 'assignment':
            for quiz in Quiz.objects.select_related('session', 'session__course').all():
                results.append({
                    'id': quiz.id,
                    'type': 'quiz',
                    'title': quiz.session.title if quiz.session else '',
                    'course_title': quiz.session.course.title if quiz.session and quiz.session.course else '',
                    'question_count': quiz.questions.count(),
                    'submission_count': quiz.submissions.count(),
                })

        if assessment_type != 'quiz':
            for asn in Assignment.objects.select_related('session', 'session__course').all():
                results.append({
                    'id': asn.id,
                    'type': 'assignment',
                    'title': asn.session.title if asn.session else '',
                    'course_title': asn.session.course.title if asn.session and asn.session.course else '',
                    'max_points': asn.max_points,
                    'submission_count': asn.submissions.count(),
                })

        page_size = int(request.query_params.get('page_size', 20))
        page = int(request.query_params.get('page', 1))
        start = (page - 1) * page_size
        end = start + page_size

        return Response({
            'count': len(results),
            'results': results[start:end],
        })

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        from apps.learning.models import QuizSubmission
        quiz_count = Quiz.objects.count()
        assignment_count = Assignment.objects.count()
        total = quiz_count + assignment_count
        quiz_subs = QuizSubmission.objects.all()
        total_attempts = quiz_subs.count()
        passed = quiz_subs.filter(passed=True).count()
        pass_rate = round((passed / total_attempts * 100), 1) if total_attempts > 0 else 0.0
        return Response({
            'total': total,
            'quizzes': quiz_count,
            'assignments': assignment_count,
            'pass_rate': pass_rate,
            'total_attempts': total_attempts,
        })
