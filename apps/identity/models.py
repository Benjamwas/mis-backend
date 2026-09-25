"""Identity, people, users, roles and permissions.

Following the SALA spec:
- A `Person` holds shared biographical/contact data.
- A `User` belongs to a Person and may (or may not) be able to log in.
- Roles and permissions are modeled explicitly; users receive roles scoped
  to a school (or platform-wide for SUPER_ADMIN).
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import EmailValidator
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel, SoftDeleteModel, UUIDPKMixin


def _token_expiry():
    return timezone.now() + timedelta(hours=settings.AUTHSLUG_LIFETIME_HOURS)


def timezone_now():
    return timezone.now()


class UserStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    SUSPENDED = "SUSPENDED", "Suspended"
    LOCKED = "LOCKED", "Locked"
    PENDING = "PENDING", "Pending"


class RoleCode(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
    SCHOOL_ADMIN = "SCHOOL_ADMIN", "School Admin"
    FINANCE_ADMIN = "FINANCE_ADMIN", "Finance Admin"
    HR_ADMIN = "HR_ADMIN", "HR Admin"
    CLASS_TEACHER = "CLASS_TEACHER", "Class Teacher"
    SUBJECT_TEACHER = "SUBJECT_TEACHER", "Subject Teacher"
    PARENT = "PARENT", "Parent"
    STUDENT = "STUDENT", "Student"


# --------------------------------------------------------------------------
# Person
# --------------------------------------------------------------------------
class Person(UUIDPKMixin, TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"
        OTHER = "OTHER", "Other"

    first_name = models.CharField(max_length=120)
    middle_name = models.CharField(max_length=120, blank=True, default="")
    last_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.OTHER)
    phone = models.CharField(max_length=30, blank=True, default="", db_index=True)
    email = models.EmailField(blank=True, default="", db_index=True)
    address = models.CharField(max_length=255, blank=True, default="")
    photo_url = models.URLField(blank=True, default="")

    class Meta:
        verbose_name_plural = "people"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)


# --------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------
class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, person, email, username, password, **extra):
        if not email and not username:
            raise ValueError("A username or email is required.")
        email = self.normalize_email(email) if email else ""
        user = self.model(person=person, email=email, username=username or email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, person, email, username=None, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(person, email, username, password, **extra)

    def create_superuser(self, person, email, username=None, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("status", UserStatus.ACTIVE)
        return self._create_user(person, email, username, password, **extra)


class User(UUIDPKMixin, AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="users")
    username = models.CharField(max_length=150, unique=True, db_index=True)
    email = models.EmailField(validators=[EmailValidator()], unique=True, db_index=True)
    status = models.CharField(max_length=12, choices=UserStatus.choices, default=UserStatus.PENDING, db_index=True)
    is_staff = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email or self.username

    @property
    def full_name(self):
        return self.person.full_name

    @property
    def is_active(self):
        if self.status == UserStatus.LOCKED and self.locked_until and self.locked_until > timezone_now():
            return False
        return self.status not in {UserStatus.INACTIVE, UserStatus.SUSPENDED}

    def activate(self):
        self.status = UserStatus.ACTIVE
        self.failed_login_count = 0
        self.locked_until = None
        self.save(update_fields=["status", "failed_login_count", "locked_until", "updated_at"])

    def deactivate(self):
        self.status = UserStatus.INACTIVE
        self.save(update_fields=["status", "updated_at"])

    def suspend(self):
        self.status = UserStatus.SUSPENDED
        self.save(update_fields=["status", "updated_at"])

    def lock(self):
        from django.utils import timezone
        from datetime import timedelta

        self.status = UserStatus.LOCKED
        self.locked_until = timezone.now() + timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
        self.save(update_fields=["status", "locked_until", "updated_at"])

    def record_login(self):
        from django.utils import timezone

        self.last_login_at = timezone.now()
        self.failed_login_count = 0
        self.locked_until = None
        self.status = UserStatus.ACTIVE
        self.save(update_fields=["last_login_at", "failed_login_count", "locked_until", "status", "updated_at"])


# --------------------------------------------------------------------------
# Roles & Permissions
# --------------------------------------------------------------------------
class PermissionCode:
    _CODES = None

    @classmethod
    def all(cls):
        if cls._CODES is None:
            from apps.identity.seed import PERMISSION_CODES

            cls._CODES = PERMISSION_CODES
        return cls._CODES


class Permission(UUIDPKMixin, TimeStampedModel):
    code = models.CharField(max_length=120, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    module = models.CharField(max_length=120, default="", blank=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(UUIDPKMixin, TimeStampedModel):
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=80, unique=True, db_index=True, choices=RoleCode.choices)
    description = models.TextField(blank=True, default="")
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class RolePermission(UUIDPKMixin, TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uq_role_permission"),
        ]


class UserRole(UUIDPKMixin, TimeStampedModel):
    """Assigns a role to a user, optionally scoped to a school.

    SUPER_ADMIN roles use school=NULL (platform scope).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="user_roles",
        null=True,
        blank=True,
        db_index=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role", "school"], name="uq_user_role_school"),
        ]
        indexes = [models.Index(fields=["user", "school"])]

    def __str__(self):
        scope = self.school_id or "PLATFORM"
        return f"{self.user_id} -> {self.role.code} @ {scope}"


class UserGrant(UUIDPKMixin, TimeStampedModel):
    """Explicit per-user permission grants (in addition to role permissions)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_grants")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="user_grants")
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="user_grants", null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "permission", "school"], name="uq_user_grant_school"),
        ]


class PasswordResetToken(UUIDPKMixin, TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=_token_expiry)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expired(self):
        return timezone_now() > self.expires_at

    def __str__(self):
        return f"{self.user_id}:{self.token[:8]}..."