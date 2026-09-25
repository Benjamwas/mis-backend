"""Standard, domain errors and a DRF exception handler producing the SALA error envelope."""

from django.http import JsonResponse
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class SalaError(APIException):
    """Base error carrying a stable machine-readable `code`."""

    code = "ERROR"
    default_detail = "An error occurred."
    default_status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message="", code=None, status_code=None, errors=None):
        self.detail = message or self.default_detail
        self.error_code = code or self.code
        self.errors = errors or None
        self.status_code = status_code or self.default_status_code


class NotFoundError(SalaError):
    code = "NOT_FOUND"
    default_detail = "The requested resource does not exist."
    default_status_code = status.HTTP_404_NOT_FOUND


class PermissionDeniedError(SalaError):
    code = "PERMISSION_DENIED"
    default_detail = "You do not have permission to perform this action."
    default_status_code = status.HTTP_403_FORBIDDEN


class TenantIsolationError(SalaError):
    code = "TENANT_ISOLATION"
    default_detail = "The requested resource is outside the caller's school context."
    default_status_code = status.HTTP_403_FORBIDDEN


class ValidationFailedError(SalaError):
    code = "VALIDATION_ERROR"
    default_detail = "Validation failed."
    default_status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class ConflictError(SalaError):
    code = "CONFLICT"
    default_detail = "The operation conflicts with the current state."
    default_status_code = status.HTTP_409_CONFLICT


class ModuleDisabledError(SalaError):
    code = "MODULE_DISABLED"
    default_detail = "This feature is not enabled for the school."
    default_status_code = status.HTTP_403_FORBIDDEN


class AccountingError(SalaError):
    code = "ACCOUNTING_ERROR"
    default_detail = "The financial operation could not be completed."
    default_status_code = status.HTTP_409_CONFLICT


class IdempotencyConflict(SalaError):
    code = "IDEMPOTENCY_CONFLICT"
    default_detail = "A request with this idempotency key already exists."
    default_status_code = status.HTTP_409_CONFLICT


class ProviderNotConfiguredError(SalaError):
    code = "PROVIDER_NOT_CONFIGURED"
    default_detail = "The external provider has not been configured."
    default_status_code = status.HTTP_503_SERVICE_UNAVAILABLE


def exception_handler(exc, context):
    """Route both DRF and custom Sala errors to the standard envelope.

    DRF validation errors are flattened into a `field_errors` structure.
    """
    response = drf_exception_handler(exc, context)

    if isinstance(exc, SalaError):
        body = {
            "success": False,
            "data": None,
            "error": {
                "code": exc.error_code,
                "message": str(exc.detail),
            },
        }
        if exc.errors:
            body["error"]["field_errors"] = exc.errors
        return JsonResponse(body, status=exc.status_code)

    if response is not None:
        code = _django_code(exc)
        detail = _extract_detail(response.data)
        body = {
            "success": False,
            "data": None,
            "error": {"code": code, "message": detail},
        }
        if hasattr(exc, "detail") and isinstance(exc.detail, dict):
            body["error"]["field_errors"] = exc.detail
        response.data = body
        return response

    return None


def _django_code(exc):
    mapping = {
        "AuthenticationFailed": "AUTHENTICATION_FAILED",
        "NotAuthenticated": "UNAUTHENTICATED",
        "PermissionDenied": "PERMISSION_DENIED",
        "NotFound": "NOT_FOUND",
        "MethodNotAllowed": "METHOD_NOT_ALLOWED",
        "Throttled": "RATE_LIMITED",
        "ValidationError": "VALIDATION_ERROR",
    }
    cls = exc.__class__.__name__
    return mapping.get(cls, "ERROR")


def _extract_detail(data):
    if isinstance(data, dict):
        # pick first error
        for key, val in data.items():
            if isinstance(val, list) and val:
                return str(val[0])
            elif isinstance(val, (list, dict)) and val:
                return str(val)
        return str(data)
    if isinstance(data, list) and data:
        return str(data[0])
    return str(data)