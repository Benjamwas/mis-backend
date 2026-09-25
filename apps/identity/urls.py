from django.urls import path

from apps.identity.views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("password-reset/request", PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("password-reset/confirm", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("change-password", ChangePasswordView.as_view(), name="auth-change-password"),
    path("me", MeView.as_view(), name="auth-me"),
]