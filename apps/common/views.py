"""Health and readiness endpoints."""
import logging

from django.conf import settings
from django.db import connection
from redis import Redis
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("apps.common")


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class ReadinessView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {"database": False, "redis": False}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                checks["database"] = True
        except Exception as exc:  # noqa: BLE001
            logger.error("readiness db check failed: %s", exc)

        try:
            client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
            client.ping()
            checks["redis"] = True
        except Exception as exc:  # noqa: BLE001
            logger.error("readiness redis check failed: %s", exc)

        healthy = all(checks.values())
        return Response({"healthy": healthy, "checks": checks}, status=200 if healthy else 503)