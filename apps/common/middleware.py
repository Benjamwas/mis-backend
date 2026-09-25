"""Request-scoped context: request_id, user_id, school_id, timing and structured logging."""
import logging
import threading
import time
import uuid

_local = threading.local()

logger = logging.getLogger("apps")

RESERVED_KEYS = {"asctime", "levelname", "module", "process", "thread", "msecs", "created", "name"}


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        ctx = getattr(_local, "context", {})
        for key in RESERVED_KEYS:
            setattr(record, key, getattr(record, key, None))
        for key, value in ctx.items():
            setattr(record, key, value)
        record.request_id = ctx.get("request_id", "-")
        record.user_id = ctx.get("user_id", "-")
        record.school_id = ctx.get("school_id", "-")
        record.method = ctx.get("method", "-")
        record.path = ctx.get("path", "-")
        return True


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.perf_counter()

        user = None
        school = None
        if getattr(request, "user", None) and request.user.is_authenticated:
            user = request.user.id
            school = _resolve_school(request)

        _local.context = {
            "request_id": request.request_id,
            "user_id": user or "-",
            "school_id": school or "-",
            "method": request.method,
            "path": request.path,
        }

        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response["X-Request-ID"] = request.request_id
        if not getattr(response, "streaming", False):
            response["Access-Control-Expose-Headers"] = "X-Request-ID"

        logger.info(
            "request method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )
        _local.context = {}
        return response


def _resolve_school(request):
    """Best-effort school context from header or the user's single school."""
    from apps.identity.services import get_user_schools

    header = request.headers.get("X-School-Id")
    schools = get_user_schools(request.user)
    if header and header in [str(s.id) for s in schools]:
        return header
    if len(schools) == 1:
        return str(schools[0].id)
    return None


def get_request_context():
    return getattr(_local, "context", {})