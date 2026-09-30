"""Authentication views: login, refresh, logout, password flows, profile."""
import logging

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from apps.audit.services import audit
from apps.common.exceptions import PermissionDeniedError, ValidationFailedError
from apps.identity.models import PasswordResetToken, UserStatus
from apps.identity.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    UserSerializer,
)

logger = logging.getLogger("apps.identity")

User = get_user_model()

LOCK_PREFIX = "salalogin:lock:"
FAIL_PREFIX = "salalogin:fail:"


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []  # brute-force handled by lockout service below

    def post(self, request):
        from django.conf import settings

        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]

        identity = f"{email}:{request.META.get('REMOTE_ADDR', '')}"
        if cache.get(LOCK_PREFIX + identity):
            raise PermissionDeniedError(
                "Too many failed login attempts. Try again later.", code="ACCOUNT_LOCKED", status_code=429
            )

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.check_password(password):
            self._record_failure(identity)
            raise ValidationFailedError("Invalid email or password.", code="INVALID_CREDENTIALS", status_code=401)

        if user.status == UserStatus.LOCKED and user.locked_until and user.locked_until > timezone.now():
            raise PermissionDeniedError("Account is locked. Try again later.", code="ACCOUNT_LOCKED", status_code=423)
        if user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
            raise PermissionDeniedError("Account is not active.", code="ACCOUNT_INACTIVE", status_code=403)
        if user.status == UserStatus.PENDING:
            user.activate()

        refresh = RefreshToken.for_user(user)
        user.record_login()
        cache.delete(LOCK_PREFIX + identity)
        cache.delete(FAIL_PREFIX + identity)

        audit(request, user, "auth.login", "AUTH", "User", str(user.id), new_value={"login": True})

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )

    def _record_failure(self, identity):
        from django.conf import settings

        fails = cache.get(FAIL_PREFIX + identity, 0) + 1
        cache.set(FAIL_PREFIX + identity, fails, timeout=settings.LOGIN_LOCKOUT_SECONDS)
        if fails >= settings.LOGIN_FAILURE_THRESHOLD:
            cache.set(LOCK_PREFIX + identity, 1, timeout=settings.LOGIN_LOCKOUT_SECONDS)


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            raise ValidationFailedError("refresh token is required.", code="REFRESH_REQUIRED")
        try:
            token = RefreshToken(refresh)
            user_id = token["user_id"]
            user = User.objects.get(pk=user_id)
            if user.status == UserStatus.LOCKED and user.locked_until and user.locked_until > timezone.now():
                raise PermissionDeniedError("Account is locked.", code="ACCOUNT_LOCKED", status_code=423)
            if user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
                raise PermissionDeniedError("Account is not active.", code="ACCOUNT_INACTIVE", status_code=403)
            return Response({"access": str(token.access_token), "refresh": str(token)})
        except TokenError:
            raise ValidationFailedError("Refresh token is invalid or expired.", code="INVALID_REFRESH_TOKEN", status_code=401)
        except User.DoesNotExist:
            raise ValidationFailedError("Refresh token is invalid or expired.", code="INVALID_REFRESH_TOKEN", status_code=401)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                token = RefreshToken(refresh)
                token.blacklist()
            except TokenError:
                logger.warning("logout with invalid refresh token ignored")
        audit(request, request.user, "auth.logout", "AUTH", "User", str(request.user.id), new_value={"logout": True})
        return Response({"message": "Logged out."})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        if user:
            token = PasswordResetToken.objects.create(user=user)
            from apps.communication.tasks import dispatch_transactional_email

            dispatch_transactional_email(
                to_email=user.email,
                subject="SALA Password Reset",
                template="password_reset",
                context={"name": user.full_name, "reset_link": f"{request.build_absolute_uri('/')[:-1]}/reset-password?token={token.token}"},
            )
        # always return success to avoid user enumeration
        return Response({"message": "If that email exists, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_str = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]
        token = PasswordResetToken.objects.filter(token=token_str).select_related("user").first()
        if not token or token.is_expired or token.used_at:
            raise ValidationFailedError("Reset token is invalid or expired.", code="INVALID_RESET_TOKEN", status_code=400)
        token.user.set_password(new_password)
        token.user.status = UserStatus.ACTIVE
        token.user.save()
        token.used_at = timezone.now()
        token.save()
        audit(request, token.user, "auth.password_reset", "AUTH", "User", str(token.user.id), new_value={"reset": True})
        return Response({"message": "Password has been reset."})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        audit(request, request.user, "auth.change_password", "AUTH", "User", str(request.user.id), new_value={"changed": True})
        return Response({"message": "Password changed."})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = User.objects.select_related("person").prefetch_related("user_roles__role__permissions").get(pk=request.user.pk)
        from apps.identity.services import effective_permission_codes, get_user_school_ids

        school_ids = get_user_school_ids(user)
        data = UserSerializer(user).data
        data["school_ids"] = school_ids
        data["permissions"] = sorted(effective_permission_codes(user))
        # active role codes as primary-role for the frontend
        data["roles"] = [ur.role.code for ur in user.user_roles.all()]
        return Response(data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(request.user, serializer.validated_data)
        audit(request, request.user, "auth.profile_update", "AUTH", "User", str(request.user.id), new_value=serializer.validated_data)
        user = User.objects.select_related("person").get(pk=request.user.pk)
        return Response(UserSerializer(user).data)
