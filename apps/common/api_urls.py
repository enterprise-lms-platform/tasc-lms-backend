from django.urls import path, include

urlpatterns = [
    path("", include("apps.common.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("public/", include("apps.catalogue.urls_public")),
    path("catalogue/", include("apps.catalogue.urls")),
    path("learning/", include("apps.learning.urls")),
    path("payments/", include("apps.payments.urls")),
]
