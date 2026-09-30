# SALA School Digital Platform Architecture

## 1. System Overview

SALA is a multi-tenant school operations platform with two applications:

- `Frontend/`: React and TypeScript single-page application.
- `backend/`: Django and Django REST Framework API.

The frontend serves public school content and authenticated portals. The backend owns authentication, authorization, school data, business rules, reporting, audit history, files, payments, and communication delivery.

The normal request path is:

```text
Browser
  -> React Router page
  -> Frontend API client
  -> /api/v1/
  -> Django URL router
  -> Domain ViewSet or APIView
  -> Serializer and permission checks
  -> Domain service
  -> Database and external provider integrations
```

## 2. Frontend Architecture

### Application shell

`Frontend/src/App.tsx` owns route registration. Routes are grouped into:

- Public pages: home, academics, admissions, application tracking, news, contact, and login.
- Parent portal.
- Student portal.
- Teacher portal.
- School administrator portal.
- Finance portal.
- HR portal.
- Super administrator portal.

`AppProvider` in `Frontend/src/contexts/AppContext.tsx` owns session state, role state, selected school, toast notifications, and login/logout behavior.

`RequireAuth` protects portal route groups. It checks:

1. Whether the application has finished booting.
2. Whether a demo or API session exists.
3. Whether the current role is allowed to enter the route group.

### API client

`Frontend/src/api/client.ts` is the single HTTP boundary. It:

- Adds the JWT bearer token.
- Adds `X-School-Id` when a school context is selected.
- Normalizes relative paths before joining them to `/api/v1`.
- Parses the SALA response envelope.
- Refreshes an expired access token once.
- Exposes `get`, `post`, `patch`, `put`, and `delete` methods.
- Supports JSON and multipart `FormData` requests.

`Frontend/src/api/hooks.ts` provides read helpers:

- `useList`: list resources.
- `useObject`: object responses.
- `useDetail`: detail resources.
- `useDashboard`: dashboard endpoints.

In demo mode, portal pages use local data modules. In API mode, pages should use the backend response and only fall back to local data where the feature has not yet been connected.

## 3. Backend Application Boundaries

The backend is split into domain applications. Each app owns models, serializers, views, URLs, and business services for one area.

| App | Responsibility |
| --- | --- |
| `identity` | Users, people, roles, permissions, JWT login, password flows |
| `schools` | Schools, modules, academic years, terms, grades, classes, settings |
| `people` | Students, parents, and parent/student relationships |
| `academics` | Subjects, enrollments, teaching assignments, assignments, grading, results |
| `lms` | Topics, lessons, resources, and student topic progress |
| `attendance` | Student and employee attendance |
| `finance` | Fee structures, invoices, payments, allocations, receipts, M-Pesa hooks |
| `admissions` | Applicants, applications, decisions, enrollment |
| `crm` | Leads, interactions, tasks, and school visits |
| `hr` | Employees, leave, payroll, duties, and HR tickets |
| `communication` | Announcements, notifications, campaigns, email, SMS, WhatsApp |
| `content` | CMS pages, posts, events, galleries |
| `reporting` | Dashboards, reports, exports, and global search |
| `audit` | Immutable audit history |
| `files` | File validation, storage, linking, and archive behavior |

All domain URLs are mounted from `backend/config/urls.py` under `/api/v1/`.

## 4. Request and Response Contracts

Successful API responses use the envelope renderer:

```json
{
  "success": true,
  "data": {},
  "meta": {}
}
```

