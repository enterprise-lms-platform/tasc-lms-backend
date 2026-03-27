from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework import viewsets, status, mixins, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from apps.payments.permissions import HasActiveSubscription

from .models import (
    Enrollment, SessionProgress, Certificate, Discussion, DiscussionReply, Report, Submission,
    QuizSubmission, QuizAnswer, SavedCourse
)
from .serializers import (
    EnrollmentSerializer, EnrollmentCreateSerializer, BulkEnrollmentSerializer,
    SessionProgressSerializer, SessionProgressUpdateSerializer,
    CertificateSerializer,
    DiscussionSerializer, DiscussionCreateSerializer,
    DiscussionReplySerializer, DiscussionReplyCreateSerializer,
    ReportSerializer, ReportGenerateSerializer,
    SubmissionSerializer, SubmissionCreateSerializer,
    SubmissionUpdateSerializer, GradeSubmissionSerializer,
    QuizSubmissionSerializer, QuizSubmissionCreateSerializer,
    SavedCourseSerializer,
)


@extend_schema(
    tags=['Learning - Enrollments'],
    description='Manage user course enrollments and progress',
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

    def get_serializer_class(self):
        if self.action == 'create':
            return EnrollmentCreateSerializer
        return EnrollmentSerializer

    def get_queryset(self):
        user = self.request.user
        role_param = self.request.query_params.get('role', '').strip()

        # ?role=instructor → show enrollments in courses I teach (my students)
        if role_param == 'instructor' and user.role in ('instructor', 'tasc_admin'):
            qs = Enrollment.objects.filter(
                course__instructor=user
            ).select_related('course', 'course__category')
        else:
            # Default: show my own enrollments as a learner
            qs = Enrollment.objects.filter(user=user)

        # Optional course filter
        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(course_id=course_id)

        # Search by learner name or email, or course title
        search = self.request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(course__title__icontains=search)
            )

        return qs

    @extend_schema(
        summary='List my enrollments',
        description='Returns list of courses the authenticated user is enrolled in (instructors see their students)',
        responses={200: EnrollmentSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Enroll in a course',
        description='Enroll the authenticated user in a course. Idempotent: repeated POST returns 200 with existing enrollment.',
        request=EnrollmentCreateSerializer,
        responses={
            200: EnrollmentSerializer,
            201: EnrollmentSerializer,
            403: OpenApiResponse(description='Active subscription required'),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        response_serializer = EnrollmentSerializer(instance, context=self.get_serializer_context())
        status_code = status.HTTP_201_CREATED if getattr(serializer, '_created', True) else status.HTTP_200_OK
        return Response(response_serializer.data, status=status_code)
    
    @extend_schema(
        summary='Generate certificate',
        description='Generate a completion certificate for this enrollment',
        responses={
            200: CertificateSerializer,
            400: OpenApiResponse(description='Course not completed or certificate already exists'),
        },
    )
    @action(detail=True, methods=['post'])
    def generate_certificate(self, request, pk=None):
        enrollment = self.get_object()
        
        if enrollment.progress_percentage < 100:
            return Response(
                {'error': 'Course must be completed to generate certificate'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        certificate, created = Certificate.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                'certificate_number': Certificate.generate_certificate_number(),
            }
        )
        
        if not created:
            return Response(
                {'error': 'Certificate already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = CertificateSerializer(certificate)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Bulk enroll users',
        description='Manager only. Enrolls multiple users from the manager\'s organization into a course.',
        request=BulkEnrollmentSerializer,
        responses={
            200: OpenApiResponse(description='Bulk enrollment results'),
            403: OpenApiResponse(description='Not an LMS manager'),
        },
    )
    @action(detail=False, methods=['post'])
    def bulk(self, request):
        from apps.accounts.rbac import is_lms_manager
        from django.db import transaction
        from django.contrib.auth import get_user_model
        
        user = request.user
        if not is_lms_manager(user):
            return Response({'error': 'Only LMS Managers can bulk enroll users.'}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = BulkEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        course = serializer.validated_data['course']
        user_ids = serializer.validated_data['user_ids']
        
        User = get_user_model()
        valid_users = User.objects.filter(id__in=user_ids, organization=user.organization)
        valid_user_ids = set(valid_users.values_list('id', flat=True))
        
        existing_enrollments = set(Enrollment.objects.filter(
            course=course, 
            user_id__in=valid_user_ids
        ).values_list('user_id', flat=True))
        
        new_user_ids = valid_user_ids - existing_enrollments
        
        enrollments_to_create = [
            Enrollment(
                user_id=uid,
                course=course,
                organization=user.organization,
                paid_amount=0,
                currency='USD'
            )
            for uid in new_user_ids
        ]
        
        if enrollments_to_create:
            with transaction.atomic():
                Enrollment.objects.bulk_create(enrollments_to_create, ignore_conflicts=True)
                
        failed = len(user_ids) - len(valid_user_ids)
        
        return Response({
            'enrolled': len(new_user_ids),
            'already_enrolled': len(existing_enrollments),
            'failed': failed,
            'errors': ['Some users were not found or do not belong to your organization.'] if failed > 0 else []
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Learning - Session Progress'],
    description='Track user progress through individual course sessions',
)
class SessionProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for managing session progress."""
    queryset = SessionProgress.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return SessionProgressUpdateSerializer
        return SessionProgressSerializer
    
    def get_queryset(self):
        qs = SessionProgress.objects.filter(enrollment__user=self.request.user)

        enrollment_id = self.request.query_params.get('enrollment')
        if enrollment_id:
            qs = qs.filter(enrollment_id=enrollment_id)

        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)

        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(enrollment__course_id=course_id)

        return qs

    @extend_schema(
        summary='List session progress',
        description='Returns progress for all sessions across user enrollments',
        parameters=[
            OpenApiParameter(name='enrollment', type=int, description='Filter by enrollment ID'),
            OpenApiParameter(name='session', type=int, description='Filter by session ID'),
            OpenApiParameter(name='course', type=int, description='Filter by course ID'),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Mark session as completed',
        description='Mark a session as completed and update progress',
        request=SessionProgressUpdateSerializer,
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


@extend_schema(
    tags=['Learning - Certificates'],
    description='Manage course completion certificates',
)
class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing certificates."""
    queryset = Certificate.objects.all()
    serializer_class = CertificateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action == 'verify':
            return [AllowAny()]
        return super().get_permissions()
    
    def get_queryset(self):
        return Certificate.objects.filter(enrollment__user=self.request.user)
    
    @extend_schema(
        summary='List my certificates',
        description='Returns all certificates earned by the authenticated user',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get certificate details',
        description='Returns detailed certificate information',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
        
    @extend_schema(
        summary='Get latest certificate',
        description='Returns the most recently issued certificate for the authenticated user',
        responses={
            200: CertificateSerializer,
            404: OpenApiResponse(description='No certificates found'),
        },
    )
    @action(detail=False, methods=['get'])
    def latest(self, request):
        certificate = self.get_queryset().order_by('-issued_at').first()
        if not certificate:
            return Response(
                {'detail': 'No certificates found for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(certificate)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Verify certificate',
        description='Verify a certificate by its number',
        responses={
            200: CertificateSerializer,
            404: OpenApiResponse(description='Certificate not found'),
        },
    )
    @action(detail=False, methods=['get'])
    def verify(self, request):
        certificate_number = request.query_params.get('number')
        
        if not certificate_number:
            return Response(
                {'error': 'Certificate number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            certificate = Certificate.objects.get(certificate_number=certificate_number)
            serializer = CertificateSerializer(certificate)
            return Response(serializer.data)
        except Certificate.DoesNotExist:
            return Response(
                {'error': 'Certificate not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(
        summary='Certificate statistics',
        description='Returns aggregate certificate stats for admin dashboards',
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Admin-level certificate statistics."""
        from django.db.models.functions import TruncMonth
        all_certs = Certificate.objects.all()
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total = all_certs.count()
        this_month = all_certs.filter(issued_at__gte=start_of_month).count()
        total_courses = all_certs.values('enrollment__course').distinct().count()
        valid = all_certs.filter(is_valid=True).count()

        return Response({
            'total': total,
            'this_month': this_month,
            'total_courses_with_certs': total_courses,
            'valid': valid,
        })


@extend_schema(
    tags=['Learning - Discussions'],
    description='Manage discussion threads for courses and sessions',
)
class DiscussionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing discussions."""
    queryset = Discussion.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DiscussionCreateSerializer
        return DiscussionSerializer
    
    def get_queryset(self):
        qs = Discussion.objects.all()
        
        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(course_id=course_id)
            
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)
            
        search = self.request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))
            
        return qs
    
    @extend_schema(
        summary='List discussions',
        description='Returns all discussions',
        parameters=[
            OpenApiParameter(name='course', type=int, description='Filter by course ID'),
            OpenApiParameter(name='session', type=int, description='Filter by session ID'),
            OpenApiParameter(name='search', type=str, description='Search in title and content'),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Create discussion',
        description='Create a new discussion thread',
        request=DiscussionCreateSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get discussion details',
        description='Returns discussion with all replies',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary='Pin/unpin discussion',
        description='Toggle pin status (Instructor/Manager only)',
        responses={200: OpenApiResponse(response={'type': 'object', 'properties': {'is_pinned': {'type': 'boolean'}}})},
    )
    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        """Pin or unpin a discussion thread."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if getattr(request.user, 'role', None) not in (User.Role.INSTRUCTOR, User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return Response({'detail': 'Only instructors and admins can pin discussions.'}, status=status.HTTP_403_FORBIDDEN)
            
        discussion = self.get_object()
        discussion.is_pinned = not discussion.is_pinned
        discussion.save()
        return Response({'is_pinned': discussion.is_pinned})

    @extend_schema(
        summary='Lock/unlock discussion',
        description='Toggle lock status (Instructor/Manager only). When locked, no new replies are allowed.',
        responses={200: OpenApiResponse(response={'type': 'object', 'properties': {'is_locked': {'type': 'boolean'}}})},
    )
    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """Lock or unlock a discussion thread."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if getattr(request.user, 'role', None) not in (User.Role.INSTRUCTOR, User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return Response({'detail': 'Only instructors and admins can lock discussions.'}, status=status.HTTP_403_FORBIDDEN)
            
        discussion = self.get_object()
        discussion.is_locked = not discussion.is_locked
        discussion.save()
        return Response({'is_locked': discussion.is_locked})


@extend_schema(
    tags=['Learning - Discussion Replies'],
    description='Manage replies to discussion threads',
)
class DiscussionReplyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing discussion replies."""
    queryset = DiscussionReply.objects.all()
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DiscussionReplyCreateSerializer
        return DiscussionReplySerializer
    
    def get_queryset(self):
        return DiscussionReply.objects.all()
    
    @extend_schema(
        summary='List replies',
        description='Returns all replies for discussions',
        parameters=[
            OpenApiParameter(name='discussion', type=int, description='Filter by discussion ID'),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Create reply',
        description='Create a new reply to a discussion',
        request=DiscussionReplyCreateSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)


# REPORTS

@extend_schema_view(
    list=extend_schema(
        summary='List reports',
        description='Returns list of generated reports',
    ),
    retrieve=extend_schema(
        summary='Get report',
        description='Returns report details by ID',
    ),
    create=extend_schema(
        summary='Generate report',
        description='Generate a new report',
    ),
)
@extend_schema(
    tags=['Learning - Reports'],
    description='Generate and manage organization reports',
)
class ReportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    ViewSet for managing organization reports.
    Supports listing reports, generating new reports, and downloading reports.
    """
    queryset = Report.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ReportGenerateSerializer
        return ReportSerializer
    
    def get_queryset(self):
        # Users can only see their own reports or all reports if admin/manager
        return Report.objects.filter(generated_by=self.request.user)
    
    @extend_schema(
        summary='List report types',
        description='Returns available report types',
    )
    @action(detail=False, methods=['get'])
    def types(self, request):
        """Get available report types"""
        return Response([
            {'id': 'user_activity', 'name': 'User Activity Report', 'description': 'User login patterns, session durations, platform engagement'},
            {'id': 'course_performance', 'name': 'Course Performance Report', 'description': 'Course completion rates, learner satisfaction scores'},
            {'id': 'enrollment', 'name': 'Enrollment Summary', 'description': 'Enrollment trends, new registrations, drop-off rates'},
            {'id': 'completion', 'name': 'Completion Analytics', 'description': 'Course and module completion, time-to-complete'},
            {'id': 'assessment', 'name': 'Assessment Results', 'description': 'Quiz and assignment scores, pass/fail distributions'},
            {'id': 'revenue', 'name': 'Revenue Report', 'description': 'Financial summary, subscription income, revenue per learner'},
        ])
    
    @extend_schema(
        summary='Generate report',
        description='Generate a new report',
        request=ReportGenerateSerializer,
    )
    def create(self, request, *args, **kwargs):
        """Generate a new report"""
        from .tasks import generate_report
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        report_type = serializer.validated_data['report_type']
        
        report = Report.objects.create(
            report_type=report_type,
            name=f"{report_type.replace('_', ' ').title()} - {timezone.now().strftime('%Y-%m-%d')}",
            generated_by=request.user,
            status=Report.Status.PROCESSING,
            parameters=serializer.validated_data.get('parameters', {}),
        )
        
        generate_report.delay(report.id)
        
        return Response(
            ReportSerializer(report).data,
            status=status.HTTP_201_CREATED
        )
    
    @extend_schema(
        summary='Download report',
        description='Download a generated report file',
    )
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download report file"""
        report = self.get_object()
        
        if report.status != Report.Status.READY or not report.file:
            return Response(
                {'error': 'Report is not ready for download'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return file URL or redirect
        return Response({
            'download_url': report.file.url if report.file else None,
            'file_size': report.file_size,
        })


# SUBMISSIONS (GRADES)

@extend_schema_view(
    list=extend_schema(
        summary='List submissions',
        description='Returns list of learner submissions',
    ),
    retrieve=extend_schema(
        summary='Get submission',
        description='Returns submission details by ID',
    ),
    create=extend_schema(
        summary='Create submission',
        description='Create a new submission',
    ),
    update=extend_schema(
        summary='Update submission',
        description='Update a submission',
    ),
    partial_update=extend_schema(
        summary='Partial update submission',
        description='Partially update a submission',
    ),
    destroy=extend_schema(
        summary='Delete submission',
        description='Delete a submission',
    ),
)
@extend_schema(
    tags=['Learning - Submissions'],
    description='Manage learner submissions and grading',
)
class SubmissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing learner submissions and grades.
    """
    queryset = Submission.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SubmissionCreateSerializer
        if self.action in ('update', 'partial_update'):
            return SubmissionUpdateSerializer
        return SubmissionSerializer
    
    def get_queryset(self):
        # Filter by user for learners, all for instructors/managers
        user = self.request.user
        if user.role in ['instructor', 'org_admin', 'lms_manager', 'tasc_admin']:
            # Instructors and managers can see all submissions for their courses
            return Submission.objects.all()
        # Learners can only see their own submissions
        return Submission.objects.filter(enrollment__user=user)
    
    @extend_schema(
        summary='Grade submission',
        description='Grade a learner submission',
        request=GradeSubmissionSerializer,
    )
    @action(detail=True, methods=['post'])
    def grade(self, request, pk=None):
        """Grade a submission (instructor/admin only)"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if getattr(request.user, 'role', None) not in (User.Role.INSTRUCTOR, User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return Response(
                {'detail': 'Only instructors and admins can grade submissions.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        submission = self.get_object()
        serializer = GradeSubmissionSerializer(
            data=request.data,
            context={'submission': submission}
        )
        serializer.is_valid(raise_exception=True)
        
        submission.grade = serializer.validated_data['grade']
        submission.feedback = serializer.validated_data.get('feedback', '')
        submission.internal_notes = serializer.validated_data.get('internal_notes', '')
        submission.status = Submission.Status.GRADED
        submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save()
        
        return Response(SubmissionSerializer(submission).data)

    @extend_schema(
        summary='Grade statistics',
        description='Get grade distribution and statistics for a course',
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get grade distribution for a course"""
        from django.contrib.auth import get_user_model
        from django.db.models import Avg, Count, Q
        User = get_user_model()
        
        course_id = request.query_params.get('course')
        if not course_id:
            return Response(
                {'course': 'Course ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        submissions = Submission.objects.filter(
            assignment__session__course_id=course_id,
            status=Submission.Status.GRADED,
            grade__isnull=False
        )
        
        total = submissions.count()
        graded = submissions.exclude(grade__isnull=True).count()
        pending = total - graded
        
        avg_grade = submissions.aggregate(Avg('grade'))['grade__avg'] or 0
        
        distribution = [
            {'range': '90-100', 'label': 'A', 'count': submissions.filter(grade__gte=90).count()},
            {'range': '80-89', 'label': 'B', 'count': submissions.filter(grade__gte=80, grade__lt=90).count()},
            {'range': '70-79', 'label': 'C', 'count': submissions.filter(grade__gte=70, grade__lt=80).count()},
            {'range': '60-69', 'label': 'D', 'count': submissions.filter(grade__gte=60, grade__lt=70).count()},
            {'range': '0-59', 'label': 'F', 'count': submissions.filter(grade__lt=60).count()},
        ]
        
        for d in distribution:
            d['percentage'] = round((d['count'] / total * 100), 1) if total > 0 else 0
        
        return Response({
            'total_submissions': total,
            'graded': graded,
            'pending': pending,
            'average_grade': round(avg_grade, 1),
            'distribution': distribution
        })

    @extend_schema(
        summary='Assessment statistics (superadmin)',
        description='Returns aggregate assessment stats: quizzes, assignments, grading status',
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Admin-level assessment statistics."""
        from django.db.models import Avg
        total_assignments = Submission.objects.count()
        graded = Submission.objects.filter(status=Submission.Status.GRADED).count()
        pending = Submission.objects.filter(status=Submission.Status.SUBMITTED).count()
        avg_grade = Submission.objects.filter(
            status=Submission.Status.GRADED, grade__isnull=False
        ).aggregate(avg=Avg('grade'))['avg'] or 0

        total_quizzes = QuizSubmission.objects.count()
        avg_quiz_score = QuizSubmission.objects.aggregate(avg=Avg('score'))['avg'] or 0
        quiz_pass_rate = 0
        if total_quizzes > 0:
            passed = QuizSubmission.objects.filter(passed=True).count()
            quiz_pass_rate = round((passed / total_quizzes) * 100, 1)

        return Response({
            'total_assignments': total_assignments,
            'graded': graded,
            'pending': pending,
            'average_grade': round(avg_grade, 1),
            'total_quizzes': total_quizzes,
            'average_quiz_score': round(avg_quiz_score, 1),
            'quiz_pass_rate': quiz_pass_rate,
        })

    @extend_schema(
        summary='Bulk grade submissions',
        description='Grade multiple submissions at once',
        request=serializers.Serializer,
    )
    @action(detail=False, methods=['post'])
    def bulk_grade(self, request):
        """Bulk grade submissions (instructor/admin only)"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        grades_data = request.data.get('grades', [])
        if not grades_data:
            return Response(
                {'grades': 'This field is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        graded_count = 0
        
        for grade_item in grades_data:
            submission_id = grade_item.get('submission_id')
            grade = grade_item.get('grade')
            feedback = grade_item.get('feedback', '')
            
            if not submission_id or grade is None:
                results.append({
                    'submission_id': submission_id,
                    'status': 'error',
                    'error': 'submission_id and grade are required'
                })
                continue
            
            try:
                submission = Submission.objects.get(id=submission_id)
            except Submission.DoesNotExist:
                results.append({
                    'submission_id': submission_id,
                    'status': 'error',
                    'error': 'Submission not found'
                })
                continue
            
            if submission.status != Submission.Status.SUBMITTED:
                results.append({
                    'submission_id': submission_id,
                    'status': 'error',
                    'error': 'Only submitted submissions can be graded'
                })
                continue
            
            submission.grade = grade
            submission.feedback = feedback
            submission.status = Submission.Status.GRADED
            submission.graded_at = timezone.now()
            submission.graded_by = request.user
            submission.save()
            
            results.append({
                'submission_id': submission_id,
                'status': 'success'
            })
            graded_count += 1
        
        return Response({
            'graded': graded_count,
            'results': results
        })


@extend_schema(
    tags=['Learning - Quiz Submissions'],
    description='Manage quiz submissions and grading',
)
class QuizSubmissionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    ViewSet for quiz submissions.
    - POST: Submit quiz answers (auto-grades)
    - GET: List submissions (filtered by user/enrollment/quiz)
    - GET /{id}: Retrieve single submission with answers
    """
    queryset = QuizSubmission.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return QuizSubmissionCreateSerializer
        return QuizSubmissionSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = QuizSubmission.objects.select_related('enrollment__user', 'quiz__session').prefetch_related('answers')

        if user.role in ['instructor', 'org_admin', 'lms_manager', 'tasc_admin']:
            return queryset

        return queryset.filter(enrollment__user=user)

    def create(self, request, *args, **kwargs):
        serializer = QuizSubmissionCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        return Response(
            QuizSubmissionSerializer(submission).data,
            status=status.HTTP_201_CREATED
        )

from django.db.models import Count, Avg
from django.db.models.functions import TruncMonth
from datetime import timedelta

@extend_schema(tags=['Learning - Analytics'])
class LearningAnalyticsViewSet(viewsets.ViewSet):
    """ViewSet for dashboard analytics regarding enrollments and completion."""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='enrollment-trends')
    def enrollment_trends(self, request):
        months = int(request.query_params.get('months', 6))
        start_date = timezone.now() - timedelta(days=months * 30)

        user = request.user
        base_qs = Enrollment.objects.filter(created_at__gte=start_date)

        if user.role == 'lms_manager' and hasattr(user, 'organization') and user.organization:
            base_qs = base_qs.filter(user__organization=user.organization)
        elif user.role == 'instructor':
            base_qs = base_qs.filter(course__instructor=user)

        # Enrolls by month
        enrolls = base_qs.annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')

        # Completions by month
        comps = base_qs.filter(status='completed').annotate(
            month=TruncMonth('completed_at')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')

        # Build consistent month list
        labels_map = {}
        for i in range(months-1, -1, -1):
            d = timezone.now() - timedelta(days=i*30)
            label = d.strftime('%b %Y')
            labels_map[label] = {'enrollments': 0, 'completions': 0}

        for e in enrolls:
            if e['month']:
                labels_map[e['month'].strftime('%b %Y')]['enrollments'] = e['count']
        for c in comps:
            if c['month']:
                labels_map[c['month'].strftime('%b %Y')]['completions'] = c['count']

        labels = list(labels_map.keys())
        enrollments = [labels_map[l]['enrollments'] for l in labels]
        completions = [labels_map[l]['completions'] for l in labels]

        return Response({
            "labels": labels,
            "enrollments": enrollments,
            "completions": completions
        })

    @action(detail=False, methods=['get'], url_path='learning-stats')
    def learning_stats(self, request):
        user = request.user
        base_qs = Enrollment.objects.all()

        if user.role == 'lms_manager' and hasattr(user, 'organization') and user.organization:
            base_qs = base_qs.filter(user__organization=user.organization)
        elif user.role == 'instructor':
            base_qs = base_qs.filter(course__instructor=user)

        total_learners = base_qs.values('user').distinct().count()
        
        thirty_days_ago = timezone.now() - timedelta(days=30)
        active_learners = base_qs.filter(updated_at__gte=thirty_days_ago).values('user').distinct().count()
        
        avg_completion = base_qs.aggregate(avg=Avg('progress_percentage'))['avg'] or 0.0

        in_progress = base_qs.filter(status='in_progress').count()
        completed = base_qs.filter(status='completed').count()

        quiz_qs = QuizSubmission.objects.all()
        if user.role == 'lms_manager' and hasattr(user, 'organization') and user.organization:
            quiz_qs = quiz_qs.filter(enrollment__user__organization=user.organization)
        elif user.role == 'instructor':
            quiz_qs = quiz_qs.filter(enrollment__course__instructor=user)
            
        avg_quiz = quiz_qs.aggregate(avg=Avg('score'))['avg'] or 0.0

        return Response({
            "total_learners": total_learners,
            "active_learners": active_learners,
            "avg_completion_rate": round(avg_completion, 1),
            "total_courses_in_progress": in_progress,
            "total_completed_courses": completed,
            "avg_quiz_score": round(avg_quiz, 1)
        })


# ═══════════════════════════════════════════════════════════════════════════
# BADGES
# ═══════════════════════════════════════════════════════════════════════════

@extend_schema(
    tags=['Learning - Badges'],
    description='Badge definitions and user badge tracking',
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
        if self.action == 'my_badges':
            return UserBadgeSerializer
        return BadgeSerializer

    def get_queryset(self):
        from apps.learning.models import Badge
        return Badge.objects.all()

    @extend_schema(
        summary='List all badge definitions',
        description='Returns all available badges with their criteria.',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Get current user earned badges',
        description='Returns badges earned by the currently authenticated user.',
    )
    @action(detail=False, methods=['get'], url_path='my-badges')
    def my_badges(self, request):
        from apps.learning.models import UserBadge
        from apps.learning.badge_serializers import UserBadgeSerializer
        qs = UserBadge.objects.filter(user=request.user).select_related('badge')
        serializer = UserBadgeSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary='Check and award badges',
        description='Triggers badge evaluation for the current user. Returns any newly earned badges.',
    )
    @action(detail=False, methods=['post'], url_path='check')
    def check_badges(self, request):
        from apps.learning.badge_engine import check_and_award_badges
        from apps.learning.badge_serializers import UserBadgeSerializer
        newly_earned = check_and_award_badges(request.user)
        serializer = UserBadgeSerializer(newly_earned, many=True)
        return Response({'newly_earned': serializer.data})


# ═══════════════════════════════════════════════════════════════════════════
# SAVED COURSES
# ═══════════════════════════════════════════════════════════════════════════

@extend_schema(
    tags=['Learning - Saved Courses'],
    description='Manage user\'s bookmarked/saved courses',
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
        return SavedCourse.objects.filter(
            user=self.request.user
        ).select_related('course', 'course__instructor', 'course__category')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        summary='List saved courses',
        description='Returns all courses saved/bookmarked by the authenticated user',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Save a course',
        description='Bookmark a course. Send { "course": <id> }.',
        responses={201: SavedCourseSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary='Unsave a course',
        description='Remove a course from bookmarks by saved-course ID',
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary='Toggle save/unsave a course',
        description='If the course is saved, unsave it. If not saved, save it. Returns { "saved": bool }.',
        request={'application/json': {'type': 'object', 'properties': {'course': {'type': 'integer'}}}},
        responses={200: {'type': 'object', 'properties': {'saved': {'type': 'boolean'}, 'id': {'type': 'integer', 'nullable': True}}}},
    )
    @action(detail=False, methods=['post'])
    def toggle(self, request):
        course_id = request.data.get('course')
        if not course_id:
            return Response(
                {'error': 'course field is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            saved = SavedCourse.objects.get(user=request.user, course_id=course_id)
            saved.delete()
            return Response({'saved': False, 'id': None})
        except SavedCourse.DoesNotExist:
            from apps.catalogue.models import Course as CatCourse
            try:
                course = CatCourse.objects.get(id=course_id)
            except CatCourse.DoesNotExist:
                return Response(
                    {'error': 'Course not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            saved = SavedCourse.objects.create(user=request.user, course=course)
            return Response(
                {'saved': True, 'id': saved.id},
                status=status.HTTP_201_CREATED
            )
