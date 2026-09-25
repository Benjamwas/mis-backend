"""Shared implementation conventions for SALA backend domain apps.

Domain agents MUST follow these contracts so cross-app references are consistent.
"""

# ---------------------------------------------------------------------------
# Primary keys
# ---------------------------------------------------------------------------
# Every model uses UUID primary keys via `apps.common.models.UUIDPKMixin`.

# ---------------------------------------------------------------------------
# Base mixins (apps/common/models.py)
# ---------------------------------------------------------------------------
# - UUIDPKMixin:        id = UUIDField(primary_key=True)
# - TimeStampedModel:   created_at, updated_at
# - SoftDeleteModel:    is_deleted, deleted_at, deleted_by  (+ `.delete()` is soft)
# - SchoolScopedModel:  school = FK("schools.School", related_name="+")
#
# A school-scoped model inherits (note: MRO order matters):
#     class X(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
#
# Use `objects = ...` ONLY when overriding non-soft managers is intended.

# ---------------------------------------------------------------------------
# Canonical cross-app model names (do not rename these)
# ---------------------------------------------------------------------------
# identity.User, identity.Person, identity.Role, identity.RolePermission,
#     identity.UserRole, identity.UserGrant, identity.PasswordResetToken
# schools.School, schools.Module, schools.SchoolModule, schools.AcademicYear,
#     schools.Term, schools.GradeLevel, schools.SchoolClass, schools.SchoolSettings
# people.Parent, people.Student, people.ParentStudent
# academics.Subject, academics.ClassSubject, academics.TeachingAssignment,
#     academics.Enrollment, academics.Assignment, academics.AssignmentSubmission,
#     academics.AssignmentGrade, academics.Assessment, academics.AssessmentScore,
#     academics.StudentSubjectResult, academics.LearningRecommendation
# lms.Topic, lms.Lesson, lms.Resource, lms.StudentTopicProgress
# attendance.AttendanceSession, attendance.StudentAttendance, attendance.EmployeeAttendance
# finance.FeeStructure, finance.StudentFeeAccount, finance.Invoice,
#     finance.InvoiceItem, finance.Payment, finance.PaymentAllocation, finance.Receipt
# admissions.AdmissionApplication, admissions.Applicant,
#     admissions.ApplicationDocument, admissions.ApplicationStatusHistory
# crm.CrmLead, crm.CrmInteraction, crm.CrmTask, crm.SchoolVisit
# hr.Department, hr.Employee, hr.TeacherProfile, hr.LeaveType, hr.LeaveRequest,
#     hr.PayrollPeriod, hr.Payslip, hr.PayslipItem, hr.Duty, hr.DutyAssignment,
#     hr.HrTicket, hr.HrTicketMessage
# communication.Announcement, communication.Notification,
#     communication.NotificationTemplate, communication.BroadcastCampaign,
#     communication.BroadcastRecipient
# content.CmsPage, content.CmsPost, content.Event, content.EventParticipant,
#     content.GalleryAlbum, content.GalleryMedia
# files.FileUpload

# ---------------------------------------------------------------------------
# Canonical related_names used across apps (do not deviate)
# ---------------------------------------------------------------------------
# school-owned models: school = FK(... related_name="+") from SchoolScopedModel
# people.Student.person -> related_name="students"
# people.Parent.person   -> related_name="parents"
# hr.Employee.person     -> related_name="hr_employees"

# ---------------------------------------------------------------------------
# Choice enums (single source of truth naming)
# ---------------------------------------------------------------------------
# Student statuses: ACTIVE, ARCHIVED  (people.Student.Status)
# Enrollment status: ACTIVE, COMPLETED, TRANSFERRED_OUT, DROPPED, PENDING
# Attendance: PRESENT, ABSENT, LATE, EXCUSED
# Payment: PENDING, PROCESSING, SUCCESS, FAILED, CANCELLED, REVERSED, REFUNDED
# Application: DRAFT, SUBMITTED, UNDER_REVIEW, SHORTLISTED, INTERVIEW,
#     DECISION_PENDING, ACCEPTED, REJECTED, WAITLISTED, ENROLLED, WITHDRAWN

# ---------------------------------------------------------------------------
# URL layout
# ---------------------------------------------------------------------------
# config/urls.py already wires every app under /api/v1/. Domain apps only need
# to populate their own urls.py. Auth lives at /api/v1/auth/*.

# ---------------------------------------------------------------------------
# View conventions
# ---------------------------------------------------------------------------
# - School-scoped list views inherit apps.common.viewsets.SchoolScopedViewSet
#   which filters by school automatically.
# - Permission classes come from apps.common.permissions.
# - Complex logic lives in `services.py`; querysets/selectors in `selectors.py`.
# - Multi-step mutations wrap in django.db.transaction.atomic().
# - Audit events via apps.audit.services.audit(request, user, action, module,
#   entity_type, entity_id, old_value=..., new_value=..., school=...).
# - Errors: raise apps.common.exceptions.* subclasses.

# ---------------------------------------------------------------------------
# Response envelopes
# ---------------------------------------------------------------------------
# Success: {"success": true, "data": ..., "meta": {...}}
# Errors:  {"success": false, "data": null, "error": {"code":..., "message":...}}

# ---------------------------------------------------------------------------
# Module gating
# ---------------------------------------------------------------------------
# Endpoints that belong to a switchable product module should use
# apps.common.permissions.ModuleEnabled with the module code (e.g. "FINANCE").