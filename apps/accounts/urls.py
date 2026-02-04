from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import me, verify_email
from .auth_views import LoginView, RefreshView, RegisterView, verify_email
from .google_auth_views import (
    google_oauth_login,
    google_oauth_link,
    google_oauth_unlink,
    google_oauth_status
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/<uidb64>/<token>/", verify_email, name="accounts-email-verify"),
    path("login/", LoginView.as_view(), name="token_obtain_pair"),
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("me/", me, name="me"),
    # Google OAuth endpoints
    path("google/login/", google_oauth_login, name="google_oauth_login"),
    path("google/link/", google_oauth_link, name="google_oauth_link"),
    path("google/unlink/", google_oauth_unlink, name="google_oauth_unlink"),
    path("google/status/", google_oauth_status, name="google_oauth_status"),
]