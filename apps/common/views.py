import uuid
from pathlib import Path

from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .spaces import create_boto3_client


ALLOWED_UPLOAD_PREFIXES = {"course-thumbnails", "course-banners"}
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
EXTENSION_FALLBACKS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


class UploadPresignRequestSerializer(serializers.Serializer):
    prefix = serializers.ChoiceField(choices=sorted(ALLOWED_UPLOAD_PREFIXES))
    filename = serializers.CharField(max_length=255)
    content_type = serializers.ChoiceField(choices=sorted(ALLOWED_CONTENT_TYPES))


def _key_extension(filename, content_type):
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in ALLOWED_EXTENSIONS:
        return "jpg" if ext == "jpeg" else ext
    return EXTENSION_FALLBACKS[content_type]


def _public_url_for_key(key):
    return f'{settings.DO_SPACES_CDN_BASE_URL.rstrip("/")}/{key}'


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
    responses={200: dict},
    examples=[
        OpenApiExample(
            "Presign response",
            value={
                "upload_url": "https://example-presigned-url",
                "public_url": "https://cdn.example.com/course-thumbnails/uuid.png",
                "method": "PUT",
                "headers": {"Content-Type": "image/png"},
            },
            response_only=True,
        )
    ],
)
class PresignUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UploadPresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        required_settings = {
            "DO_SPACES_BUCKET": settings.DO_SPACES_BUCKET,
            "DO_SPACES_ENDPOINT": settings.DO_SPACES_ENDPOINT,
            "DO_SPACES_ACCESS_KEY_ID": settings.DO_SPACES_ACCESS_KEY_ID,
            "DO_SPACES_SECRET_ACCESS_KEY": settings.DO_SPACES_SECRET_ACCESS_KEY,
            "DO_SPACES_CDN_BASE_URL": settings.DO_SPACES_CDN_BASE_URL,
        }
        missing = [k for k, v in required_settings.items() if not v]
        if missing:
            return Response(
                {"detail": f"Spaces upload is not configured. Missing: {', '.join(missing)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        ext = _key_extension(data["filename"], data["content_type"])
        key = f'{data["prefix"]}/{uuid.uuid4()}.{ext}'

        s3_client = create_boto3_client()
        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.DO_SPACES_BUCKET,
                "Key": key,
                "ContentType": data["content_type"],
                "ACL": "public-read",
            },
            ExpiresIn=settings.DO_SPACES_PRESIGN_EXPIRY_SECONDS,
            HttpMethod="PUT",
        )

        return Response(
            {
                "upload_url": upload_url,
                "public_url": _public_url_for_key(key),
                "method": "PUT",
                "headers": {
                    "Content-Type": data["content_type"],
                    "x-amz-acl": "public-read",
                },
            }
        )
