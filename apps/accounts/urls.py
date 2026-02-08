from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import me, verify_email, invite_user
from .auth_views import (
    LoginView,
    RefreshView,
    RegisterView,
    verify_email,
    password_reset_request,
    password_reset_confirm,
    resend_verification_email,
    change_password,
    logout,
    set_password_from_invite,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/<uidb64>/<token>/", verify_email, name="accounts-email-verify"),
    path("login/", LoginView.as_view(), name="token_obtain_pair"),
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("me/", me, name="me"),
    path("password-reset/", password_reset_request, name="password-reset"),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        password_reset_confirm,
        name="password-reset-confirm",
    ),
    path("resend-verification/", resend_verification_email, name="resend-verification"),
    path("change-password/", change_password, name="change-password"),
    path("logout/", logout, name="logout"),
    path(
        "set-password/<uidb64>/<token>/",
        set_password_from_invite,
        name="set-password-from-invite",
    ),
]