Errors use the exception envelope:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Readable error message"
  }
}
```

The frontend API client returns the value inside `data` to pages and throws `ApiError` for non-2xx responses.

## 5. Authentication and Tenant Isolation

### Authentication

1. The frontend posts credentials to `/api/v1/auth/login`.
2. The backend validates the account and returns access and refresh JWTs.
3. The frontend stores the tokens in browser storage.
4. The frontend calls `/api/v1/auth/me`.
5. The backend returns role codes, permission codes, and school IDs.
6. The frontend maps the highest-priority role to a portal role.

Access tokens last a short period. On a `401`, the frontend calls `/auth/refresh` once and retries the original request.

### School context

School-scoped requests resolve a school using:

- The user's only school, when the user belongs to one school.
- `X-School-Id`, when a user belongs to multiple schools.
- The selected school header for super administrators.
- No school context for platform-wide super administrator operations.

`SchoolScopedViewSet` applies the resolved school to querysets. Services must also validate that related records belong to the same school before mutating data.

### Permission layers

Permissions are checked at several layers:

- DRF authentication classes require a valid JWT.
- `HasPermission` checks a granular permission code in the current school.
- `IsSuperAdmin` restricts platform operations.
- `SchoolObjectPermission` checks object ownership by school.
- Service functions repeat important ownership and business validations.

Superusers bypass granular permission checks, but they still need a school header for operations that require a school-specific business context.

## 6. Domain Service Pattern

Views should coordinate HTTP concerns. Complex business logic belongs in `services.py`.

Typical mutation flow:

```text
Request
  -> permission check
  -> school resolution
  -> serializer validation
  -> transaction.atomic service
  -> audit event
  -> notification or external side effect
  -> response serializer
```

Multi-record operations use `transaction.atomic()` so the database cannot be left half-updated. Finance payment allocation, attendance recording, assignment grading, result publication, and admission decisions follow this pattern.

## 7. LMS Architecture

The LMS is split between the `lms` app and the `academics` app.

### LMS-owned records

- `Topic`: subject-level learning unit.
- `Lesson`: ordered lesson belonging to a topic.
- `Resource`: file or external resource belonging to a lesson.
- `StudentTopicProgress`: per-student percentage and progress status for a topic.
- `Quiz`: published question set attached to a topic.
- `QuizAttempt`: immutable scored attempt belonging to a student and quiz.

### Academics-owned learning records

- `TeachingAssignment`: teacher, class, subject, and term scope.
- `Assignment`: work published against a teaching assignment and optional LMS topic.
- `AssignmentSubmission`: learner submission.
- `AssignmentGrade`: marks and feedback for a submission.
- `StudentSubjectResult`: published subject result.
- `LearningRecommendation`: personalized next-step recommendation.

### LMS routes

```text
/api/v1/lms/topics/
/api/v1/lms/lessons/
/api/v1/lms/resources/
/api/v1/lms/progress/
/api/v1/lms/quizzes/
/api/v1/subjects/assignments/
/api/v1/subjects/results/
```

Topic actions:

```text
POST /lms/topics/{id}/publish/
POST /lms/topics/{id}/archive/
```

Progress action:

```text
POST /lms/progress/{id}/update_progress/
POST /lms/quizzes/{id}/publish/
POST /lms/quizzes/{id}/submit/
GET  /lms/quizzes/{id}/attempts/
```

Assignment actions:

```text
POST /subjects/assignments/{id}/publish/
POST /subjects/assignments/{id}/close/
POST /subjects/assignments/{id}/submit/
GET  /subjects/assignments/{id}/submissions/
POST /subjects/assignments/{id}/grade_student/
POST /subjects/assignments/{id}/request_resubmission/
```

### LMS visibility rules

- Students see published topics, published lessons, and resources under published content.
- Students see assignments attached to their active class enrollment.
- Students see and update only their own topic progress.
- Teachers and school administrators may manage content according to their permission codes.
- Teachers can grade only assignments inside their teaching scope unless they have a broader assignment permission.

## 8. LMS Trigger Flows

### Topic publication

```text
Teacher creates topic
  -> TopicViewSet validates subject school
  -> topic is created as DRAFT
  -> teacher calls publish action
  -> topic becomes PUBLISHED
  -> audit event is recorded
  -> student topic queries can return it
```

### Lesson and resource creation

```text
Teacher creates lesson
  -> topic ownership is validated
  -> lesson is assigned to the active school
  -> lesson may be published after content is ready

Teacher uploads a resource
  -> FileUpload validates size and MIME type
  -> storage driver writes local or Supabase storage
  -> FileUpload record links the stored file to the lesson or submission
```

### Student learning progress

```text
Student opens a published topic
  -> frontend loads topic and progress lists
  -> student completes a lesson step
  -> frontend posts progress_percentage
  -> backend clamps percentage to 0..100
  -> backend derives NOT_STARTED, IN_PROGRESS, or COMPLETED
  -> last_activity_at is updated
```

### Assignment publication

```text
Teacher creates assignment
  -> teaching assignment and optional topic are school-validated
  -> assignment starts as DRAFT
  -> teacher publishes it
  -> assignment becomes PUBLISHED
  -> enrolled learners can see it
  -> in-app class notifications are generated
