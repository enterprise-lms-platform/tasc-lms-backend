from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Enrollment, SessionProgress, Certificate, Discussion, DiscussionReply
)
from .serializers import (
    EnrollmentSerializer, EnrollmentCreateSerializer,
    SessionProgressSerializer, SessionProgressUpdateSerializer,
    CertificateSerializer,
    DiscussionSerializer, DiscussionCreateSerializer,
    DiscussionReplySerializer, DiscussionReplyCreateSerializer
)


@extend_schema(
    tags=['Learning - Enrollments'],
    description='Manage user course enrollments and progress',
)
class EnrollmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing user enrollments."""
    queryset = Enrollment.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return EnrollmentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return SessionProgressUpdateSerializer
        return EnrollmentSerializer
    
    def get_queryset(self):
        return Enrollment.objects.filter(user=self.request.user)
    
    @extend_schema(
        summary='List my enrollments',
        description='Returns list of courses the authenticated user is enrolled in',
        responses={200: EnrollmentSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Enroll in a course',
        description='Enroll the authenticated user in a course',
        request=EnrollmentCreateSerializer,
        responses={201: EnrollmentSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get enrollment details',
        description='Returns detailed enrollment information including progress',
        responses={200: EnrollmentSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        summary='Update enrollment progress',
        description='Update enrollment progress and completion status',
        request=EnrollmentSerializer,
        responses={200: EnrollmentSerializer},
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
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
    tags=['Learning - Session Progress'],
    description='Track user progress through individual course sessions',
)
class SessionProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for managing session progress."""
    queryset = SessionProgress.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return SessionProgressUpdateSerializer
        return SessionProgressSerializer
    
    def get_queryset(self):
        return SessionProgress.objects.filter(enrollment__user=self.request.user)
    
    @extend_schema(
        summary='List session progress',
        description='Returns progress for all sessions across user enrollments',
        parameters=[
            OpenApiParameter(name='enrollment', type=int, description='Filter by enrollment ID'),
            OpenApiParameter(name='session', type=int, description='Filter by session ID'),
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
    tags=['Learning - Discussions'],
    description='Manage discussion threads for courses and sessions',
)
class DiscussionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing discussions."""
    queryset = Discussion.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DiscussionCreateSerializer
        return DiscussionSerializer
    
    def get_queryset(self):
        return Discussion.objects.all()
    
    @extend_schema(
        summary='List discussions',
        description='Returns all discussions',
        parameters=[
            OpenApiParameter(name='course', type=int, description='Filter by course ID'),
            OpenApiParameter(name='session', type=int, description='Filter by session ID'),
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
    tags=['Learning - Discussion Replies'],
    description='Manage replies to discussion threads',
)
class DiscussionReplyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing discussion replies."""
    queryset = DiscussionReply.objects.all()
    permission_classes = [IsAuthenticated]
    
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
