"""Permission code catalogue and default role->permission matrix.

This is the single source of truth for RBAC. The `sync_permissions` management
command seeds these into the database. View/API permissions reference these codes.
"""

MODULES = [
    "school", "user", "module", "dashboard", "report", "audit",
    "student", "parent", "teacher", "class", "subject", "enrollment", "term",
    "assignment", "assessment", "result", "attendance",
    "fee", "invoice", "payment", "receipt",
    "admission", "lead", "visit", "crm",
    "leave", "payroll", "payslip", "duty", "hrticket", "employee", "department",
    "notification", "announcement", "campaign", "communication",
    "cms", "event", "gallery", "file",
]

_PERMISSIONS = {
    "school": ["read", "update"],
    "user": ["read", "create", "update", "delete", "manage-role"],
    "module": ["read", "manage"],
    "dashboard": ["read", "finance", "hr"],
    "report": ["read", "export"],
    "audit": ["read"],
    "student": ["read", "create", "update", "delete"],
    "parent": ["read", "create", "update"],
    "teacher": ["read", "create", "update"],
    "class": ["read", "create", "update"],
    "subject": ["read", "create", "update"],
    "enrollment": ["read", "create", "update", "transfer", "close"],
    "term": ["read", "create", "update"],
    "assignment": ["read", "create", "update", "delete", "grade", "publish"],
    "assessment": ["read", "create", "update", "delete", "record"],
    "result": ["read", "create", "update", "publish"],
    "attendance": ["read", "record", "update"],
    "fee": ["read", "create", "update"],
    "invoice": ["read", "create", "update", "reverse"],
    "payment": ["read", "create", "reverse", "allocate"],
    "receipt": ["read", "create"],
    "admission": ["read", "create", "update", "approve", "reject"],
    "lead": ["read", "create", "update"],
    "visit": ["read", "create", "update"],
    "crm": ["read", "manage"],
    "leave": ["read", "request", "approve", "reject"],
    "payroll": ["read", "manage"],
    "payslip": ["read", "create", "manage"],
    "duty": ["read", "manage"],
    "hrticket": ["read", "create", "update"],
    "employee": ["read", "create", "update", "manage"],
    "department": ["read", "create", "update"],
    "notification": ["read", "create", "send"],
    "announcement": ["read", "create", "send"],
    "campaign": ["read", "create", "manage", "send"],
    "communication": ["read", "create", "send"],
    "cms": ["read", "create", "update", "publish"],
    "event": ["read", "create", "update"],
    "gallery": ["read", "create", "update", "publish"],
    "file": ["read", "create", "upload", "delete"],
}

PERMISSION_CODES: list[str] = [
    f"{module}.{action}" for module, actions in _PERMISSIONS.items() for action in actions
]

PERMISSION_LABELS: dict[str, str] = {
    f"{module}.{action}": f"{module.replace('_', ' ').title()} {action.title()}"
    for module, actions in _PERMISSIONS.items()
    for action in actions
}

PERMISSION_MODULES: dict[str, str] = {
    f"{module}.{action}": module for module, actions in _PERMISSIONS.items() for action in actions
}


def _codes_for(*modules: str) -> set[str]:
    result = set()
    for module in modules:
        for action in _PERMISSIONS.get(module, []):
            result.add(f"{module}.{action}")
    return result


# Role -> permission codes
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "SUPER_ADMIN": set(PERMISSION_CODES),
    "SCHOOL_ADMIN": _codes_for(
        "school", "user", "module", "dashboard", "report", "audit",
        "student", "parent", "teacher", "class", "subject", "enrollment", "term",
        "assignment", "assessment", "result", "attendance",
        "fee", "invoice", "payment", "receipt",
        "admission", "lead", "visit", "crm",
        "leave", "payroll", "payslip", "duty", "hrticket", "employee", "department",
        "notification", "announcement", "campaign",
        "cms", "event", "gallery", "file",
    ),
    "FINANCE_ADMIN": _codes_for(
        "dashboard", "report", "student", "fee", "invoice", "payment", "receipt",
        "notification", "file",
    ),
    "HR_ADMIN": _codes_for(
        "dashboard", "report", "employee", "department", "leave", "payroll", "payslip",
        "duty", "hrticket", "attendance", "notification", "file", "payslip",
    ),
    "CLASS_TEACHER": _codes_for(
        "dashboard", "report", "student", "parent", "class", "subject", "enrollment",
        "assignment", "assessment", "result", "attendance", "notification",
        "event", "communication", "file", "gallery",
    ),
    "SUBJECT_TEACHER": _codes_for(
        "dashboard", "student", "subject", "assignment", "assessment", "result",
        "notification", "communication", "file",
    ),
    "PARENT": _codes_for(
        "dashboard", "parent", "student", "result", "attendance", "fee", "invoice", "payment",
        "receipt", "event", "announcement", "notification", "communication",
    ),
    "STUDENT": _codes_for(
        "dashboard", "student", "subject", "assignment", "assessment", "result",
        "attendance", "event", "announcement", "notification", "file",
    ),
}

# Dashboard finance/HR views are portal-specific. Teachers, parents and students
# keep only the read-level overview; finance and HR admins do not cross portal
# lines. SUPER_ADMIN/SCHOOL_ADMIN retain both via their "dashboard" module grant.
for _role in ("CLASS_TEACHER", "SUBJECT_TEACHER", "PARENT", "STUDENT"):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] - {"dashboard.finance", "dashboard.hr"}
ROLE_PERMISSIONS["HR_ADMIN"].discard("dashboard.finance")
ROLE_PERMISSIONS["FINANCE_ADMIN"].discard("dashboard.hr")


def permissions_for_role(role_code: str) -> set[str]:
    return ROLE_PERMISSIONS.get(role_code, set())
