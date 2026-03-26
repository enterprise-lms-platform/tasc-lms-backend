# TASC LMS Backend — Pending Tasks

**Last updated:** 27 March 2026
**Repo:** `tasc-lms-backend`
**Contact for questions:** Coordinate with frontend team on endpoint contracts

---

## How to Use This File

This file tracks all known incomplete work in the backend codebase. Each item includes:
- Exact file paths and line numbers
- What already exists vs what's missing
- **Concrete request/response examples** so you can implement without guessing
- Frontend impact

When you pick up a task, update this file.

---

## Completed Items

| # | Item | Details |
|---|------|---------|
| 1 | Quiz Submission System | `QuizSubmission`/`QuizAnswer` models, serializers, views, and migration all implemented |
| 2 | Report Generation / Celery | Celery infrastructure (`config/celery.py`), async `generate_report` task in `apps/learning/tasks.py` with all 6 report types |
| 3 | Bulk User Import (Superadmin) | Full CSV parsing with validation, error tracking, file size/row limits in `apps/accounts/views_superadmin.py` |
| 4 | LivestreamQuestion Model | Model, migration, serializers, and endpoints implemented in `apps/livestream/` |
| 8 | ReportViewSet Data Queries | Covered by #2 — Celery report generation |
| 9a | Bulk Grade Action | Implemented in `apps/learning/views.py` |
| 9b | Grade Statistics Action | Implemented in `apps/learning/views.py` |
| 14 | Migration Backfill | `backfill()` function fully implemented in migration 0009 |
| — | Course Reviews | New `CourseReview` model, serializers, and viewset added |
| — | Public Endpoints | `/api/v1/public/stats/`, `/api/v1/public/clients/`, `/api/v1/uploads/quota/` all implemented |
| — | Celery Setup | `config/celery.py`, broker config in settings, `apps/learning/tasks.py` |
| 0a | Public Course Search & Ordering | Added `SearchFilter` + `OrderingFilter` to `PublicCourseViewSet`. Search fields: `title`, `short_description`, `instructor__first_name`, `instructor__last_name`. Ordering fields: `title`, `published_at`, `enrollment_count`. Default: `-published_at`. |
| — | Category courses_count | Added `courses_count` annotated field to `CategorySerializer` and `PublicCategoryViewSet` queryset (`Count` + `Q` for published courses only) |
| — | InvoiceViewSet date filters | Added `from_date`/`to_date` query params to `InvoiceViewSet.list()` |
| — | EnrollmentViewSet search | Added `search` filter (user name/email, course title) to `EnrollmentViewSet.get_queryset()` |
| — | SessionProgressViewSet filters | Implemented `enrollment`, `session`, `course` filters (were documented in OpenAPI but not implemented) |
| — | Livestream Tests & Setup | Added `apps/livestream/tests.py` and `apps/livestream/admin.py` |
| 12 | Calendar Service | Fixed timezone caching silent error in `apps/livestream/services/calendar_service.py` |
| 15 | Livestream Webhooks | Renamed `validate_webhook` to `webhook_health` in `apps/livestream/views.py` and `urls.py` |
| 46 | Livestream Session Creation | Verified `IsInstructorOrReadOnly` and added `IsLmsManager` in `LivestreamSessionViewSet` |
| 24 | Messaging API | Created `messaging` app, defined models, and implemented endpoints with 100% test coverage |
| 4 | DiscussionViewSet Moderation | Added `@action` endpoints `/pin/` and `/lock/` (toggle) with RBAC, search/filter query params (`course`, `session`, `search`) in `get_queryset()`, locked-reply validation in `DiscussionReplyCreateSerializer` [26 Mar] |
| 7 | SubmissionViewSet Validation | Added `attempt_number` to Submission model, `unique_together` updated, file-type validation against `Assignment.allowed_file_types`, attempt-limit enforcement against `Assignment.max_attempts`, `attempt_number` exposed in serializer [26 Mar] |
| 0b | Manager Bulk Import | Implemented manager-scoped bulk import with frontend CSV header mapping (`email_address`→`email`, `user_role`→`role`, `full_name`→`first_name`/`last_name`) and auto org-assignment [26 Mar] |
| DB | Analytics ViewSets | `LearningAnalyticsViewSet` (enrollment-trends, learning-stats), `PaymentAnalyticsViewSet` (revenue), `CatalogueAnalyticsViewSet` (courses-by-category) — all role-scoped [26 Mar] |
| 5 | Module Bulk Reorder | `ModuleBulkReorderSerializer` + `reorder` action in `ModuleViewSet` with `bulk_update` + `transaction.atomic()` [27 Mar] |
| 18 | Analytics Endpoints | `LearningAnalyticsViewSet`, `PaymentAnalyticsViewSet`, `CatalogueAnalyticsViewSet` — enrollment-trends, learning-stats, revenue, courses-by-category [26 Mar] |
| 19 | Certificate Auto-Creation | Added `post_save` signal on Enrollment to auto-create Certificate when completed. Added `latest` action and public `verify` to `CertificateViewSet`. [27 Mar] |

---

## MEDIUM — Incomplete Serializers & Models

### 1. AssignmentCreateUpdateSerializer — Missing `update()` Method

**File:** `apps/catalogue/serializers.py`

**Status:** Has `create()` and `validate()` but no `update()` method. PUT/PATCH on assignments won't work correctly without it.

**Fix:** Add `update()` to handle fields like `instructions`, `max_points`, `due_date`, `rubric_criteria`, `allowed_file_types`, etc.

---

### 2. Quiz Model — Missing Fields

**File:** `apps/catalogue/models.py`

**Current Quiz model** has: `session` (OneToOne), `settings` (JSONField), timestamps. Quiz settings are stored in the `settings` JSON field.

