import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .spaces import create_boto3_client
from apps.accounts.rbac import is_course_writer
from apps.catalogue.models import Course, Session, Assignment
from apps.learning.models import Enrollment


ALLOWED_UPLOAD_PREFIXES = {"course-thumbnails", "course-banners", "session-assets", "submission-files"}
ALLOWED_CONTENT_TYPES_PUBLIC = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_CONTENT_TYPES_SESSION_ASSETS = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
}
ALLOWED_CONTENT_TYPES = ALLOWED_CONTENT_TYPES_PUBLIC | ALLOWED_CONTENT_TYPES_SESSION_ASSETS
EXTENSION_FALLBACKS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
}
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "mp4", "webm", "mov", "pdf", "zip"}


class UploadPresignRequestSerializer(serializers.Serializer):
    prefix = serializers.ChoiceField(choices=sorted(ALLOWED_UPLOAD_PREFIXES))
    filename = serializers.CharField(max_length=255)
    content_type = serializers.ChoiceField(choices=sorted(ALLOWED_CONTENT_TYPES))
    course_id = serializers.IntegerField(required=False, allow_null=True)
    session_id = serializers.IntegerField(required=False, allow_null=True)
    enrollment_id = serializers.IntegerField(required=False, allow_null=True)
    assignment_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        prefix = attrs["prefix"]
        content_type = attrs["content_type"]

        if prefix == "submission-files":
            enrollment_id = attrs.get("enrollment_id")
            assignment_id = attrs.get("assignment_id")
            err = {}
            if enrollment_id is None:
                err["enrollment_id"] = "enrollment_id is required for submission-files."
            if assignment_id is None:
                err["assignment_id"] = "assignment_id is required for submission-files."
            if err:
                raise serializers.ValidationError(err)
            if content_type not in ALLOWED_CONTENT_TYPES_SESSION_ASSETS:
                raise serializers.ValidationError(
                    {"content_type": "submission-files only allows video, PDF, or zip content types."}
                )
            return attrs

        if prefix == "session-assets":
            course_id = attrs.get("course_id")
            session_id = attrs.get("session_id")
            err = {}
            if course_id is None:
                err["course_id"] = "course_id is required for session-assets."
            if session_id is None:
                err["session_id"] = "session_id is required for session-assets."
            if err:
                raise serializers.ValidationError(err)
            if content_type not in ALLOWED_CONTENT_TYPES_SESSION_ASSETS:
                raise serializers.ValidationError(
                    {"content_type": "session-assets only allows video, PDF, or zip content types."}
                )
        else:
            if content_type not in ALLOWED_CONTENT_TYPES_PUBLIC:
                raise serializers.ValidationError(
                    {"content_type": "course-thumbnails and course-banners only allow image content types."}
                )
        return attrs


def _key_extension(filename, content_type):
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in ALLOWED_EXTENSIONS:
        return "jpg" if ext == "jpeg" else ext
    return EXTENSION_FALLBACKS.get(content_type, "bin")


def _sanitize_filename(filename):
    """Remove path separators and other unsafe characters from filename."""
    # Keep alphanumeric, dots, hyphens, underscores
    base = Path(filename).name
    sanitized = re.sub(r"[^\w.\-]", "_", base)
    return sanitized or "file"


def _public_url_for_key(key):
    return f'{settings.DO_SPACES_CDN_BASE_URL.rstrip("/")}/{key}'


