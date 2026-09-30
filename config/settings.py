"""
SALA School Digital Platform - Django settings.

Environment-driven configuration. No secrets are hardcoded.
"""
from datetime import timedelta
from pathlib import Path

import dj_database_url
from corsheaders.defaults import default_headers

from config.env import env_bool, env_int, env_list, env_str, BASE_DIR

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = env_str("SECRET_KEY", "dev-insecure-secret-change-me")
DEBUG = env_bool("DEBUG", True)
ENVIRONMENT = env_str("ENVIRONMENT", "development")

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

APP_URL = env_str("APP_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = env_str("FRONTEND_URL", "http://localhost:5173").rstrip("/")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

SITE_ID = 1

# --------------------------------------------------------------------------
# Installed apps
# --------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # only used when Postgres is active
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.common",
    "apps.identity",
    "apps.schools",
    "apps.people",
    "apps.academics",
    "apps.lms",
    "apps.attendance",
    "apps.finance",
    "apps.admissions",
    "apps.crm",
    "apps.hr",
    "apps.communication",
    "apps.content",
    "apps.reporting",
    "apps.audit",
    "apps.files",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# --------------------------------------------------------------------------
# Middleware
# --------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.RequestContextMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DATABASES: dict = {}
if env_bool("DB_SQLITE", False):
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
else:
    database_url = env_str("DATABASE_URL", "")
    if database_url:
        DATABASES["default"] = dj_database_url.parse(database_url, conn_max_age=600)
        if env_str("DB_SSLMODE", "prefer") == "require":
            DATABASES["default"]["OPTIONS"] = {"sslmode": "require"}
    else:
        DATABASES["default"] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env_str("DB_NAME", "sala"),
            "USER": env_str("DB_USER", "postgres"),
            "PASSWORD": env_str("DB_PASSWORD", "postgres"),
            "HOST": env_str("DB_HOST", "localhost"),
            "PORT": env_str("DB_PORT", "5432"),
            "CONN_MAX_AGE": 600,
            "OPTIONS": {"sslmode": env_str("DB_SSLMODE", "prefer")},
        }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Use a compatible DB-independent app registry is default; `django.contrib.postgres`
# is only harmless when Postgres is inactive but its code paths are never hit.

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "identity.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": env_str("JWT_ALGORITHM", "HS256"),
    "SIGNING_KEY": env_str("JWT_SIGNING_KEY", "") or SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
}

# Login protection
LOGIN_FAILURE_THRESHOLD = env_int("LOGIN_FAILURE_THRESHOLD", 5)
LOGIN_LOCKOUT_SECONDS = env_int("LOGIN_LOCKOUT_SECONDS", 300)

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.exception_handler",
    "DEFAULT_RENDERER_CLASSES": (
        "apps.common.renderers.EnvelopeRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "600/min",
        "login": "10/min",
        "auth_otp": "20/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SALA School Digital Platform API",
    "DESCRIPTION": (
        "REST API for St. Ann Lifred Academy Schools. "
        "Versioned under /api/v1/ with role-based access control and school-level tenant isolation."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"])
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = list(default_headers) + ["x-school-id", "idempotency-key"]
CORS_EXPOSE_HEADERS = ["Content-Disposition", "x-request-id"]

# --------------------------------------------------------------------------
# Storage / files
# --------------------------------------------------------------------------
STORAGE_DRIVER = env_str("STORAGE_DRIVER", "local")
if STORAGE_DRIVER == "local":
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
elif STORAGE_DRIVER == "supabase":
    DEFAULT_FILE_STORAGE = "apps.files.storage.SupabaseStorage"
    STORAGES = {
        "default": {"BACKEND": "apps.files.storage.SupabaseStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

MEDIA_ROOT = BASE_DIR / env_str("MEDIA_ROOT", "media")
MEDIA_URL = "/media/"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --------------------------------------------------------------------------
# Supabase helpers (never leaked to frontend; backend-only)
# --------------------------------------------------------------------------
SUPABASE_URL = env_str("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = env_str("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = env_str("SUPABASE_STORAGE_BUCKET", "sala-files")

# --------------------------------------------------------------------------
# Celery / Redis
# --------------------------------------------------------------------------
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env_str("CELERY_REDIS_URL", "redis://localhost:6379/1")
REDIS_REQUIRED = env_bool("REDIS_REQUIRED", ENVIRONMENT != "development")
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", ENVIRONMENT == "development")
CELERY_TASK_EAGER_PROPAGATES = env_bool("CELERY_TASK_EAGER_PROPAGATES", ENVIRONMENT == "development")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Nairobi"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 30
CELERY_BEAT_SCHEDULE = {}

# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "SALA <no-reply@sala.example.com>")
if DEBUG and not EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Development can deliver email inline when Redis/Celery is not available. Set
# EMAIL_DELIVERY_MODE=async in production when a Celery worker is running.
EMAIL_DELIVERY_MODE = env_str("EMAIL_DELIVERY_MODE", "sync" if ENVIRONMENT == "development" else "async").lower()

# --------------------------------------------------------------------------
# Communication providers
# --------------------------------------------------------------------------
SMS_PROVIDER = env_str("SMS_PROVIDER", "")
SMS_PROVIDER_URL = env_str("SMS_PROVIDER_URL", "")
SMS_PROVIDER_API_KEY = env_str("SMS_PROVIDER_API_KEY", "")
SMS_PROVIDER_SENDER_ID = env_str("SMS_PROVIDER_SENDER_ID", "")
TWILIO_ACCOUNT_SID = env_str("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = env_str("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = env_str("TWILIO_FROM_NUMBER", "")
WHATSAPP_PROVIDER = env_str("WHATSAPP_PROVIDER", "")
WHATSAPP_FROM_NUMBER = env_str("WHATSAPP_FROM_NUMBER", "")

# --------------------------------------------------------------------------
# M-Pesa (Daraja)
# --------------------------------------------------------------------------
MPESA_ENVIRONMENT = env_str("MPESA_ENVIRONMENT", "sandbox")
MPESA_CONSUMER_KEY = env_str("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = env_str("MPESA_CONSUMER_SECRET", "")
MPESA_PASSKEY = env_str("MPESA_PASSKEY", "")
MPESA_SHORTCODE = env_str("MPESA_SHORTCODE", "")
MPESA_BUSINESS_SHORTCODE = env_str("MPESA_BUSINESS_SHORTCODE", "")
MPESA_CALLBACK_BASE_URL = env_str("MPESA_CALLBACK_BASE_URL", APP_URL)
MPESA_INITIATOR_NAME = env_str("MPESA_INITIATOR_NAME", "")
MPESA_INITIATOR_PASSWORD = env_str("MPESA_INITIATOR_PASSWORD", "")

# --------------------------------------------------------------------------
# Logging - structured
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} request_id={request_id} message={message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
    },
    "filters": {"request_context": {"()": "apps.common.middleware.RequestContextFilter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose", "filters": ["request_context"]},
        "console_simple": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.db.backends": {"handlers": ["console_simple"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# --------------------------------------------------------------------------
# Rates / misc
# --------------------------------------------------------------------------
PHONE_REGEX = r"^\+?[0-9\s\-()]{7,20}$"
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB max upload body

# Finance settings
PAYMENT_IDEMPOTENCY_WINDOW_HOURS = 24
RECEIPT_PREFIX = "RCP"
INVOICE_PREFIX = "INV"
PAYMENT_PREFIX = "PAY"
APPLICATION_PREFIX = "APP"
ADMISSION_NUMBER_PREFIX = "SALA"

# Internationalization
LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True