**What's still missing:**
- `QuizQuestion` is missing:
  - `explanation` (TextField, blank=True) — text shown after answering, explaining the correct answer
- Consider promoting frequently-queried settings from JSON to model fields for DB-level filtering:
  - `time_limit_minutes` (PositiveIntegerField, null=True)
  - `randomize_questions` (BooleanField, default=False)

**Severity:** MEDIUM for `explanation` field, LOW for promoting JSON fields.

---

### 3. Assignment Model — Minor Gap

**File:** `apps/catalogue/models.py`

**Only missing:**
- `file_upload_required` (BooleanField, default=True) — frontend infers this from `allowed_file_types` being non-empty, but an explicit flag would be cleaner.

**Severity:** LOW.

---

## MEDIUM — Incomplete Views & Actions

### ~~4. DiscussionViewSet — Moderation~~ ✅ COMPLETED [26 Mar]

**File:** `apps/learning/views.py`

**Implemented:**
- `POST /api/v1/learning/discussions/{id}/pin/` — toggles `is_pinned`, Instructor/Manager/Admin only
- `POST /api/v1/learning/discussions/{id}/lock/` — toggles `is_locked`, Instructor/Manager/Admin only
- Query params `?course=`, `?session=`, `?search=` added to `get_queryset()`
- `DiscussionReplyCreateSerializer.validate()` blocks replies on locked discussions
- **Frontend wired:** `discussionApi.pin()`/`lock()` in `learning.services.ts`, Pin/Lock UI in `CoursePlayerPage.tsx`

---

### ~~5. ModuleViewSet — Bulk Reorder~~ ✅ COMPLETED [27 Mar]

**File:** `apps/catalogue/views.py`

**Implemented:**
- `ModuleReorderItemSerializer` + `ModuleBulkReorderSerializer` in `apps/catalogue/serializers.py`
- `@action(detail=False, methods=['post'])` `reorder` method on `ModuleViewSet`
- Validates course ownership for instructors, verifies all module IDs belong to the specified course
- Uses `transaction.atomic()` + `Module.objects.bulk_update(modules, ['order'])` for efficiency
- **Frontend wired:** `moduleApi.reorder()` in `catalogue.services.ts`, `useReorderModules` hook in `useCatalogue.ts`, `CourseStructurePage.tsx` uses single bulk POST instead of N individual PATCHes

```
POST /api/v1/catalogue/modules/reorder/
```
Request:
```json
{
  "course": 5,
  "order": [
    { "id": 10, "order": 0 },
    { "id": 11, "order": 1 },
    { "id": 12, "order": 2 }
  ]
}
```
Response: `{ "updated": 3 }`

---

### 6. SessionViewSet — Gaps

**File:** `apps/catalogue/views.py`

**a) Quiz creation via API:**
Currently `/sessions/{id}/quiz/` only supports GET and PATCH. Add POST to create a new Quiz for a session:
```
POST /api/v1/catalogue/sessions/{id}/quiz/
```
Request:
```json
{
  "settings": {
    "time_limit_minutes": 30,
    "passing_score_percent": 70,
    "max_attempts": 3,
    "shuffle_questions": true
  }
}
```
Response: `QuizDetailResponse` (session + settings + empty questions array)

**b) Assignment creation via API:**
Same pattern — add POST to `/sessions/{id}/assignment/`:
```
POST /api/v1/catalogue/sessions/{id}/assignment/
```
Request:
```json
{
  "assignment_type": "project",
  "instructions": "Build a REST API...",
  "max_points": 100,
  "due_date": "2026-04-01T23:59:00Z",
  "allowed_file_types": [".pdf", ".zip", ".py"],
  "max_file_size_mb": 50
}
```

**c) Session preview for non-enrolled users:** Add a `preview` action returning limited session data (title, description, duration) without content URLs.

---

### ~~7. SubmissionViewSet — Remaining Enhancements~~ ✅ COMPLETED [26 Mar]

**File:** `apps/learning/views.py`, `apps/learning/serializers.py`, `apps/learning/models.py`

**Implemented:**
- `attempt_number` field added to `Submission` model, `unique_together` updated to `(enrollment, assignment, attempt_number)`
- `SubmissionCreateSerializer.validate()` enforces `Assignment.max_attempts` limits
- File extension validation against `Assignment.allowed_file_types` in both Create and Update serializers
- Migration generated: `0005_alter_submission_unique_together_and_more.py`
- `attempt_number` exposed in `SubmissionSerializer` read fields
- **Frontend wired:** Backend validation errors parsed and displayed in `LearnerAssignmentsPage.tsx` toast messages

---

## HIGH — Missing Endpoints (Frontend Blocked)

### ~~18. Analytics Aggregation Endpoints~~ ✅ COMPLETED [26 Mar]

**Implemented:**
- `LearningAnalyticsViewSet` — `/api/v1/learning/analytics/enrollment-trends/` and `/learning-stats/`
- `PaymentAnalyticsViewSet` — `/api/v1/payments/analytics/revenue/`
- `CatalogueAnalyticsViewSet` — `/api/v1/catalogue/analytics/courses-by-category/`
- All endpoints are role-scoped (instructors see their courses only, managers see their org, superadmin sees all)
- **Frontend wired:** `useEnrollmentTrends`, `useLearningStats`, `useCoursesByCategory`, `useRevenueTrends` hooks power Manager, Instructor, Finance, and Superadmin analytics pages

**Frontend blocking:** ~~Manager dashboard charts (a, b, d), Instructor analytics (a, b), Finance analytics (c), Superadmin analytics (a, b, c, d)~~ All unblocked.

---

### 32. Superadmin All Courses — Stats Action (Minor)

**Why:** `AllCoursesPage` displays KPIs (total, published, draft, archived) and a courses table — all hardcoded.

