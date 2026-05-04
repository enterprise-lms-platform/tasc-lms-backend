from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiExample,
)
from rest_framework import viewsets, status, mixins, serializers
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.permissions import HasActiveSubscription
from apps.accounts.rbac import get_active_membership_organization

User = get_user_model()

_ENROLLMENT_ORDERING_WHITELIST = frozenset(
    (
        "enrolled_at",
        "-enrolled_at",
        "last_accessed_at",
        "-last_accessed_at",
        "progress_percentage",
        "-progress_percentage",
    )
)


class EnrollmentPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


class CertificatePageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


from .models import (
    Enrollment,
    SessionProgress,
    Certificate,
    Discussion,
    DiscussionReply,
    DiscussionReport,
    Report,
    Submission,
    QuizSubmission,
    QuizAnswer,
    SavedCourse,
    Workshop,
)


def _analytics_enrollment_scope_qs(user):
    """Enrollments visible for learning analytics (product scope)."""
    role = getattr(user, 'role', None) or ''
    if role == User.Role.INSTRUCTOR:
        return Enrollment.objects.filter(course__instructor=user)
    if role == User.Role.ORG_ADMIN:
        org = get_active_membership_organization(user)
        return Enrollment.objects.filter(organization=org) if org else Enrollment.objects.none()
    if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
        return Enrollment.objects.all()
    return Enrollment.objects.filter(user=user)


def _analytics_quiz_submission_scope_qs(user):
    """Quiz submissions visible for learning analytics; scope matches enrollments."""
    role = getattr(user, 'role', None) or ''
    if role == User.Role.INSTRUCTOR:
        return QuizSubmission.objects.filter(enrollment__course__instructor=user)
    if role == User.Role.ORG_ADMIN:
        org = get_active_membership_organization(user)
        return (
            QuizSubmission.objects.filter(enrollment__organization=org)
            if org
            else QuizSubmission.objects.none()
        )
    if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
        return QuizSubmission.objects.all()
    return QuizSubmission.objects.filter(enrollment__user=user)


from .serializers import (
    EnrollmentSerializer,
    EnrollmentCreateSerializer,
    BulkEnrollmentSerializer,
    SessionProgressSerializer,
    SessionProgressUpdateSerializer,
    CertificateSerializer,
    DiscussionSerializer,
    DiscussionCreateSerializer,
    DiscussionReplySerializer,
    DiscussionReplyCreateSerializer,
    ReportSerializer,
    ReportGenerateSerializer,
    SubmissionSerializer,
    SubmissionCreateSerializer,
    SubmissionUpdateSerializer,
    GradeSubmissionSerializer,
    QuizSubmissionSerializer,
    QuizSubmissionCreateSerializer,
    SavedCourseSerializer,
    WorkshopSerializer,
    WorkshopCreateUpdateSerializer,
)


