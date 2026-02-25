from django.urls import path, include
from apps.accounts.views import invite_user
from apps.common.views import PresignUploadView

urlpatterns = [
    path("uploads/presign/", PresignUploadView.as_view(), name="uploads-presign"),
    path("", include("apps.common.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("admin/users/invite/", invite_user, name="admin-invite-user"),
    path("superadmin/", include("apps.audit.urls")),
    path("public/", include("apps.catalogue.urls_public")),
    path("catalogue/", include("apps.catalogue.urls")),
    path("learning/", include("apps.learning.urls")),
    path("payments/", include("apps.payments.urls")),
]