**Already exists:** `CourseViewSet` at `/api/v1/catalogue/courses/` supports list with `status` filter. Frontend can use this for the table.

**Still needed:** Add a `stats` action to `CourseViewSet` (or a new superadmin course view) for efficient KPI counts:
```
GET /api/v1/catalogue/courses/stats/
```
Response:
```json
{
  "total": 876,
  "published": 654,
  "draft": 178,
  "archived": 44
}
```
- One query: `Course.objects.values('status').annotate(count=Count('id'))`
- Without this, frontend must fetch all courses just to count statuses

**Frontend can wire now:** Table → `courseApi.getAll({ status, search, page_size })` (existing endpoint)
**Frontend needs backend for:** KPI stats only

**Frontend blocking:** SuperadminAllCoursesPage (partial — table can be wired now)

---

### 33. Superadmin Assessments — List & Stats Endpoint

**Why:** `AssessmentsPage` shows assessment KPIs and a table of quizzes/assignments — all hardcoded.

**Endpoints needed:**

**a) Assessment stats:**
```
GET /api/v1/superadmin/assessments/stats/
```
Response:
```json
{
  "total": 892,
  "pass_rate": 78.5,
  "active": 34,
  "total_attempts": 24567
}
```
- Aggregate from `Quiz` + `Assignment` counts, `QuizSubmission` pass rates

**b) Assessment list:**
```
GET /api/v1/superadmin/assessments/?type=quiz&status=active&page_size=20
```
- Combine quizzes and assignments into a unified list with type, course name, question count, avg score

**Frontend blocking:** SuperadminAssessmentsPage

---

### 34. Superadmin Certifications — Stats Action (Minor)

**Why:** `CertificationsPage` shows certification KPIs (issued, valid, expired, revoked) and a certs table — all hardcoded.

**Already exists:** `CertificateViewSet` at `/api/v1/learning/certificates/` has list + retrieve + verify. Currently scoped to current user's certificates.

**Still needed:**
- Add superadmin-scoped certificate list (all users' certs, not just mine) — either a new superadmin ViewSet or a role check in existing one
- Add a `stats` action for KPI counts
- Optionally add `status` filter if Certificate model has status field

**Frontend can wire now:** Nothing — current endpoint is user-scoped only
**Frontend needs backend for:** Admin-scoped list + stats

**Frontend blocking:** SuperadminCertificationsPage (depends on #19 Certificate PDF Generation too)

---

### 35. Superadmin Instructors — List & Stats Endpoint

**Why:** `InstructorsPage` shows instructor KPIs and a table — all hardcoded.

**Endpoints needed:**

**a) Instructor stats:**
```
GET /api/v1/superadmin/instructors/stats/
```
Response:
```json
{
  "total": 156,
  "active": 142,
  "avg_rating": 4.6,
  "total_courses": 876
}
```
- Filter `User.objects.filter(role='instructor')`, annotate with `course_count`, `avg_rating`

**b) Instructor list (may reuse existing users endpoint with `?role=instructor`):**
```
GET /api/v1/superadmin/users/?role=instructor&page_size=20
```
- Needs annotated fields: `courses_count`, `students_count`, `avg_rating`

**Frontend blocking:** SuperadminInstructorsPage

---

### 36. Superadmin Invoices — Stats Action (Minor)

**Why:** `InvoicesPage` shows invoice KPIs ($1.8M paid, $234K pending, $45K overdue) and invoice table — all hardcoded.

**Already exists:** `InvoiceViewSet` at `/api/v1/payments/invoices/` has full CRUD with `status`, `from_date`, `to_date` filters. Finance users already see all invoices.

**Still needed:** Add a `stats` action to `InvoiceViewSet`:
```
GET /api/v1/payments/invoices/stats/
```
- One query: aggregate `Sum('amount')` grouped by status

**Frontend can wire now:** Table → `invoiceApi.getAll({ status, page_size })` (existing endpoint)
**Frontend needs backend for:** KPI stats only

**Frontend blocking:** SuperadminInvoicesPage (partial — table can be wired now)

---

### 37. Superadmin Revenue — Org Revenue Breakdown

**Why:** `RevenuePage` shows revenue KPIs and per-organization revenue breakdown — all hardcoded.

**Endpoints needed:**

**a) Revenue stats:**
```
GET /api/v1/superadmin/revenue/stats/
```
Response:
```json
{
  "total_revenue": "2400000.00",
  "monthly_revenue": "186000.00",
  "avg_per_org": "16900.00",
  "growth_percent": 12.5
}
```

**b) Revenue by organization:**
```
GET /api/v1/superadmin/revenue/by-organization/
```
Response:
```json
[
  { "org_name": "TechCorp", "course_revenue": "45000.00", "subscription_revenue": "12000.00", "trend": 8.5 }
]
```
- Aggregate from `Transaction` joined to `Organization`

**Frontend blocking:** SuperadminRevenuePage

---

### 38. Superadmin System Settings & Health

**Why:** `SystemSettingsPage` has hardcoded defaults (site name, URL, timezone, SMTP config, feature toggles, system version). `SystemHealth` component shows hardcoded health checks.

**Endpoints needed:**

**a) System settings CRUD:**
```
GET  /api/v1/superadmin/settings/
PUT  /api/v1/superadmin/settings/
```
- Store as key-value pairs or a JSON blob in a `SystemSettings` singleton model

**b) System health:**
```
GET /api/v1/superadmin/system/health/
```
Response:
```json
{
  "database": "healthy",
  "storage": "online",
  "cpu_usage": "78%",
  "api_latency_ms": 142,
  "uptime_percent": 99.97
}
```

**c) SMTP test:**
```
POST /api/v1/superadmin/settings/test-email/
```

**Frontend blocking:** SuperadminSystemSettingsPage, SystemHealth dashboard widget