@extend_schema(
    tags=["Learning - Enrollments"],
    description="Manage user course enrollments and progress",
)
class EnrollmentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for managing user enrollments. Supports list, create, retrieve, and generate_certificate only."""

    queryset = Enrollment.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = EnrollmentPageNumberPagination

    def get_serializer_class(self):
        if self.action == "create":
            return EnrollmentCreateSerializer
        return EnrollmentSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", "") or ""
        role_param = self.request.query_params.get("role", "").strip()

        related = (
            "course",
            "course__category",
            "course__instructor",
            "user",
            "organization",
        )

        # ?role=instructor → enrollments in courses this user teaches (never widens scope by client alone)
        if role_param == "instructor" and role in (
            User.Role.INSTRUCTOR,
            User.Role.TASC_ADMIN,
        ):
            qs = Enrollment.objects.filter(course__instructor=user).select_related(
                *related
            )
        elif role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            qs = Enrollment.objects.all().select_related(*related)
        elif role == User.Role.ORG_ADMIN:
            org = get_active_membership_organization(user)
            if org is None:
                qs = Enrollment.objects.none()
            else:
                qs = Enrollment.objects.filter(organization=org).select_related(
                    *related
                )
        else:
            # learner, finance, instructor (without instructor list mode), unknown → own enrollments only
            qs = Enrollment.objects.filter(user=user).select_related(*related)

        course_id = self.request.query_params.get("course")
        if course_id:
            qs = qs.filter(course_id=course_id)

        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(course__title__icontains=search)
            )

        status_val = self.request.query_params.get("status", "").strip()
        valid_statuses = {c[0] for c in Enrollment.Status.choices}
        if status_val and status_val in valid_statuses:
            qs = qs.filter(status=status_val)

        ordering_raw = self.request.query_params.get("ordering", "").strip()
        if ordering_raw in _ENROLLMENT_ORDERING_WHITELIST:
            qs = qs.order_by(ordering_raw)
        else:
            qs = qs.order_by("-enrolled_at")

        return qs

    @extend_schema(
        summary="List enrollments",
        description=(
            "Scope is determined by the authenticated user role only. "
            "Learners see their enrollments; instructors see theirs by default, or their students with ?role=instructor; "
            "org admins see enrollments for their active membership organization; "
            "LMS managers and TASC admins see all enrollments platform-wide."
        ),
        parameters=[
            OpenApiParameter(
                name="course", type=int, description="Filter by course id"
            ),
            OpenApiParameter(
                name="search",
                type=str,
                description="Search learner name/email or course title",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                description="Filter by enrollment status (active, completed, dropped, expired)",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                description="Whitelist: enrolled_at, -enrolled_at, last_accessed_at, -last_accessed_at, progress_percentage, -progress_percentage",
            ),
            OpenApiParameter(name="page", type=int),
            OpenApiParameter(name="page_size", type=int, description="Max 100"),
            OpenApiParameter(
                name="role",
                type=str,
                description="Use role=instructor (with instructor or tasc_admin account) to list students in courses you teach",
            ),
        ],
        responses={200: EnrollmentSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Enroll in a course",
        description="Enroll the authenticated user in a course. Idempotent: repeated POST returns 200 with existing enrollment.",
        request=EnrollmentCreateSerializer,
        responses={
            200: EnrollmentSerializer,
            201: EnrollmentSerializer,
            403: OpenApiResponse(description="Active subscription required"),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        response_serializer = EnrollmentSerializer(
            instance, context=self.get_serializer_context()
        )
        status_code = (
            status.HTTP_201_CREATED
            if getattr(serializer, "_created", True)
            else status.HTTP_200_OK
        )
        return Response(response_serializer.data, status=status_code)

    @extend_schema(
        summary="Generate certificate",
        description="Generate a completion certificate for this enrollment",
        responses={
            200: CertificateSerializer,
            400: OpenApiResponse(
                description="Course not completed or certificate already exists"
            ),
        },
    )
    @action(detail=True, methods=["post"])
    def generate_certificate(self, request, pk=None):
        enrollment = self.get_object()

        if enrollment.progress_percentage < 100:
            return Response(
                {"error": "Course must be completed to generate certificate"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        certificate, created = Certificate.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                "certificate_number": Certificate.generate_certificate_number(),
            },
        )

        if not created:
            return Response(
                {"error": "Certificate already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CertificateSerializer(certificate)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Bulk enroll users",
        description="Manager only. Enrolls multiple users from the manager's organization into a course.",
        request=BulkEnrollmentSerializer,
        responses={
            200: OpenApiResponse(description="Bulk enrollment results"),
            403: OpenApiResponse(description="Not an LMS manager"),
        },
    )
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        from apps.accounts.rbac import is_lms_manager
        from django.db import transaction
        from django.contrib.auth import get_user_model

        user = request.user
        role = getattr(user, "role", "")
        if not is_lms_manager(user) and role != "org_admin":
            return Response(
                {"error": "Only LMS Managers and Org Admins can bulk enroll users."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = BulkEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        course = serializer.validated_data["course"]
        user_ids = serializer.validated_data["user_ids"]

        User = get_user_model()
        valid_users = User.objects.filter(
            id__in=user_ids, organization=user.organization
        )
        valid_user_ids = set(valid_users.values_list("id", flat=True))

        existing_enrollments = set(
            Enrollment.objects.filter(
                course=course, user_id__in=valid_user_ids
            ).values_list("user_id", flat=True)
        )

        new_user_ids = valid_user_ids - existing_enrollments

        enrollments_to_create = [
            Enrollment(
                user_id=uid,
                course=course,
                organization=user.organization,
                paid_amount=0,
                currency="USD",
            )
            for uid in new_user_ids
        ]

        if enrollments_to_create:
            with transaction.atomic():
                Enrollment.objects.bulk_create(
                    enrollments_to_create, ignore_conflicts=True
                )

        failed = len(user_ids) - len(valid_user_ids)

        return Response(
            {
                "enrolled": len(new_user_ids),
                "already_enrolled": len(existing_enrollments),
                "failed": failed,
                "errors": [
                    "Some users were not found or do not belong to your organization."
                ]
                if failed > 0
                else [],
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Learning - Session Progress"],
    description="Track user progress through individual course sessions",
)
class SessionProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for managing session progress."""

    queryset = SessionProgress.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]

    def get_serializer_class(self):
        if self.action in ["update", "partial_update"]:
            return SessionProgressUpdateSerializer
        return SessionProgressSerializer

    def get_queryset(self):
        qs = SessionProgress.objects.filter(enrollment__user=self.request.user)

        enrollment_id = self.request.query_params.get("enrollment")
        if enrollment_id:
            qs = qs.filter(enrollment_id=enrollment_id)

        session_id = self.request.query_params.get("session")
        if session_id:
            qs = qs.filter(session_id=session_id)

        course_id = self.request.query_params.get("course")
        if course_id:
            qs = qs.filter(enrollment__course_id=course_id)

        return qs

    def _sync_enrollment_rollup(self, instance: SessionProgress) -> None:
        """Keep enrollment progress and resume fields aligned after SessionProgress writes."""
        enrollment = instance.enrollment
        enrollment.last_accessed_session = instance.session
        enrollment.update_progress()

    def perform_create(self, serializer):
        instance = serializer.save()
        self._sync_enrollment_rollup(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._sync_enrollment_rollup(instance)

    @extend_schema(
        summary="List session progress",
        description="Returns progress for all sessions across user enrollments",
        parameters=[
            OpenApiParameter(
                name="enrollment", type=int, description="Filter by enrollment ID"
            ),
            OpenApiParameter(
                name="session", type=int, description="Filter by session ID"
            ),
            OpenApiParameter(
                name="course", type=int, description="Filter by course ID"
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Mark session as completed",
        description="Mark a session as completed and update progress",
        request=SessionProgressUpdateSerializer,
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


@extend_schema(
    tags=["Learning - Certificates"],
    description="Manage course completion certificates",
)
class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing certificates."""

    queryset = Certificate.objects.all()
    serializer_class = CertificateSerializer
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    pagination_class = CertificatePageNumberPagination

    _CERT_STATS_ROLES = frozenset(
        (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN, User.Role.ORG_ADMIN),
    )

    def get_permissions(self):
        if self.action == "verify":
            return [AllowAny()]
        return super().get_permissions()

    def _certificate_scope_queryset(self, user):
        """Role-scoped base queryset (no list search/course filters). Used for list/retrieve/latest/stats."""
        role = getattr(user, "role", "") or ""
        related = (
            "enrollment",
            "enrollment__user",
            "enrollment__course",
            "enrollment__organization",
        )
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return Certificate.objects.all().select_related(*related)
        if role == User.Role.ORG_ADMIN:
            org = get_active_membership_organization(user)
            if org is None:
                return Certificate.objects.none()
            return Certificate.objects.filter(
                enrollment__organization=org
            ).select_related(*related)
        # learner, instructor, finance, and other roles: own enrollments only
        return Certificate.objects.filter(enrollment__user=user).select_related(
            *related
        )

    def get_queryset(self):
        qs = self._certificate_scope_queryset(self.request.user)
        if getattr(self, "action", None) != "list":
            return qs.order_by("-issued_at")

        course_id = self.request.query_params.get("course")
        if course_id:
            try:
                qs = qs.filter(enrollment__course_id=int(course_id))
            except (TypeError, ValueError):
                pass

        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(enrollment__user__first_name__icontains=search)
                | Q(enrollment__user__last_name__icontains=search)
                | Q(enrollment__user__email__icontains=search)
                | Q(enrollment__course__title__icontains=search)
                | Q(certificate_number__icontains=search)
            )

        return qs.order_by("-issued_at")

    @extend_schema(
        summary="List certificates",
        description=(
            "Returns certificates visible to the authenticated user: learners see their own; "
            "org admins see certificates for enrollments in their active organization; "
            "LMS managers and TASC admins see all certificates platform-wide."
        ),
        parameters=[
            OpenApiParameter(
                name="course",
                type=int,
                description="Filter by course id (enrollment course)",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                description="Search learner name, email, course title, or certificate number",
            ),
            OpenApiParameter(name="page", type=int),
            OpenApiParameter(name="page_size", type=int, description="Max 100"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Get certificate details",
        description="Returns detailed certificate information",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Get latest certificate",
        description="Returns the most recently issued certificate for the authenticated user",
        responses={
            200: CertificateSerializer,
            404: OpenApiResponse(description="No certificates found"),
        },
    )
    @action(detail=False, methods=["get"])
    def latest(self, request):
        certificate = self.get_queryset().order_by("-issued_at").first()
        if not certificate:
            return Response(
                {"detail": "No certificates found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(certificate)
        return Response(serializer.data)

    @extend_schema(
        summary="Verify certificate",
        description="Verify a certificate by its number",
        responses={
            200: CertificateSerializer,
            404: OpenApiResponse(description="Certificate not found"),
        },
    )
    @action(detail=False, methods=["get"])
    def verify(self, request):
        certificate_number = request.query_params.get("number")

        if not certificate_number:
            return Response(
                {"error": "Certificate number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            certificate = Certificate.objects.get(certificate_number=certificate_number)
            serializer = self.get_serializer(certificate)
            return Response(serializer.data)
        except Certificate.DoesNotExist:
            return Response(
                {"error": "Certificate not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(
        summary="Regenerate certificate",
        description=(
            "Invalidate the existing certificate for an enrollment and create a new one. "
            "Only the enrollment owner (or admin/instructor) may regenerate."
        ),
        responses={201: CertificateSerializer, 403: OpenApiResponse(description="Forbidden"), 404: OpenApiResponse(description="Not found")},
    )
    @action(detail=True, methods=["post"], url_path="regenerate")
    def regenerate(self, request, pk=None):
        certificate = self.get_object()
        enrollment = certificate.enrollment
        user = request.user

        is_owner = enrollment.user_id == user.id
        is_admin = hasattr(user, "role") and user.role in [
            "tasc_admin", "lms_manager", "instructor",
        ]
        if not is_owner and not is_admin:
            return Response(
                {"detail": "You do not have permission to regenerate this certificate."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not certificate.is_valid:
            return Response(
                {"detail": "Certificate is already invalidated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        certificate.is_valid = False
        certificate.save(update_fields=["is_valid"])

        new_cert = Certificate.objects.create(
            enrollment=enrollment,
            expiry_date=timezone.now() + __import__("datetime").timedelta(days=365),
        )
        from django.conf import settings as _settings
        new_cert.verification_url = (
            f"{_settings.FRONTEND_URL}/verify-certificate?number={new_cert.certificate_number}"
        )
        new_cert.save(update_fields=["verification_url"])

        serializer = self.get_serializer(new_cert)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Certificate statistics",
        description=(
            "Returns aggregate certificate stats over the same role scope as list "
            "(org admins: their organization only; LMS manager / TASC admin: platform-wide). "
            "Learners and other roles receive 403."
        ),
        responses={
            200: OpenApiResponse(description="Scoped totals"),
            403: OpenApiResponse(description="Not permitted for this role"),
        },
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Certificate statistics over the same role scope as list (no search/course filters)."""
        role = getattr(request.user, "role", "") or ""
        if role not in self._CERT_STATS_ROLES:
            return Response(
                {
                    "detail": "You do not have permission to access certificate statistics."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        all_certs = self._certificate_scope_queryset(request.user)
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total = all_certs.count()
        this_month = all_certs.filter(issued_at__gte=start_of_month).count()
        total_courses = all_certs.values("enrollment__course").distinct().count()
        valid = all_certs.filter(is_valid=True).count()

        return Response(
            {
                "total": total,
                "this_month": this_month,
                "total_courses_with_certs": total_courses,
                "valid": valid,
            }
        )

    @extend_schema(
        summary="Request certificate for enrollment",
        description="Learner requests a certificate for a completed enrollment. Creates a PENDING certificate awaiting approval.",
        request=None,
        responses={201: CertificateSerializer, 400: OpenApiResponse(description="Bad request")},
    )
    @action(detail=False, methods=["post"], url_path="request")
    def request_certificate(self, request):
        enrollment_id = request.data.get("enrollment")
        if not enrollment_id:
            return Response({"error": "enrollment ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            enrollment = Enrollment.objects.get(pk=enrollment_id, user=request.user)
        except Enrollment.DoesNotExist:
            return Response({"error": "Enrollment not found"}, status=status.HTTP_404_NOT_FOUND)
        if enrollment.progress_percentage < 100:
            return Response({"error": "Course must be completed to request a certificate"}, status=status.HTTP_400_BAD_REQUEST)
        existing = Certificate.objects.filter(enrollment=enrollment).first()
        if existing and existing.status in [Certificate.Status.APPROVED, Certificate.Status.PENDING]:
            return Response({"error": "Certificate already exists for this enrollment"}, status=status.HTTP_400_BAD_REQUEST)
        if existing and existing.status == Certificate.Status.DENIED:
            return Response({"error": "Certificate was denied. Use resubmit instead."}, status=status.HTTP_400_BAD_REQUEST)
        cert = Certificate.objects.create(
            enrollment=enrollment,
            status=Certificate.Status.PENDING,
        )
        from django.conf import settings as _settings
        cert.verification_url = f"{_settings.FRONTEND_URL}/verify-certificate?number={cert.certificate_number}"
        cert.save(update_fields=["verification_url"])
        serializer = self.get_serializer(cert)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Deny a pending certificate",
        description="Admin/manager denies a pending certificate request with a reason.",
        request=None,
        responses={200: CertificateSerializer, 400: OpenApiResponse(description="Bad request"), 403: OpenApiResponse(description="Forbidden")},
    )
    @action(detail=True, methods=["post"], url_path="deny")
    def deny(self, request, pk=None):
        certificate = self.get_object()
        if not (hasattr(request.user, "role") and request.user.role in ["tasc_admin", "lms_manager", "instructor"]):
            return Response({"detail": "Only admins or instructors can deny certificates."}, status=status.HTTP_403_FORBIDDEN)
        if certificate.status != Certificate.Status.PENDING:
            return Response({"error": "Only pending certificates can be denied."}, status=status.HTTP_400_BAD_REQUEST)
        reason = request.data.get("reason", "")
        certificate.status = Certificate.Status.DENIED
        certificate.denial_reason = reason
        certificate.save(update_fields=["status", "denial_reason"])
        serializer = self.get_serializer(certificate)
        return Response(serializer.data)

    @extend_schema(
        summary="Resubmit a denied certificate",
        description="Learner resubmits a denied certificate for re-review.",
        request=None,
        responses={200: CertificateSerializer, 400: OpenApiResponse(description="Bad request")},
    )
    @action(detail=True, methods=["post"], url_path="resubmit")
    def resubmit(self, request, pk=None):
        certificate = self.get_object()
        if certificate.enrollment.user_id != request.user.id:
            return Response({"detail": "You can only resubmit your own certificates."}, status=status.HTTP_403_FORBIDDEN)
        if certificate.status != Certificate.Status.DENIED:
            return Response({"error": "Only denied certificates can be resubmitted."}, status=status.HTTP_400_BAD_REQUEST)
        certificate.status = Certificate.Status.PENDING
        certificate.denial_reason = ""
        certificate.save(update_fields=["status", "denial_reason"])
        serializer = self.get_serializer(certificate)
        return Response(serializer.data)


@extend_schema(
    tags=["Learning - Discussions"],
    description="Manage discussion threads for courses and sessions",
)
class DiscussionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing discussions."""

    queryset = Discussion.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]

    def get_serializer_class(self):
        if self.action == "create":
            return DiscussionCreateSerializer
        return DiscussionSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", "")
        qs = Discussion.objects.select_related("user", "course", "session")

        # Scope to accessible courses only
        if role not in ("tasc_admin", "lms_manager", "org_admin"):
            if role == "instructor":
                from apps.catalogue.models import Course as CatalogCourse
                qs = qs.filter(course__instructor=user)
            else:
                enrolled_course_ids = Enrollment.objects.filter(
                    user=user, status__in=["active", "completed"]
                ).values_list("course_id", flat=True)
                qs = qs.filter(course_id__in=enrolled_course_ids)

        course_id = self.request.query_params.get("course")
        if course_id:
            qs = qs.filter(course_id=course_id)

        session_id = self.request.query_params.get("session")
        if session_id:
            qs = qs.filter(session_id=session_id)

        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))

        return qs

    @extend_schema(
        summary="List discussions",
        description="Returns all discussions",
        parameters=[
            OpenApiParameter(
                name="course", type=int, description="Filter by course ID"
            ),
            OpenApiParameter(
                name="session", type=int, description="Filter by session ID"
            ),
            OpenApiParameter(
                name="search", type=str, description="Search in title and content"
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Create discussion",
        description="Create a new discussion thread",
        request=DiscussionCreateSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Get discussion details",
        description="Returns discussion with all replies",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Pin/unpin discussion",
        description="Toggle pin status (Instructor/Manager only)",
        responses={
            200: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {"is_pinned": {"type": "boolean"}},
                }
            )
        },
    )
    @action(detail=True, methods=["post"])
    def pin(self, request, pk=None):
        """Pin or unpin a discussion thread."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if getattr(request.user, "role", None) not in (
            User.Role.INSTRUCTOR,
            User.Role.LMS_MANAGER,
            User.Role.TASC_ADMIN,
        ):
            return Response(
                {"detail": "Only instructors and admins can pin discussions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        discussion = self.get_object()
        discussion.is_pinned = not discussion.is_pinned
        discussion.save()
        return Response({"is_pinned": discussion.is_pinned})

    @extend_schema(
        summary="Lock/unlock discussion",
        description="Toggle lock status (Instructor/Manager only). When locked, no new replies are allowed.",
        responses={
            200: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {"is_locked": {"type": "boolean"}},
                }
            )
        },
    )
    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        """Lock or unlock a discussion thread."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if getattr(request.user, "role", None) not in (
            User.Role.INSTRUCTOR,
            User.Role.LMS_MANAGER,
            User.Role.TASC_ADMIN,
        ):
            return Response(
                {"detail": "Only instructors and admins can lock discussions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        discussion = self.get_object()
        discussion.is_locked = not discussion.is_locked
        discussion.save()
        return Response({"is_locked": discussion.is_locked})

    @extend_schema(summary="Report discussion", description="Report a discussion as abusive, spam, etc.")
    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        discussion = self.get_object()
        reason = request.data.get("reason", "other")
        detail = request.data.get("detail", "")
        _, created = DiscussionReport.objects.get_or_create(
            reporter=request.user, discussion=discussion,
            defaults={"reason": reason, "detail": detail},
        )
        if not created:
            return Response({"detail": "You have already reported this discussion."}, status=status.HTTP_400_BAD_REQUEST)
        discussion.report_count = discussion.reports.filter(is_resolved=False).count()
        # Auto-hide after 3 reports
        if discussion.report_count >= 3:
            discussion.is_hidden = True
        discussion.save(update_fields=["report_count", "is_hidden"])
        return Response({"detail": "Report submitted. A moderator will review it."})

    @extend_schema(summary="Moderate discussion", description="Delete or restore a discussion (Instructor/Manager/Admin only)")
    @action(detail=True, methods=["post"])
    def moderate(self, request, pk=None):
        role = getattr(request.user, "role", "")
        if role not in ("instructor", "lms_manager", "tasc_admin", "org_admin"):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        discussion = self.get_object()
        action_type = request.data.get("action")  # 'delete' | 'restore' | 'dismiss_reports'
        if action_type == "delete":
            discussion.is_deleted = True
            discussion.is_hidden = True
            DiscussionReport.objects.filter(discussion=discussion).update(is_resolved=True)
        elif action_type == "restore":
            discussion.is_deleted = False
            discussion.is_hidden = False
            discussion.report_count = 0
            DiscussionReport.objects.filter(discussion=discussion).update(is_resolved=True)
        elif action_type == "dismiss_reports":
            discussion.is_hidden = False
            discussion.report_count = 0
            DiscussionReport.objects.filter(discussion=discussion).update(is_resolved=True)
        else:
            return Response({"detail": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)
        discussion.save()
        return Response({"detail": f"Discussion {action_type}d."})


@extend_schema(
    tags=["Learning - Discussion Replies"],
    description="Manage replies to discussion threads",
)
class DiscussionReplyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing discussion replies."""

    queryset = DiscussionReply.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]

    def get_serializer_class(self):
        if self.action == "create":
            return DiscussionReplyCreateSerializer
        return DiscussionReplySerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", "")
        qs = DiscussionReply.objects.select_related("user", "discussion__course")

        if role not in ("tasc_admin", "lms_manager", "org_admin"):
            if role == "instructor":
                qs = qs.filter(discussion__course__instructor=user)
            else:
                enrolled_course_ids = Enrollment.objects.filter(
                    user=user, status__in=["active", "completed"]
                ).values_list("course_id", flat=True)
                qs = qs.filter(discussion__course_id__in=enrolled_course_ids)

        discussion_id = self.request.query_params.get("discussion")
        if discussion_id:
            qs = qs.filter(discussion_id=discussion_id)

        return qs

    @extend_schema(
        summary="List replies",
        description="Returns all replies for discussions",
        parameters=[
            OpenApiParameter(
                name="discussion", type=int, description="Filter by discussion ID"
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Create reply",
        description="Create a new reply to a discussion",
        request=DiscussionReplyCreateSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(summary="Report reply", description="Report a reply as abusive, spam, etc.")
    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        reply = self.get_object()
        reason = request.data.get("reason", "other")
        detail = request.data.get("detail", "")
        _, created = DiscussionReport.objects.get_or_create(
            reporter=request.user, reply=reply,
            defaults={"reason": reason, "detail": detail},
        )
        if not created:
            return Response({"detail": "You have already reported this reply."}, status=status.HTTP_400_BAD_REQUEST)
        reply.report_count = reply.reports.filter(is_resolved=False).count()
        if reply.report_count >= 3:
            reply.is_hidden = True
        reply.save(update_fields=["report_count", "is_hidden"])
        return Response({"detail": "Report submitted. A moderator will review it."})

    @extend_schema(summary="Moderate reply", description="Delete or restore a reply (Instructor/Manager/Admin only)")
    @action(detail=True, methods=["post"])
    def moderate(self, request, pk=None):
        role = getattr(request.user, "role", "")
        if role not in ("instructor", "lms_manager", "tasc_admin", "org_admin"):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        reply = self.get_object()
        action_type = request.data.get("action")
        if action_type == "delete":
            reply.is_deleted = True
            reply.is_hidden = True
            DiscussionReport.objects.filter(reply=reply).update(is_resolved=True)
        elif action_type == "restore":
            reply.is_deleted = False
            reply.is_hidden = False
            reply.report_count = 0
            DiscussionReport.objects.filter(reply=reply).update(is_resolved=True)
        elif action_type == "dismiss_reports":
            reply.is_hidden = False
            reply.report_count = 0
            DiscussionReport.objects.filter(reply=reply).update(is_resolved=True)
        else:
            return Response({"detail": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)
        reply.save()
        return Response({"detail": f"Reply {action_type}d."})


@extend_schema(tags=["Learning - Discussions"], summary="Moderation queue")
class DiscussionModerationQueueView(APIView):
    """Returns flagged discussions and replies for moderator review."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = getattr(request.user, "role", "")
        if role not in ("instructor", "lms_manager", "tasc_admin", "org_admin"):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only instructors and managers can view the moderation queue.")

        discussions_qs = Discussion.objects.filter(report_count__gt=0, is_deleted=False)
        replies_qs = DiscussionReply.objects.filter(report_count__gt=0, is_deleted=False)

        if role == "instructor":
            discussions_qs = discussions_qs.filter(course__instructor=request.user)
            replies_qs = replies_qs.filter(discussion__course__instructor=request.user)
        elif role == "org_admin":
            org = get_active_membership_organization(request.user)
            if org:
                discussions_qs = discussions_qs.filter(course__organization=org)
                replies_qs = replies_qs.filter(discussion__course__organization=org)

        discussions = [
            {
                "id": d.id, "type": "discussion", "title": d.title, "content": d.content,
                "author": d.user.email, "report_count": d.report_count, "is_hidden": d.is_hidden,
                "course_id": d.course_id, "created_at": d.created_at,
                "reasons": list(d.reports.filter(is_resolved=False).values_list("reason", flat=True)),
            }
            for d in discussions_qs.select_related("user", "course").order_by("-report_count")[:50]
        ]
        replies = [
            {
                "id": r.id, "type": "reply", "content": r.content,
                "author": r.user.email, "report_count": r.report_count, "is_hidden": r.is_hidden,
                "discussion_id": r.discussion_id, "created_at": r.created_at,
                "reasons": list(r.reports.filter(is_resolved=False).values_list("reason", flat=True)),
            }
            for r in replies_qs.select_related("user", "discussion").order_by("-report_count")[:50]
        ]
        return Response({"discussions": discussions, "replies": replies, "total": len(discussions) + len(replies)})


# REPORTS


@extend_schema_view(
    list=extend_schema(
        summary="List reports",
        description="Returns list of generated reports",
    ),
    retrieve=extend_schema(
        summary="Get report",
        description="Returns report details by ID",
    ),
    create=extend_schema(
        summary="Generate report",
        description="Generate a new report",
    ),
)
@extend_schema(
    tags=["Learning - Reports"],
    description="Generate and manage organization reports",
)
class ReportViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """
    ViewSet for managing organization reports.
    Supports listing reports, generating new reports, and downloading reports.
    """

    queryset = Report.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return ReportGenerateSerializer
        return ReportSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", "")
        if role in ("tasc_admin", "lms_manager"):
            return Report.objects.all()
        if role == "org_admin":
            from apps.accounts.rbac import get_active_membership_organization
            org = get_active_membership_organization(user)
            if org:
                return Report.objects.filter(generated_by__memberships__organization=org).distinct()
        return Report.objects.filter(generated_by=user)

    @extend_schema(
        summary="List report types",
        description="Returns available report types",
    )
    @action(detail=False, methods=["get"])
    def types(self, request):
        """Get available report types — finance types shown for finance role"""
        role = getattr(request.user, "role", "")
        if role in ("finance", "tasc_admin"):
            return Response([
                {"id": "transactions", "name": "All Transactions", "description": "Complete transaction ledger — amounts, statuses, payment methods, dates"},
                {"id": "invoices", "name": "All Invoices", "description": "Invoice records with totals, due dates, payment status, and org"},
                {"id": "subscriptions", "name": "Subscription List", "description": "Active and historical subscriptions — plan, price, start/end dates, status"},
                {"id": "revenue", "name": "Revenue Report", "description": "Revenue breakdown by period, payment method, and plan"},
                {"id": "churn", "name": "Churn Report", "description": "Cancelled subscriptions — dates, plans, and duration"},
            ])
        return Response([
            {"id": "user_activity", "name": "User Activity Report", "description": "User login patterns, session durations, platform engagement"},
            {"id": "course_performance", "name": "Course Performance Report", "description": "Course completion rates, learner satisfaction scores"},
            {"id": "enrollment", "name": "Enrollment Summary", "description": "Enrollment trends, new registrations, drop-off rates"},
            {"id": "completion", "name": "Completion Analytics", "description": "Course and module completion, time-to-complete"},
            {"id": "assessment", "name": "Assessment Results", "description": "Quiz and assignment scores, pass/fail distributions"},
            {"id": "revenue", "name": "Revenue Report", "description": "Financial summary, subscription income, revenue per learner"},
        ])

    @extend_schema(
        summary="Generate report",
        description="Generate a new report",
        request=ReportGenerateSerializer,
    )
    def create(self, request, *args, **kwargs):
        """Generate a new report"""
        from .tasks import generate_report
        from rest_framework.exceptions import PermissionDenied

        role = getattr(request.user, "role", "")
        if role not in ("tasc_admin", "lms_manager", "org_admin", "instructor"):
            raise PermissionDenied("You do not have permission to generate reports.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report_type = serializer.validated_data["report_type"]

        report = Report.objects.create(
            report_type=report_type,
            name=f"{report_type.replace('_', ' ').title()} - {timezone.now().strftime('%Y-%m-%d')}",
            generated_by=request.user,
            status=Report.Status.PROCESSING,
            parameters=serializer.validated_data.get("parameters", {}),
        )

        generate_report.delay(report.id)

        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Download report",
        description="Download a generated report file",
    )
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Download report file"""
        report = self.get_object()

        if report.status != Report.Status.READY or not report.file:
            return Response(
                {"error": "Report is not ready for download"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Return file URL or redirect
        return Response(
            {
                "download_url": report.file.url if report.file else None,
                "file_size": report.file_size,
            }
        )


# SUBMISSIONS (GRADES)


@extend_schema_view(
    list=extend_schema(
        summary="List submissions",
        description="Returns list of learner submissions",
    ),
    retrieve=extend_schema(
        summary="Get submission",
        description="Returns submission details by ID",
    ),
    create=extend_schema(
        summary="Create submission",
        description="Create a new submission",
    ),
    update=extend_schema(
        summary="Update submission",
        description="Update a submission",
    ),
    partial_update=extend_schema(
        summary="Partial update submission",
        description="Partially update a submission",
    ),
    destroy=extend_schema(
        summary="Delete submission",
        description="Delete a submission",
    ),
)
@extend_schema(
    tags=["Learning - Submissions"],
    description="Manage learner submissions and grading",
)
class SubmissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing learner submissions and grades.
    """

    queryset = Submission.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]

    def get_serializer_class(self):
        if self.action == "create":
            return SubmissionCreateSerializer
        if self.action in ("update", "partial_update"):
            return SubmissionUpdateSerializer
        return SubmissionSerializer

    def get_queryset(self):
        # Filter by user for learners, all for instructors/managers
        user = self.request.user
        base_qs = Submission.objects.select_related(
            "enrollment",
            "enrollment__user",
            "assignment",
            "assignment__session",
            "graded_by",
        )
        if user.role == "org_admin":
            org = get_active_membership_organization(user)
            if not org:
                return base_qs.none()
            return base_qs.filter(enrollment__organization=org)
        if user.role in ["instructor", "lms_manager", "tasc_admin"]:
            return base_qs
        return base_qs.filter(enrollment__user=user)

    @extend_schema(
        summary="Grade submission",
        description="Grade a learner submission",
        request=GradeSubmissionSerializer,
    )
    @action(detail=True, methods=["post"])
    def grade(self, request, pk=None):
        """Grade a submission (instructor/admin only)"""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if getattr(request.user, "role", None) not in (
            User.Role.INSTRUCTOR,
            User.Role.LMS_MANAGER,
            User.Role.TASC_ADMIN,
        ):
            return Response(
                {"detail": "Only instructors and admins can grade submissions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        submission = self.get_object()
        serializer = GradeSubmissionSerializer(
            data=request.data, context={"submission": submission}
        )
        serializer.is_valid(raise_exception=True)

        submission.grade = serializer.validated_data["grade"]
        submission.feedback = serializer.validated_data.get("feedback", "")
        submission.internal_notes = serializer.validated_data.get("internal_notes", "")
        submission.status = Submission.Status.GRADED
        submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save()

        return Response(SubmissionSerializer(submission).data)

    @extend_schema(
        summary="Grade statistics",
        description="Get grade distribution and statistics for a course",
    )
    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """Get grade distribution for a course"""
        from django.contrib.auth import get_user_model
        from django.db.models import Avg, Count, Q

        User = get_user_model()

        course_id = request.query_params.get("course")
        if not course_id:
            return Response(
                {"course": "Course ID is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        submissions = Submission.objects.filter(
            assignment__session__course_id=course_id,
            status=Submission.Status.GRADED,
            grade__isnull=False,
        )
        if getattr(request.user, "role", None) == "org_admin":
            org = get_active_membership_organization(request.user)
            if org:
                submissions = submissions.filter(enrollment__organization=org)
            else:
                submissions = submissions.none()

        total = submissions.count()
        graded = submissions.exclude(grade__isnull=True).count()
        pending = total - graded

        avg_grade = submissions.aggregate(Avg("grade"))["grade__avg"] or 0

        distribution = [
            {
                "range": "90-100",
                "label": "A",
                "count": submissions.filter(grade__gte=90).count(),
            },
            {
                "range": "80-89",
                "label": "B",
                "count": submissions.filter(grade__gte=80, grade__lt=90).count(),
            },
            {
                "range": "70-79",
                "label": "C",
                "count": submissions.filter(grade__gte=70, grade__lt=80).count(),
            },
            {
                "range": "60-69",
                "label": "D",
                "count": submissions.filter(grade__gte=60, grade__lt=70).count(),
            },
            {
                "range": "0-59",
                "label": "F",
                "count": submissions.filter(grade__lt=60).count(),
            },
        ]

        for d in distribution:
            d["percentage"] = round((d["count"] / total * 100), 1) if total > 0 else 0

        return Response(
            {
                "total_submissions": total,
                "graded": graded,
                "pending": pending,
                "average_grade": round(avg_grade, 1),
                "distribution": distribution,
            }
        )

    @extend_schema(
        summary="Assessment statistics (superadmin)",
        description="Returns aggregate assessment stats: quizzes, assignments, grading status",
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Aggregate assignment + quiz stats for privileged roles only."""
        from django.db.models import Avg

        user = request.user
        role = getattr(user, 'role', None)
        allowed = (
            User.Role.ORG_ADMIN,
            User.Role.LMS_MANAGER,
            User.Role.TASC_ADMIN,
            User.Role.INSTRUCTOR,
        )
        if role not in allowed:
            return Response(
                {'detail': 'You do not have permission to access assessment statistics.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if role == User.Role.ORG_ADMIN and not get_active_membership_organization(user):
            return Response(
                {'detail': 'You do not have permission to access assessment statistics.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        submissions_qs = Submission.objects.all()
        quiz_qs = QuizSubmission.objects.all()
        if role == User.Role.ORG_ADMIN:
            org = get_active_membership_organization(user)
            submissions_qs = submissions_qs.filter(enrollment__organization=org)
            quiz_qs = quiz_qs.filter(enrollment__organization=org)
        # instructor, lms_manager, tasc_admin: platform-wide (matches submission list visibility)

        total_assignments = submissions_qs.count()
        graded = submissions_qs.filter(status=Submission.Status.GRADED).count()
        pending = submissions_qs.filter(status=Submission.Status.SUBMITTED).count()
        avg_grade = (
            submissions_qs.filter(
                status=Submission.Status.GRADED, grade__isnull=False
            ).aggregate(avg=Avg("grade"))["avg"]
            or 0
        )

        total_quizzes = quiz_qs.count()
        avg_quiz_score = quiz_qs.aggregate(avg=Avg("score"))["avg"] or 0
        quiz_pass_rate = 0
        if total_quizzes > 0:
            passed = quiz_qs.filter(passed=True).count()
            quiz_pass_rate = round((passed / total_quizzes) * 100, 1)

        return Response(
            {
                "total_assignments": total_assignments,
                "graded": graded,
                "pending": pending,
                "average_grade": round(avg_grade, 1),
                "total_quizzes": total_quizzes,
                "average_quiz_score": round(avg_quiz_score, 1),
                "quiz_pass_rate": quiz_pass_rate,
            }
        )

    @extend_schema(
        summary="Bulk grade submissions",
        description="Grade multiple submissions at once",
        request=serializers.Serializer,
    )
    @action(detail=False, methods=["post"])
    def bulk_grade(self, request):
        """Bulk grade submissions (instructor/admin only)"""
        from django.contrib.auth import get_user_model

        User = get_user_model()

        grades_data = request.data.get("grades", [])
        if not grades_data:
            return Response(
                {"grades": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        graded_count = 0

        for grade_item in grades_data:
            submission_id = grade_item.get("submission_id")
            grade = grade_item.get("grade")
            feedback = grade_item.get("feedback", "")

            if not submission_id or grade is None:
                results.append(
                    {
                        "submission_id": submission_id,
                        "status": "error",
                        "error": "submission_id and grade are required",
                    }
                )
                continue

            try:
                submission = Submission.objects.get(id=submission_id)
            except Submission.DoesNotExist:
                results.append(
                    {
                        "submission_id": submission_id,
                        "status": "error",
                        "error": "Submission not found",
                    }
                )
                continue

            if submission.status != Submission.Status.SUBMITTED:
                results.append(
                    {
                        "submission_id": submission_id,
                        "status": "error",
                        "error": "Only submitted submissions can be graded",
                    }
                )
                continue

            submission.grade = grade
            submission.feedback = feedback
            submission.status = Submission.Status.GRADED
            submission.graded_at = timezone.now()
            submission.graded_by = request.user
            submission.save()

            results.append({"submission_id": submission_id, "status": "success"})
            graded_count += 1

        return Response({"graded": graded_count, "results": results})


@extend_schema(
    tags=["Learning - Quiz Submissions"],
    description="Manage quiz submissions and grading",
)
class QuizSubmissionViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for quiz submissions.
    - POST: Submit quiz answers (auto-grades)
    - GET: List submissions (filtered by user/enrollment/quiz)
    - GET /{id}: Retrieve single submission with answers
    """

    queryset = QuizSubmission.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]

    def get_serializer_class(self):
        if self.action == "create":
            return QuizSubmissionCreateSerializer
        return QuizSubmissionSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = QuizSubmission.objects.select_related(
            "enrollment__user", "quiz__session"
        ).prefetch_related("answers")

        quiz_id = self.request.query_params.get("quiz")
        if quiz_id:
            try:
                queryset = queryset.filter(quiz_id=int(quiz_id))
            except (TypeError, ValueError):
                pass

        enrollment_id = self.request.query_params.get("enrollment")
        if enrollment_id:
            try:
                queryset = queryset.filter(enrollment_id=int(enrollment_id))
            except (TypeError, ValueError):
                pass

        if user.role == "org_admin":
            org = get_active_membership_organization(user)
            if not org:
                return queryset.none()
            return queryset.filter(enrollment__organization=org)
        if user.role in ["instructor", "lms_manager", "tasc_admin"]:
            return queryset

        return queryset.filter(enrollment__user=user)

    @action(detail=False, methods=["post"])
    def start(self, request):
        """Record server-side start time for a quiz attempt. Call before beginning the quiz."""
        from django.core.cache import cache
        enrollment_id = request.data.get("enrollment")
        quiz_id = request.data.get("quiz")
        if not enrollment_id or not quiz_id:
            return Response({"error": "enrollment and quiz are required."}, status=status.HTTP_400_BAD_REQUEST)
        key = f"quiz_start:{enrollment_id}:{quiz_id}:{request.user.id}"
        cache.set(key, timezone.now().isoformat(), timeout=7200)  # 2 hour max
        return Response({"started_at": cache.get(key)})

    def create(self, request, *args, **kwargs):
        serializer = QuizSubmissionCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        return Response(
            QuizSubmissionSerializer(submission).data, status=status.HTTP_201_CREATED
        )


from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncMonth
from datetime import timedelta


@extend_schema(tags=["Learning - Analytics"])
class LearningAnalyticsViewSet(viewsets.ViewSet):
    """ViewSet for dashboard analytics regarding enrollments and completion."""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="enrollment-trends")
    def enrollment_trends(self, request):
        months = int(request.query_params.get("months", 6))
        start_date = timezone.now() - timedelta(days=months * 30)

        user = request.user
        base_qs = _analytics_enrollment_scope_qs(user).filter(enrolled_at__gte=start_date)

        # Enrolls by month
        enrolls = (
            base_qs.annotate(month=TruncMonth("enrolled_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Completions by month
        comps = (
            base_qs.filter(status="completed")
            .annotate(month=TruncMonth("completed_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Build consistent month list
        labels_map = {}
        for i in range(months - 1, -1, -1):
            d = timezone.now() - timedelta(days=i * 30)
            label = d.strftime("%b %Y")
            labels_map[label] = {"enrollments": 0, "completions": 0}

        for e in enrolls:
            if e["month"]:
                key = e["month"].strftime("%b %Y")
                if key in labels_map:
                    labels_map[key]["enrollments"] = e["count"]
        for c in comps:
            if c["month"]:
                key = c["month"].strftime("%b %Y")
                if key in labels_map:
                    labels_map[key]["completions"] = c["count"]

        labels = list(labels_map.keys())
        enrollments = [labels_map[l]["enrollments"] for l in labels]
        completions = [labels_map[l]["completions"] for l in labels]

        return Response(
            {"labels": labels, "enrollments": enrollments, "completions": completions}
        )

    @action(detail=False, methods=["get"], url_path="learning-stats")
    def learning_stats(self, request):
        user = request.user
        base_qs = _analytics_enrollment_scope_qs(user)

        thirty_days_ago = timezone.now() - timedelta(days=30)
        active_learners = (
            base_qs.filter(last_accessed_at__gte=thirty_days_ago)
            .values("user")
            .distinct()
            .count()
        )

        avg_completion = base_qs.aggregate(avg=Avg("progress_percentage"))["avg"] or 0.0

        in_progress = base_qs.filter(status=Enrollment.Status.ACTIVE).count()
        completed = base_qs.filter(status="completed").count()

        quiz_qs = _analytics_quiz_submission_scope_qs(user)

        avg_quiz = quiz_qs.aggregate(avg=Avg('score'))['avg'] or 0.0

        avg_quiz = quiz_qs.aggregate(avg=Avg("score"))["avg"] or 0.0

        return Response(
            {
                "total_learners": total_learners,
                "active_learners": active_learners,
                "avg_completion_rate": round(avg_completion, 1),
                "total_courses_in_progress": in_progress,
                "total_completed_courses": completed,
                "avg_quiz_score": round(avg_quiz, 1),
            }
        )

    @action(detail=False, methods=["get"], url_path="top-course-performance")
    def top_course_performance(self, request):
        """Per-course enrollment and completion aggregates for analytics dashboards."""
        from rest_framework.exceptions import PermissionDenied

        user = request.user
        role = getattr(user, 'role', None) or ''
        if role == User.Role.ORG_ADMIN:
            org = get_active_membership_organization(user)
            if not org:
                raise PermissionDenied('You do not have permission to access this resource.')
            base_qs = Enrollment.objects.filter(organization=org)
        elif role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            base_qs = Enrollment.objects.all()
        elif role == User.Role.INSTRUCTOR:
            base_qs = Enrollment.objects.filter(course__instructor=user)
        elif user.role == "lms_manager":
            from apps.accounts.models import get_active_membership_organization
            org = get_active_membership_organization(user)
            if org:
                base_qs = Enrollment.objects.filter(organization=org)
            else:
                base_qs = Enrollment.objects.none()
        else:
            raise PermissionDenied(
                "You do not have permission to access this resource."
            )

        try:
            limit = int(request.query_params.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 50))

        rows = (
            base_qs.values("course_id", "course__title")
            .annotate(
                enrollments=Count("id"),
                completed=Count("id", filter=Q(status="completed")),
            )
            .order_by("-enrollments")[:limit]
        )

        data = []
        for row in rows:
            enr = row["enrollments"]
            comp = row["completed"]
            rate = round(100 * comp / enr) if enr else 0
            data.append(
        {
            "course_id": row["course_id"],
            "course_title": row["course__title"] or "",
            "enrollments": enr,
            "completed": comp,
            "completion_rate": rate,
        }
        )
        return Response(data)

    @extend_schema(
        summary="At-risk learners",
        description="Get learners at risk (low progress or inactive) for intervention",
    )
    @action(detail=False, methods=["get"], url_path="at-risk-learners")
    def at_risk_learners(self, request):
        """Get list of at-risk learners for LMS Manager to intervene."""
        user = request.user
        
        if user.role not in ["lms_manager", "tasc_admin", "instructor"]:
            return Response(
                {"error": "Unauthorized"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Base queryset
        base_qs = Enrollment.objects.filter(status=Enrollment.Status.ACTIVE)
        
        if user.role == "instructor":
            base_qs = base_qs.filter(course__instructor=user)
        elif user.role == "lms_manager":
            from apps.accounts.models import get_active_membership_organization
            org = get_active_membership_organization(user)
            if org:
                base_qs = base_qs.filter(organization=org)
            else:
                base_qs = base_qs.none()
        
        # At-risk criteria: progress < 30% OR no activity in 14 days
        fourteen_days_ago = timezone.now() - timedelta(days=14)

        at_risk = base_qs.filter(
            Q(progress_percentage__lt=30) |
            Q(last_accessed_at__lt=fourteen_days_ago)
        ).select_related('user', 'course').order_by('last_accessed_at')[:50]
        
        results = []
        for e in at_risk:
            days_inactive = None
            if e.last_accessed_at:
                days_inactive = (timezone.now() - e.last_accessed_at).days
            
            results.append({
                "id": e.id,
                "user_id": e.user.id,
                "user_name": f"{e.user.first_name} {e.user.last_name}".strip() or e.user.email,
                "user_email": e.user.email,
                "course_id": e.course.id,
                "course_title": e.course.title,
                "progress_percentage": float(e.progress_percentage) if e.progress_percentage else 0,
                "last_accessed_at": e.last_accessed_at,
                "days_inactive": days_inactive,
                "risk_level": "high" if (e.progress_percentage or 0) < 10 or (days_inactive and days_inactive > 21) else "medium",
            })
        
        return Response({
            "count": len(results),
            "results": results,
        })


# ═══════════════════════════════════════════════════════════════════════════
# BADGES
# ═══════════════════════════════════════════════════════════════════════════
# BADGES
# ═══════════════════════════════════════════════════════════════════════════


@extend_schema(
    tags=["Learning - Badges"],
    description="Badge definitions and user badge tracking",
)
class BadgeViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    """
    ViewSet for badges.
    - GET  /badges/         → list all badge definitions
    - GET  /badges/my-badges/ → current user's earned badges
    - POST /badges/check/   → trigger badge evaluation, return newly earned
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from apps.learning.badge_serializers import UserBadgeSerializer, BadgeSerializer

        if self.action == "my_badges":
            return UserBadgeSerializer
        return BadgeSerializer

    def get_queryset(self):
        from apps.learning.models import Badge

        return Badge.objects.all()

    @extend_schema(
        summary="List all badge definitions",
        description="Returns all available badges with their criteria.",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Get current user earned badges",
        description="Returns badges earned by the currently authenticated user.",
    )
    @action(detail=False, methods=["get"], url_path="my-badges")
    def my_badges(self, request):
        from apps.learning.models import UserBadge
        from apps.learning.badge_serializers import UserBadgeSerializer

        qs = UserBadge.objects.filter(user=request.user).select_related("badge")
        serializer = UserBadgeSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Check and award badges",
        description="Triggers badge evaluation for the current user. Returns any newly earned badges.",
    )
    @action(detail=False, methods=["post"], url_path="check")
    def check_badges(self, request):
        from apps.learning.badge_engine import check_and_award_badges
        from apps.learning.badge_serializers import UserBadgeSerializer

        newly_earned = check_and_award_badges(request.user)
        serializer = UserBadgeSerializer(newly_earned, many=True)
        return Response({"newly_earned": serializer.data})


# ═══════════════════════════════════════════════════════════════════════════
# SAVED COURSES
# ═══════════════════════════════════════════════════════════════════════════


@extend_schema(
    tags=["Learning - Saved Courses"],
    description="Manage user's bookmarked/saved courses",
)
class SavedCourseViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for managing saved/bookmarked courses."""

    serializer_class = SavedCourseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedCourse.objects.filter(user=self.request.user).select_related(
            "course", "course__instructor", "course__category"
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        summary="List saved courses",
        description="Returns all courses saved/bookmarked by the authenticated user",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Save a course",
        description='Bookmark a course. Send { "course": <id> }.',
        responses={201: SavedCourseSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Unsave a course",
        description="Remove a course from bookmarks by saved-course ID",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Toggle save/unsave a course",
        description='If the course is saved, unsave it. If not saved, save it. Returns { "saved": bool }.',
        request={
            "application/json": {
                "type": "object",
                "properties": {"course": {"type": "integer"}},
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "saved": {"type": "boolean"},
                    "id": {"type": "integer", "nullable": True},
                },
            }
        },
    )
    @action(detail=False, methods=["post"])
    def toggle(self, request):
        course_id = request.data.get("course")
        if not course_id:
            return Response(
                {"error": "course field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            saved = SavedCourse.objects.get(user=request.user, course_id=course_id)
            saved.delete()
            return Response({"saved": False, "id": None})
        except SavedCourse.DoesNotExist:
            from apps.catalogue.models import Course as CatCourse

            try:
                course = CatCourse.objects.get(id=course_id)
            except CatCourse.DoesNotExist:
                return Response(
                    {"error": "Course not found"}, status=status.HTTP_404_NOT_FOUND
                )
            saved = SavedCourse.objects.create(user=request.user, course=course)
            return Response(
                {"saved": True, "id": saved.id}, status=status.HTTP_201_CREATED
            )


@extend_schema(
    tags=["Learning - Workshops"],
    description="Manage in-person training workshops",
)
class WorkshopViewSet(viewsets.ModelViewSet):
    """
    CRUD for Workshops (in-person training events).
    - Instructors see only their own workshops.
    - TASC admins / LMS managers see all workshops.
    - No subscription required (workshops are offline events).
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return WorkshopCreateUpdateSerializer
        return WorkshopSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Workshop.objects.select_related("instructor")
        role = getattr(user, "role", "")
        if role in ("tasc_admin", "lms_manager"):
            pass  # see all
        else:
            qs = qs.filter(instructor=user)

        # Optional filters
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        search = self.request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q

            qs = qs.filter(
                Q(title__icontains=search)
                | Q(location__icontains=search)
                | Q(category__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        role = getattr(user, "role", "")
        if role not in ("instructor", "lms_manager", "tasc_admin"):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only instructors can create workshops.")
        serializer.save(instructor=user)

    @extend_schema(
        summary="List workshops",
        description="Returns workshops for the current instructor (or all for admins)",
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                description="Filter: upcoming | ongoing | completed",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                description="Search by title, location, or category",
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Create workshop", request=WorkshopCreateUpdateSerializer)
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(summary="Get workshop detail")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(summary="Update workshop", request=WorkshopCreateUpdateSerializer)
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary="Partial update workshop", request=WorkshopCreateUpdateSerializer
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(summary="Delete workshop")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


# Workshop Attendance ViewSet
from .serializers import (
    WorkshopAttendanceSerializer,
    WorkshopAttendanceCreateUpdateSerializer,
)
from .models import WorkshopAttendance


@extend_schema(
    tags=["Learning - Workshop Attendance"],
    description="Track attendance for workshops",
)
class WorkshopAttendanceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing workshop attendance."""

    permission_classes = [IsAuthenticated]
    serializer_class = WorkshopAttendanceSerializer

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return WorkshopAttendanceCreateUpdateSerializer
        return WorkshopAttendanceSerializer

    def get_queryset(self):
        user = self.request.user
        qs = WorkshopAttendance.objects.select_related("workshop", "user")
        role = getattr(user, "role", "")

        # Filter by workshop if provided
        workshop_id = self.request.query_params.get("workshop")
        if workshop_id:
            qs = qs.filter(workshop_id=workshop_id)

        # Filter by user if provided
        user_id = self.request.query_params.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        # TASC admins / LMS managers see all, instructors see their workshops
        if role in ("tasc_admin", "lms_manager"):
            pass
        else:
            qs = qs.filter(workshop__instructor=user)

        return qs

def perform_create(self, serializer):
    serializer.save()


class WorkshopParticipantSearchView(APIView):
    """Search users to add as workshop participants."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from rest_framework.exceptions import PermissionDenied
        role = getattr(request.user, "role", "")
        if role not in ("instructor", "lms_manager", "tasc_admin", "org_admin"):
            raise PermissionDenied("Only instructors and managers can search participants.")

        search = request.query_params.get('search', '').strip()
        workshop_id = request.query_params.get('workshop')

        if not search or len(search) < 2:
            return Response({'results': []})

        from django.contrib.auth import get_user_model
        User = get_user_model()

        qs = User.objects.filter(
            models.Q(email__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(last_name__icontains=search)
        ).filter(is_active=True)

        # Scope lms_manager and org_admin to their own org's users
        if role in ("lms_manager", "org_admin"):
            org = getattr(request.user, "organization", None)
            if org:
                qs = qs.filter(memberships__organization=org, memberships__is_active=True)

        qs = qs.distinct()[:20]
        
        results = [
            {
                'id': u.id,
                'email': u.email,
                'name': f"{u.first_name} {u.last_name}".strip() or u.email,
                'initials': f"{(u.first_name or '')[0]}{(u.last_name or '')[0]}".upper(),
            }
            for u in qs
        ]
        return Response({'results': results})
