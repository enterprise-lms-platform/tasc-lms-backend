from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic.base import RedirectView
from drf_spectacular.renderers import OpenApiJsonRenderer
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI schema + docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema.json",
        SpectacularAPIView.as_view(api_version=None, renderer_classes=[OpenApiJsonRenderer]),
        name="schema-json",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "documentation/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="documentation",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Versioned API
    path("api/v1/", include("apps.common.api_urls")),
    re_path(
        r"^(?!api/)(?!admin/)(?!documentation/).*$",
        RedirectView.as_view(pattern_name="documentation", permanent=False),
    ),
]