**Severity:** LOW — acceptable as configuration for now

---

### 39. ~~Superadmin Notifications~~ — COVERED BY EXISTING ENDPOINTS

**Already exists:** `NotificationViewSet` at `/api/v1/notifications/` has list (with `is_read`, `type` filters) + `unread_count` action + `mark_all_read`.

**No backend work needed.** Frontend should:
- Wire list to `notificationApi.getAll()`
- Wire unread count to `notificationApi.getUnreadCount()`
- Compute "today" / "this week" counts client-side from notification `created_at` timestamps

**Frontend blocking:** SuperadminNotificationsPage (#74) — frontend-only task

---

### 40. Superadmin Roles — User Counts (Minor Enhancement)

**Why:** `RolesPermissionsPage` displays roles with user counts — currently hardcoded.

**Already exists:** `UserSuperadminViewSet.stats()` returns `{ total, active, new_this_month, suspended }`. Users list supports `?role=` filter.

**Still needed:** Add per-role breakdown to existing stats endpoint or add a `roles` action:
```
GET /api/v1/superadmin/users/stats/
```
Enhanced response (add `by_role` field):
```json
{
  "total": 500,
  "active": 480,
  "new_this_month": 15,
  "suspended": 5,
  "by_role": [
    { "role": "tasc_admin", "count": 2 },
    { "role": "lms_manager", "count": 32 },
    { "role": "instructor", "count": 156 },
    { "role": "learner", "count": 305 },
    { "role": "finance", "count": 5 }
  ]
}
```
- One additional query: `User.objects.values('role').annotate(count=Count('id'))`

**Permission matrix:** Keep as frontend config (no backend needed).

**Frontend blocking:** SuperadminRolesPermissionsPage (#72) — minor backend enhancement

**Severity:** LOW

---

### 41. Superadmin Partnerships & Integrations

**Why:** `PartnershipsPage` (6 mock partners) and `IntegrationsPage` (10 mock integrations) are entirely hardcoded.

**Severity:** LOW — these are likely Phase 2 features. No models or infrastructure exist.

**When needed:** Create `Partnership` and `Integration` models with CRUD endpoints. For now, frontend should show "Coming Soon" or keep static display.

**Frontend blocking:** SuperadminPartnershipsPage, SuperadminIntegrationsPage

---

### 43. Manager Organization Settings CRUD

**Why:** `ManagerSettingsPage` has hardcoded org name, industry, website, theme settings, and toggles. No backend endpoint to read or save these.

**Endpoints needed:**
```
GET  /api/v1/manager/settings/
PUT  /api/v1/manager/settings/
```
- Store as JSON on the `Organization` model (add a `settings` JSONField) or a separate `OrganizationSettings` model
- Permission: `IsLmsManager` — scoped to `request.user.organization`
- Fields: `org_name`, `industry`, `website_url`, `primary_color`, `theme_mode`, `default_language`, `notification_toggles`, `retention_period`

**Frontend blocking:** ManagerSettingsPage (#85)

---

### 44. Manager Organization Billing / Subscription Info

**Why:** `ManagerBillingPage` shows hardcoded plan ("Enterprise $499/mo"), usage stats (users/storage/courses), and payment method. Invoices are wired but plan/usage are static.

**Endpoints needed:**

**a) Org subscription/plan details:**
```
GET /api/v1/manager/billing/plan/
```
Response:
```json
{
  "plan_name": "Enterprise",
  "price": "499.00",
  "billing_cycle": "monthly",
  "renewal_date": "2026-04-15",
  "user_limit": 500,
  "storage_limit_gb": 100,
  "courses_limit": null
}
```

**b) Org usage stats:**
```
GET /api/v1/manager/billing/usage/
```
Response:
```json
{
  "active_users": 347,
  "storage_used_gb": 42,
  "active_courses": 156
}
```
- Count users in org, calculate storage from uploads, count published courses

**Frontend blocking:** ManagerBillingPage (#84)

**Severity:** MEDIUM — useful for org admins, but not critical for testing

---

### 45. Manager Activity Log — Mostly Covered by Existing Endpoints

**Already exists:** `AuditLogListView` at `/api/v1/superadmin/audit-logs/` supports `search`, `from`/`to` date range, `action`, `resource` filters. **Managers already have access** — role-based check grants `lms_manager` full read access.

**Also exists:** `NotificationViewSet` at `/api/v1/notifications/` can serve as activity feed.

**Still needed (optional):** A summary stats action on the audit log for quick KPI counts:
```
GET /api/v1/superadmin/audit-logs/summary/?period=today
```
Response:
```json
{ "logins": 145, "enrollments": 23, "completions": 18, "submissions": 31 }
```
- Aggregate `AuditLog.objects.filter(created_at__date=today).values('action').annotate(count=Count('id'))`

**Frontend can wire now:** Activity list → audit log API. The summary stats could be computed client-side from filtered results if volume is low.

**Frontend blocking:** ManagerActivityPage (#83) — mostly frontend-only, summary stats are nice-to-have

---


---

### 42. Superadmin Data Migration & Gateway Settings

**Why:** `DataMigrationPage` (Odoo migration UI) and `GatewaySettingsPage` (payment gateway config) are entirely hardcoded with mock progress data and default config values.

**Severity:** LOW — specialized admin tools, not needed for testing.

**Frontend blocking:** SuperadminDataMigrationPage, SuperadminGatewaySettingsPage

---

### ~~19. Certificate PDF Generation~~ ✅ COMPLETED [27 Mar]

**Why:** `Certificate` model exists but was never auto-populated. Frontend certificates page relied on mock data.

**Implemented:**
- **Auto-Creation:** Hooked `Enrollment.post_save` signal in `apps/learning/signals.py` to auto-create a `Certificate` when `status == 'completed'`.
- **Validation:** Auto-generates `certificate_number`, sets 1-year `expiry_date`, and populates `verification_url` pointing to the public frontend verifier.
- **ViewSet Enhancements:** Added `@action(detail=False) latest` to fetch the most recent certificate for dashboards, and made the `verify` action public via `AllowAny`.
- **Frontend Wired:** Removed mock data in `LearnerCertificatesPage.tsx`; it now correctly lists and renders auto-generated certificates.
- **Note on PDFs:** Elected *not* to pursue server-side PDF generation (WeasyPrint/ReportLab) since the frontend's CSS-based `@media print` A4 landscape template works perfectly via `window.print()` and preserves the exact intended design.

**Frontend blocking:** ~~LearnerCertificatesPage (#8, #50)~~ Unblocked.

---

### 20. Bulk Enrollment Endpoint

**Why:** `ManagerBulkEnrollPage` needs to enroll multiple users into a course at once. Currently no bulk endpoint exists.

**Endpoint:**
```
POST /api/v1/manager/enrollments/bulk/
```
Request:
```json
{
  "course": 5,
  "user_ids": [12, 15, 18, 22, 31]
}
```
Response:
```json
{
  "enrolled": 4,
  "already_enrolled": 1,
  "failed": 0,
  "errors": []
}
```
- Permission: `IsLmsManager` — auto-scope to manager's organization users only
- Use `transaction.atomic()` and `bulk_create()` with `ignore_conflicts=True`

**Frontend blocking:** ManagerBulkEnrollPage (#20)

---

### 21. Session Attachments / Resources Endpoint

**Why:** CoursePlayerPage has a "Resources" tab that currently uses `sampleResources[]` hardcoded data. There's no backend support for attaching downloadable files to lessons/sessions.

**Model:**
```python
class SessionAttachment(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='attachments')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='session_attachments/')
    file_type = models.CharField(max_length=50)  # pdf, zip, code, etc.
    file_size = models.PositiveIntegerField()  # bytes
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Endpoints:**
```
GET  /api/v1/catalogue/sessions/{id}/attachments/   — list resources for a session
POST /api/v1/catalogue/sessions/{id}/attachments/   — upload (instructor/manager only)
DELETE /api/v1/catalogue/sessions/{id}/attachments/{attachment_id}/
```

**Frontend blocking:** CoursePlayerPage Resources tab (#10)

---

### 22. Security Metrics Endpoint

**Why:** Superadmin `SecurityPage` displays active sessions, login attempts, and security KPIs — all currently hardcoded.

**Endpoints:**

**a) Active sessions:**
```
GET /api/v1/superadmin/security/sessions/
```
Response:
```json
[
  {
    "user": { "id": 5, "email": "user@example.com", "full_name": "John Doe" },
    "ip_address": "192.168.1.1",
    "user_agent": "Chrome/120",
    "last_activity": "2026-03-22T10:30:00Z",
    "created_at": "2026-03-22T08:00:00Z"
  }
]
```
- Derive from Django sessions or a custom `UserSession` model tracking login/activity

**b) Security stats:**
```
GET /api/v1/superadmin/security/stats/
```
Response:
```json
{
  "active_sessions": 42,
  "failed_logins_today": 7,
  "locked_accounts": 2,
  "mfa_adoption_percent": 35
}
```
- `failed_logins_today`: count users where `failed_login_attempts > 0` and last attempt is today
- `locked_accounts`: count users where `account_locked_until > now()`

**Frontend blocking:** SecurityPage (#26)

---

### 23. B2B / Organization Pricing Tiers

**Why:** The `/for-business` page displays 3 hardcoded B2B pricing tiers (Team $15, Business $20, Enterprise $25). Current `Subscription` model is learner-focused.

**Options:**
- Add `tier_type` field to `Subscription` (`individual` vs `organization`) and create org plans via admin
- Or create a separate `OrganizationPlan` model with `max_seats`, `price_per_seat`, etc.

**Endpoint:**
```
GET /api/v1/public/business-plans/
```
Response:
```json
[
  { "name": "Team", "price_per_seat": "15.00", "max_seats": 25, "billing_cycle": "monthly", "features": [...] },
  { "name": "Business", "price_per_seat": "20.00", "max_seats": 100, "billing_cycle": "monthly", "features": [...] },
  { "name": "Enterprise", "price_per_seat": "25.00", "max_seats": null, "billing_cycle": "monthly", "features": [...] }
]
```

**Frontend blocking:** PricingSection (#34)

**Severity:** LOW — acceptable as hardcoded marketing content for now.



---

### 28. Badges System (Completion Badges)

**Why:** User story: *"As a Learner, I want to receive completion badges so that I feel motivated to finish courses."* (userStories.md line 55). Frontend team will build the badges page, confetti modal, and display — backend needs to provide the models, auto-award logic, and API endpoints.

**Models:**
```python
class Badge(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    icon_url = models.URLField()  # S3 URL to badge PNG
    category = models.CharField(max_length=50, choices=[
        ('course_completion', 'Course Completion'),
        ('enrollment', 'Enrollment Milestones'),
        ('subscription', 'Subscription Loyalty'),
        ('assessment', 'Assessment Excellence'),
        ('engagement', 'Engagement'),
        ('milestone', 'Milestones'),
    ])
    criteria_type = models.CharField(max_length=50)  # e.g., 'certificates_count', 'quiz_perfect_score'
    criteria_value = models.IntegerField(default=1)   # e.g., 5 (for "complete 5 courses")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'order']

class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='earned_badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='earners')
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'badge']
        indexes = [models.Index(fields=['user', '-earned_at'])]
```

**Endpoints:**
```
GET  /api/v1/learning/badges/          — all badge definitions (public, cacheable)
GET  /api/v1/learning/my-badges/       — current user's earned badges with earned_at
POST /api/v1/learning/badges/check/    — trigger badge evaluation for current user (returns newly earned)
```

**Response — `GET /api/v1/learning/badges/`:**
```json
[
  {
    "id": 1,
    "slug": "first-course",
    "name": "First Steps",
    "description": "Completed your first course",
    "icon_url": "https://cdn.../badges/first-course.png",
    "category": "course_completion",
    "criteria_type": "certificates_count",
    "criteria_value": 1
  }
]
```

**Response — `GET /api/v1/learning/my-badges/`:**
```json
[
  {
    "badge": { "id": 1, "slug": "first-course", "name": "First Steps", ... },
    "earned_at": "2026-03-15T10:30:00Z"
  }
]
```

**Response — `POST /api/v1/learning/badges/check/`:**
```json
{
  "newly_earned": [
    { "badge": { ... }, "earned_at": "2026-03-22T14:00:00Z" }
  ]
}
```

**Auto-award logic** — use Django signals or a shared `check_and_award_badges(user)` function called from:
- `Certificate` post_save signal → check course completion badges
- `Enrollment` post_save signal → check enrollment badges
- `QuizSubmission` post_save signal → check assessment badges
- `Discussion` post_save signal → check engagement badges
- `UserSubscription` post_save signal → check subscription badges

**Badge criteria mapping** (22 badges total, see `TASC-LMS-frontend/src/config/badges.md` for full list):

| criteria_type | criteria_value | Badges |
|---------------|---------------|--------|
| `certificates_count` | 1, 3, 5, 10, 20 | First Steps, Knowledge Seeker, Dedicated Learner, Knowledge Master, Scholar |
| `enrollments_count` | 1, 5, 10 | Early Bird, Curious Mind, Course Explorer |
| `subscriptions_count` | 1, 3, 5 | Supporter, Loyal Learner, Platinum Member |
| `quiz_submissions_count` | 1 | Quiz Taker |
| `quiz_perfect_score` | 1 | Perfect Score (any quiz with score=100%) |
| `quiz_pass_streak` | 5 | Quiz Streak |
| `assignment_full_marks` | 1 | Assignment Ace |
| `discussions_count` | 1, 10 | Conversation Starter, Community Voice |
| `reviews_count` | 1 | Reviewer |
| `profile_complete` | 1 | Identity (avatar + bio + phone filled) |
| `first_certificate` | 1 | Certified |

**Seed data:** Create a management command `python manage.py seed_badges` that creates all 22 badge records.

**Frontend blocking:** LearnerBadgesPage (new page, sidebar link already exists), badge earned confetti modal

---

### 29. Saved / Favorited Courses API

**Why:** The frontend has a "Saved Courses" page (`/learner/saved`) and heart icon toggles on the course catalog (`CatalogCourseCard.tsx`), but there is no backend persistence. Favorites are currently stored in React component state only — lost on page refresh. No model, no API, no localStorage fallback.

**Model:**
```python
class SavedCourse(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_courses')
    course = models.ForeignKey('catalogue.Course', on_delete=models.CASCADE, related_name='saved_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'course']
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]
```

**Endpoints:**
```
GET    /api/v1/learning/saved-courses/          — list user's saved courses (paginated)
POST   /api/v1/learning/saved-courses/          — save a course
DELETE /api/v1/learning/saved-courses/{id}/      — unsave a course
```

**Alternative toggle endpoint (simpler for frontend):**
```
POST   /api/v1/learning/saved-courses/toggle/   — toggle save/unsave by course ID
```
Request:
```json
{ "course": 5 }
```
Response:
```json
{ "saved": true }   // or { "saved": false } if it was unsaved
```

**Response — `GET /api/v1/learning/saved-courses/`:**
```json
{
  "count": 3,
  "results": [
    {
      "id": 1,
      "course": {
        "id": 5,
        "title": "Advanced React Patterns",
        "slug": "advanced-react-patterns",
        "thumbnail": "https://cdn.../thumb.jpg",
        "category": { "id": 2, "name": "Web Development" },
        "instructor_name": "Michael Rodriguez",
        "rating": 4.8,
        "review_count": 42,
        "session_count": 12,
        "difficulty_level": "advanced",
        "is_published": true
      },
      "created_at": "2026-03-20T14:30:00Z"
    }
  ]
}
```

**Serializer notes:**
- Use `select_related('course', 'course__category', 'course__instructor')` to avoid N+1
- Nest a read-only `CourseListSerializer` for the course field
- Permission: `IsAuthenticated` (any logged-in user can save courses)

**ViewSet:**
```python
class SavedCourseViewSet(viewsets.ModelViewSet):
    serializer_class = SavedCourseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedCourse.objects.filter(user=self.request.user) \
            .select_related('course', 'course__category', 'course__instructor')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        course_id = request.data.get('course')
        obj, created = SavedCourse.objects.get_or_create(
            user=request.user, course_id=course_id
        )
        if not created:
            obj.delete()
        return Response({'saved': created})
```

**Migration:** New migration in `apps/learning/` for `SavedCourse` model.

**Frontend impact:** Once ready, wire:
1. `SavedCoursesPage.tsx` — replace 6 mock courses with `GET /api/v1/learning/saved-courses/`
2. `LearnerCourseCatalogPage.tsx` — replace React state favorites with `POST .../toggle/`
3. `CatalogCourseCard.tsx` — `isFavorite` prop fed from API response instead of local state
4. Add `savedCourseApi` to `learning.services.ts`

**Frontend blocking:** SavedCoursesPage (mock data), CatalogCourseCard heart toggle (not persisted)

---

### 30. CourseViewSet — Add Ordering Support (for Top Courses widget)

**Why:** The Manager dashboard `TopCourses` widget needs to fetch courses sorted by popularity (`enrollment_count`). The `CourseListSerializer` already exposes `enrollment_count`, but the `CourseViewSet` has no `filter_backends` or `ordering_fields` configured — so `?ordering=-enrollment_count` doesn't work. Courses come back in default order.

**File:** `apps/catalogue/views.py` — `CourseViewSet`

**What to do:**
```python
from rest_framework.filters import OrderingFilter, SearchFilter

class CourseViewSet(viewsets.ModelViewSet):
    filter_backends = [OrderingFilter, SearchFilter]
    ordering_fields = ['title', 'published_at', 'enrollment_count', 'created_at']
    ordering = ['-created_at']  # default
    search_fields = ['title', 'short_description']
    # ... rest of viewset
```

**Impact:** Enables `?ordering=-enrollment_count&page_size=4` for top courses by popularity. Also enables search.

**Frontend blocking:** Manager TopCourses widget currently fetches first 4 courses in default order instead of most-enrolled.

---

### 31. Organization Serializer — Add `user_count` and `course_count` Annotations

**Why:** The Superadmin dashboard `OrganizationsTable` widget shows user count and course count per org, but the `OrganizationSerializer` doesn't expose these fields. The serializer returns `name`, `is_active`, `contact_email`, etc. but no aggregated counts.

**File:** `apps/accounts/serializers_superadmin.py` — `OrganizationSerializer`

**What to do:**

**a) Add annotated fields to the serializer:**
```python
class OrganizationSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)
    course_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = [..., 'user_count', 'course_count']
```

**b) Annotate the queryset in the view:**
```python
from django.db.models import Count, Q

class OrganizationViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return Organization.objects.annotate(
            user_count=Count('memberships', distinct=True),
            course_count=Count(
                'courses',  # or through membership → user → courses
                filter=Q(courses__status='published'),
                distinct=True
            ),
        )
```

**Note:** The exact reverse relation names depend on how `Membership` and `Course` relate to `Organization`. Check the model for the correct `related_name`.

**Impact:** Superadmin OrganizationsTable will show real user/course counts instead of empty columns.

**Frontend blocking:** OrganizationsTable widget references `org.user_count` and `org.course_count` which are currently `undefined`.

---

## LOW — Remaining Services & Templates

### 8. Email Templates

**File:** `config/settings.py`

**Current:** Console backend in dev, SendGrid configured for prod. `templates/emails/` directory does not exist.

**Templates to create:**

| Template | Trigger | Key variables |
|---|---|---|
| `verification.html` | User registration | `user_name`, `verification_url` |
| `password_reset.html` | Password reset request | `user_name`, `reset_url`, `expiry_hours` |
| `enrollment_confirmation.html` | Successful enrollment | `user_name`, `course_title`, `start_date` |
| `certificate_issued.html` | Course completion | `user_name`, `course_title`, `certificate_url` |
| `payment_receipt.html` | Successful payment | `user_name`, `course_title`, `amount`, `currency`, `transaction_id`, `date` |

---

### 9. Notifications ViewSet — Missing Features

**File:** `apps/notifications/views.py`

**Works:** CRUD + `mark_read` + `mark_all_read` + `unread_count` + type filter + is_read filter

**Missing:**
- Date range filter: `?created_after=2026-03-01&created_before=2026-03-17`
- Bulk delete: `POST /notifications/bulk_delete/` with `{ "ids": [1, 2, 3] }`
- Notification preferences: `GET/PUT /notifications/preferences/` → `{ "email_enabled": true, "push_enabled": false, "types": { "enrollment": true, "system": true, "milestone": false } }`

---

## LOW — Silent Exception Handling & Code Quality

### 10. Payment Webhook Handlers — Silent `pass`
- **File:** `apps/payments/utils/webhook_handlers.py` (lines 271, 317)
- **Problem:** `_handle_failed_payment()` and `_handle_refund()` silently ignore `Payment.DoesNotExist`.
- **Fix:** Replace `pass` with `logger.warning(f"Payment not found for transaction {transaction_id}")`.

### 11. Payment Validators — Silent Validation
- **File:** `apps/payments/utils/payment_validators.py` (line 328)
- **Problem:** Invalid phone number silently swallowed.
- **Fix:** Add `logger.info(f"Phone validation skipped for {phone}: {e}")`.


### 13. Audit Views — Date Parsing
- **File:** `apps/audit/views.py` (lines 79, 89)
- **Problem:** Malformed date filters silently ignored — user gets unfiltered results without knowing.
- **Fix:** Return `400 Bad Request` with message: `"Invalid date format for 'date_from'. Expected YYYY-MM-DD."`.

### 14. Catalogue Views — Category Filter
- **File:** `apps/catalogue/views.py` (line 118)
- **Problem:** Non-numeric category ID silently ignored.
- **Fix:** Return `400` or log warning and skip filter.


### 16. StorageQuotaView — Silent S3 Failures
- **File:** `apps/common/views.py` (lines 362-366)
- **Problem:** Two bare `except Exception: pass` blocks when calculating storage usage from S3. If S3 is misconfigured or down, the endpoint silently returns `used_bytes: 0` with no indication of failure.
- **Fix:** Log warnings and optionally return a `storage_error` flag in the response so the frontend can show "unable to calculate" instead of misleading "0 bytes used".

---

## PERFORMANCE — N+1 Query Risks

### 17. ViewSets Missing `select_related`/`prefetch_related`
Several viewsets query models with foreign keys but don't optimize their querysets:
- **`EnrollmentViewSet`** (`apps/learning/views.py`) — **Partially fixed 18 Mar:** `select_related('course', 'course__category')` added on instructor branch + `?role=instructor` and `?course=` filters. Default (learner) branch still lacks `select_related`.
- **`DiscussionViewSet`** (`apps/learning/views.py`) — `Discussion` has FK to `user`, `course`, `session` — no `select_related`
- **`DiscussionReplyViewSet`** (`apps/learning/views.py`) — `DiscussionReply` has FK to `user`, `discussion` — no `select_related`
- **`SubmissionViewSet`** (`apps/learning/views.py`) — `Submission` has FK to `enrollment`, `assignment` — no `select_related`
- **`NotificationViewSet`** (`apps/notifications/views.py`) — no `select_related` at all
- **`InvoiceViewSet`** / **`TransactionViewSet`** (`apps/payments/views.py`) — no `select_related` despite FK to `user`
- **Fix:** Add `.select_related()` for FK fields accessed in serializers and `.prefetch_related()` for reverse relations. This prevents N+1 queries on list endpoints that could degrade performance at scale.

---

## Django Admin Gaps

### 16. Catalogue Admin — Missing Model Registrations
- **File:** `apps/catalogue/admin.py`
- **Registered:** `QuestionCategory`, `BankQuestion`, `Assignment`, `Quiz`, `QuizQuestion`, `Module`
- **NOT registered:** `Course`, `Session`, `Category`, `Tag`
- **Fix:** Add `@admin.register(Course)`, etc. with appropriate `list_display`, `list_filter`, `search_fields`.


---

## TEST COVERAGE GAPS

| App | Current Tests | Major Gaps |
|---|---|---|
| `learning` | 27 tests | Quiz submission tests missing, report generation not tested |
| `catalogue` | 95 tests | Quiz creation/update minimal, assignment tests basic, course review tests missing |
| `payments` | 8 tests | Webhook handlers not tested |
| `accounts` | 48 tests | CSV bulk import not tested (now implemented — needs tests) |
| `audit` | 6 tests | Minimal |
| `notifications` | 2 tests | Only email provider routing tested; CRUD and mark_read not tested |
| `livestream` | **5 tests** | Fully covered |

---

## CRITICAL — Infrastructure for 1000 Concurrent Users

> **Why this section exists:** A scalability audit identified that the application code is solid, but infrastructure configuration has gaps that would cause failures under production load (1000+ concurrent users). These are config changes, not code rewrites.

### 25. Redis Integration (Caching + Celery Broker)

**Why:** Currently there is no caching layer at all — every request hits the database, including session lookups. Celery uses `"django://"` (database) as its broker, meaning the task queue competes with application queries on the same PostgreSQL instance. Under load, this becomes the primary bottleneck.

**What to do:**

**a) Install and configure Redis:**
- Add `redis` and `django-redis` to `requirements.txt`
- Add to `config/settings.py`:
```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
```

**b) Switch Celery to Redis broker:**
```python
CELERY_BROKER_URL = "redis://redis:6379/1"
CELERY_RESULT_BACKEND = "redis://redis:6379/2"
```
Currently set to `"django://"` and `"django-db"` (lines 375-377 in settings.py).

**c) Add Redis to docker-compose:**
```yaml
redis:
  image: redis:7-alpine
  restart: unless-stopped
  ports:
    - "127.0.0.1:6379:6379"
```

**Impact:** Eliminates DB as bottleneck for sessions, caching, and async tasks.

---

### 26. Database Connection Pooling

**Why:** Without connection pooling, each request opens a new PostgreSQL connection and closes it when done. At 1000 concurrent users, this exhausts PostgreSQL's default `max_connections` (100) and causes connection refused errors. `psycopg-pool` is already in `requirements.txt` (line 65) but is not configured.

**What to do:**

Add to `DATABASES` config in `config/settings.py`:
```python
DATABASES = {
    "default": {
        # ... existing ENGINE, NAME, USER, PASSWORD, HOST, PORT ...
        "CONN_MAX_AGE": 600,          # Keep connections alive for 10 min
        "OPTIONS": {
            "pool": {
                "min_size": 5,
                "max_size": 20,
            }
        }
    }
}
```

`CONN_MAX_AGE=600` alone gives a significant improvement. The `pool` option requires `psycopg[pool]` (psycopg v3) — verify the current psycopg version supports it, otherwise use `django-db-connection-pool`.

**Impact:** Reduces connection overhead from ~5ms/request to near-zero; prevents connection exhaustion.

---

### 27. Gunicorn Worker Scaling

**Why:** The Dockerfile hardcodes `--workers 3`. Each gunicorn worker handles one request at a time (sync). With 3 workers, only 3 requests can be processed simultaneously — at 1000 concurrent users, requests queue up and timeout.

**Current config** (`Dockerfile` line 24 and `docker-compose.staging.yml` line 41):
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

**What to change:**
```bash
gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 8 \
  --threads 4 \
  --worker-class gthread \
  --timeout 120 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

- `--workers 8`: Rule of thumb is `(2 × CPU cores) + 1`. 8 workers handles ~1200 req/sec.
- `--threads 4`: Each worker handles 4 concurrent requests (32 total slots).
- `--worker-class gthread`: Threaded workers for I/O-bound Django views.
- `--max-requests 1000`: Recycle workers to prevent memory leaks.

**Alternative:** Use `--worker-class gevent` with `--worker-connections 1000` for even higher concurrency (requires `pip install gevent`).

**Impact:** Increases concurrent request capacity from 3 to 32 (or 1000+ with gevent).

---

## Configuration TODOs

- Set `ZOOM_WEBHOOK_SECRET` in production settings
- Configure Google Meet: `GOOGLE_MEET_SERVICE_ACCOUNT_FILE`, `GOOGLE_MEET_DELEGATED_USER`, `GOOGLE_MEET_CALENDAR_ID` (code is ready, just needs credentials)
- Configure Teams: `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`, `TEAMS_CLIENT_SECRET`, `TEAMS_ORGANIZER_USER_ID` (code is ready, just needs Azure AD app registration)
- Set up SendGrid email templates for production