def _can_edit_course(user, course):
    """Same logic as CanEditCourse: admin-like can edit any; instructor only their own."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    role = getattr(user, "role", None)
    if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
        return True
    if role == User.Role.INSTRUCTOR:
        return course.instructor_id == user.id
    return False


@extend_schema(
    tags=["Common"],
    summary="Health check",
    responses={200: dict},
    examples=[
        OpenApiExample(
            "OK",
            value={"status": "ok", "service": "tasc-lms-api"},
            response_only=True,
        )
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok", "service": "tasc-lms-api"})


@extend_schema(
    tags=["Common"],
    summary="Create upload presigned URL",
    request=UploadPresignRequestSerializer,
    responses={200: dict, 403: dict, 503: dict},
    examples=[
        OpenApiExample(
            "Presign response (public image)",
            value={
                "upload_url": "https://example-presigned-url",
                "public_url": "https://cdn.example.com/course-thumbnails/uuid.png",
                "object_key": "course-thumbnails/uuid.png",
                "bucket": "tasc-public",
                "expires_in": 300,
                "method": "PUT",
                "headers": {"Content-Type": "image/png", "x-amz-acl": "public-read"},
            },
            response_only=True,
        ),
        OpenApiExample(
            "Presign response (session-assets, private)",
            value={
                "upload_url": "https://example-presigned-url",
                "object_key": "session-assets/course_1/session_5/uuid/intro.mp4",
                "bucket": "tasc-private",
                "expires_in": 300,
                "method": "PUT",
                "headers": {"Content-Type": "video/mp4"},
            },
            response_only=True,
        ),
    ],
)
class PresignUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UploadPresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        prefix = data["prefix"]
        is_session_assets = prefix == "session-assets"
        is_submission_files = prefix == "submission-files"

        if is_submission_files:
            if not getattr(settings, "DO_SPACES_PRIVATE_BUCKET", None):
                raise ImproperlyConfigured(
                    "DO_SPACES_PRIVATE_BUCKET is required for submission-files uploads."
                )
            for k in ("DO_SPACES_ENDPOINT", "DO_SPACES_ACCESS_KEY_ID", "DO_SPACES_SECRET_ACCESS_KEY"):
                if not getattr(settings, k, None):
                    return Response(
                        {"detail": f"Spaces upload is not configured. Missing: {k}"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
            enrollment = get_object_or_404(Enrollment, pk=data["enrollment_id"])
            assignment = get_object_or_404(Assignment, pk=data["assignment_id"])
            if enrollment.user_id != request.user.id:
                return Response(
                    {"detail": "You can only upload submission files for your own enrollments."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if assignment.session.course_id != enrollment.course_id:
                return Response(
                    {"detail": "Assignment does not belong to your enrollment's course."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            bucket = settings.DO_SPACES_PRIVATE_BUCKET
            use_public_acl = False
            sanitized = _sanitize_filename(data["filename"])
            ext = _key_extension(data["filename"], data["content_type"])
            key = (
                f"submission-files/enrollment_{enrollment.id}/assignment_{assignment.id}/"
                f"{uuid.uuid4()}/{Path(sanitized).stem}.{ext}"
            )
        elif is_session_assets:
            if not getattr(settings, "DO_SPACES_PRIVATE_BUCKET", None):
                raise ImproperlyConfigured(
                    "DO_SPACES_PRIVATE_BUCKET is required for session-assets uploads."
                )
            for k in ("DO_SPACES_ENDPOINT", "DO_SPACES_ACCESS_KEY_ID", "DO_SPACES_SECRET_ACCESS_KEY"):
                if not getattr(settings, k, None):
                    return Response(
                        {"detail": f"Spaces upload is not configured. Missing: {k}"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
            # Permissions: course writers only; instructor must own the course
            if not is_course_writer(request.user):
                return Response(
                    {"detail": "Only course writers (Instructor, LMS Manager, TASC Admin) can presign session-assets."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            course = get_object_or_404(Course, pk=data["course_id"])
            session = get_object_or_404(Session, pk=data["session_id"], course=course)
            if not _can_edit_course(request.user, course):
                return Response(
                    {"detail": "You do not have permission to upload assets for this course."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            bucket = settings.DO_SPACES_PRIVATE_BUCKET
            use_public_acl = False
            sanitized = _sanitize_filename(data["filename"])
            ext = _key_extension(data["filename"], data["content_type"])
            key = (
                f"session-assets/course_{course.id}/session_{session.id}/"
                f"{uuid.uuid4()}/{Path(sanitized).stem}.{ext}"
            )
        else:
            required_settings = {
                "DO_SPACES_ENDPOINT": settings.DO_SPACES_ENDPOINT,
                "DO_SPACES_ACCESS_KEY_ID": settings.DO_SPACES_ACCESS_KEY_ID,
                "DO_SPACES_SECRET_ACCESS_KEY": settings.DO_SPACES_SECRET_ACCESS_KEY,
                "DO_SPACES_CDN_BASE_URL": settings.DO_SPACES_CDN_BASE_URL,
            }
            missing = [k for k, v in required_settings.items() if not v]
            if not getattr(settings, "DO_SPACES_PUBLIC_BUCKET", None):
                missing.append("DO_SPACES_PUBLIC_BUCKET")
            if missing:
                return Response(
                    {"detail": f"Spaces upload is not configured. Missing: {', '.join(missing)}"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            bucket = settings.DO_SPACES_PUBLIC_BUCKET
            use_public_acl = True
            ext = _key_extension(data["filename"], data["content_type"])
            key = f"{prefix}/{uuid.uuid4()}.{ext}"

        s3_client = create_boto3_client()
        expires_in = settings.DO_SPACES_PRESIGN_EXPIRY_SECONDS
        params = {
            "Bucket": bucket,
            "Key": key,
            "ContentType": data["content_type"],
        }
        if use_public_acl:
            params["ACL"] = "public-read"
        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )

        headers = {"Content-Type": data["content_type"]}
        if use_public_acl:
            headers["x-amz-acl"] = "public-read"

        response_data = {
            "upload_url": upload_url,
            "object_key": key,
            "bucket": bucket,
            "expires_in": expires_in,
            "method": "PUT",
            "headers": headers,
        }
        if use_public_acl:
            response_data["public_url"] = _public_url_for_key(key)

        return Response(response_data)


@extend_schema(
    tags=["Common"],
    summary="Get storage quota",
    description="Get storage usage for the current organization or platform",
    responses={
        200: {
            'used_bytes': 5368709120,
            'total_bytes': 10737418240
        }
    },
)
class StorageQuotaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = request.user
        role = getattr(user, 'role', None)
        
        DEFAULT_QUOTA_BYTES = 10 * 1024 * 1024 * 1024
        
        total_bytes = DEFAULT_QUOTA_BYTES
        
        used_bytes = 0
        
        if hasattr(settings, 'DO_SPACES_CDN_BASE_URL') and settings.DO_SPACES_CDN_BASE_URL:
            try:
                s3_client = create_boto3_client()
                
                prefix = ""
                if role in [User.Role.INSTRUCTOR, User.Role.LMS_MANAGER, User.Role.TASC_ADMIN]:
                    prefix = f"session-assets/course_"
                elif role == User.Role.LEARNER:
                    prefix = f"submission-files/"
                
                if prefix:
                    buckets = []
                    if getattr(settings, 'DO_SPACES_PUBLIC_BUCKET', None):
                        buckets.append(settings.DO_SPACES_PUBLIC_BUCKET)
                    if getattr(settings, 'DO_SPACES_PRIVATE_BUCKET', None):
                        buckets.append(settings.DO_SPACES_PRIVATE_BUCKET)
                    
                    for bucket in buckets:
                        try:
                            response = s3_client.list_objects_v2(
                                Bucket=bucket,
                                Prefix=prefix,
                                MaxKeys=1000
                            )
                            if 'Contents' in response:
                                for obj in response['Contents']:
                                    used_bytes += obj.get('Size', 0)
                        except Exception:
                            pass
                            
            except Exception:
                pass
        
        return Response({
            "used_bytes": used_bytes,
            "total_bytes": total_bytes
        })