```

### Quiz submission

```text
Student loads a published quiz
  -> frontend receives the question set and attempt count
  -> student submits answer indexes
  -> backend validates the student and attempt limit
  -> backend scores answers against the stored question set
  -> QuizAttempt is persisted with score and percentage
  -> frontend displays the saved result
```

### Assignment submission

```text
Student opens a published assignment
  -> student enters text and optionally selects a file
  -> backend creates or updates the student's submission
  -> file is uploaded and linked to the submission
  -> submission becomes SUBMITTED
  -> teacher submission list includes it
```

### Assignment grading

```text
Teacher opens assignment submissions
  -> backend enforces teacher scope
  -> teacher submits marks and feedback
  -> marks are validated against max_marks
  -> previous grade is replaced transactionally
  -> submission becomes GRADED
  -> learner notification is generated
```

### Resubmission request

```text
Teacher requests resubmission
  -> submission becomes RETURNED
  -> learner can submit again unless already permanently graded
```

## 9. Files and Storage

The file system is abstracted behind `apps.files.storage`.

- `STORAGE_DRIVER=local` uses Django filesystem storage.
- `STORAGE_DRIVER=supabase` uses the Supabase storage adapter.

The backend validates:

- Maximum size: 25 MB.
- Allowed MIME types.
- School ownership.
- Link metadata such as `linked_type` and `linked_id`.

Files should be uploaded through `/api/v1/files/uploads/`, not directly from a page to storage.

## 10. Communication and Background Work

Communication has three delivery categories:

- In-app notifications stored in the database.
- Email through Django's configured email backend.
- SMS and WhatsApp through provider adapters.

Celery tasks are used for fan-out and external delivery. In development, `EMAIL_DELIVERY_MODE=sync` and `CELERY_TASK_ALWAYS_EAGER=1` allow the system to operate without Redis. In production, asynchronous mode should be used with a running Redis broker and Celery worker.

Email flow:

```text
Domain event
  -> dispatch_transactional_email()
  -> synchronous send in development OR Celery task in production
  -> EmailService
  -> SMTP/email backend
  -> DeliveryLog
```

SMS and WhatsApp are optional provider integrations. Missing credentials should produce a recorded failed delivery rather than break unrelated dashboard reads.

## 11. Payments and Other Cross-Domain Triggers

### Successful payment

```text
Payment request or webhook
  -> validate school and provider reference
  -> create payment idempotently
  -> allocate payment to invoices
  -> update invoice balances and statuses
  -> issue receipt PDF
  -> optionally notify guardians
  -> audit all mutations
```

### Admission decision

```text
Admin changes application status
  -> application history record
  -> audit event
  -> transactional email
  -> optional enrollment creation when accepted
```

### Published results

```text
Teacher/admin publishes result set
  -> school-scoped result validation
  -> results become PUBLISHED
  -> audit events are written
  -> student and guardian notifications are generated
```

## 12. Audit and Observability

Mutations should produce audit records containing:

- User.
- School.
- Action.
- Module.
- Entity type and ID.
- Old and new values when relevant.
- Request ID and request metadata where available.

Health endpoints:

```text
GET /health
GET /ready
```

`/health` checks process availability. `/ready` checks database availability and, when required by environment settings, Redis availability.

## 13. Environment Modes

### Development

- SQLite or local PostgreSQL may be used.
- Email can use the console backend.
- Celery tasks run eagerly when configured.
- Redis is optional.
- Demo data can be recreated with `manage.py seed_demo`.

### Production

- PostgreSQL should be used.
- A strong secret and separate JWT signing key are required.
- SMTP must be configured for real email delivery.
- Redis and Celery workers should be enabled for asynchronous work.
- Supabase or another durable storage backend should be used for files.
- `DEBUG` must be disabled and allowed hosts/CORS restricted.

## 14. Known Architectural Boundaries

- The frontend still has demo fallback data for areas without complete API integration.
- Quiz questions and attempts are persisted in the LMS app; the frontend keeps the local quiz as a fallback for demo mode or unavailable API data.
- Celery-backed SMS and WhatsApp remain optional integrations.
- Dashboard aggregation is read-only and should not be used as a replacement for domain records.
- Seed data is development data and must never be run against production school records.
