"""Sync Permission, Role and RolePermission records from the seed catalogue.

Idempotent: safe to re-run after code changes add new permission codes.
"""
from django.core.management.base import BaseCommand

from apps.identity.models import Permission, Role, RoleCode, RolePermission
from apps.identity.seed import PERMISSION_CODES, PERMISSION_LABELS, PERMISSION_MODULES, ROLE_PERMISSIONS


class Command(BaseCommand):
    help = "Create/update Permission and Role records from the seed catalogue."

    def handle(self, *args, **options):
        created = 0
        for code in PERMISSION_CODES:
            _, was_created = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": PERMISSION_LABELS.get(code, code),
                    "module": PERMISSION_MODULES.get(code, ""),
                },
            )
            if was_created:
                created += 1

        for role_code in RoleCode.choices:
            value = role_code[0]
            perm_codes = ROLE_PERMISSIONS.get(value, set())
            role, _ = Role.objects.update_or_create(
                code=value,
                defaults={"name": role_code[1], "is_system": True},
            )
            wanted = {c for c in perm_codes if Permission.objects.filter(code=c).exists()}
            existing = set(role.permissions.values_list("code", flat=True))
            to_add = wanted - existing
            to_remove = existing - wanted
            for code in to_add:
                RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
            for code in to_remove:
                perm = Permission.objects.get(code=code)
                RolePermission.objects.filter(role=role, permission=perm).delete()

        self.stdout.write(self.style.SUCCESS(f"Permissions synced. {created} new permission(s)."))