from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


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
