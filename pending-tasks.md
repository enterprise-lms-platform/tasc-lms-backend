# TASC LMS Backend — Pending Tasks

**Last updated:** 19 March 2026 (post-pull audit)
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

---

## HIGH — Public Course Search

### 0a. Add Search Support to PublicCourseViewSet

**File:** `apps/catalogue/views_public.py`

**Why:** The frontend catalogue page has a search bar but it does nothing — the backend `PublicCourseViewSet` doesn't support text search. DRF's `SearchFilter` is already imported but unused.

**Backend fix:**

Add `SearchFilter` and `OrderingFilter` to `PublicCourseViewSet`:

```python
class PublicCourseViewSet(viewsets.ReadOnlyModelViewSet):
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'short_description', 'description']
    ordering_fields = ['published_at', 'enrollment_count', 'price', 'title']
    ordering = ['-published_at']
```

This enables:
```
GET /api/v1/public/courses/?search=react
GET /api/v1/public/courses/?search=python&category=3&level=beginner
GET /api/v1/public/courses/?ordering=-enrollment_count  (most popular)
```

**Frontend impact:** Once backend is ready:
1. Add `search` param to `PublicCourseParams` in `public.services.ts`
2. Wire `CatalogueHero.onSearch` → state in `CourseCataloguePage` → pass as prop to `CoursesGrid`
3. Pass `search` param in `CoursesGrid` API call (already accepts prop, just not using it)

---

## HIGH — Manager Bulk Import Endpoint

### 0b. Add Manager-Scoped Bulk Import & CSV Template Endpoints

**Why:** Bulk import currently only exists on `UserSuperadminViewSet` (`apps/accounts/views_superadmin.py`) behind `IsTascAdminUser` permission. The frontend `ManagerBulkImportPage` calls these endpoints, but LMS managers can't access them — they get 403. Managers need their own endpoints that auto-scope imported users to their organization.

**Backend changes needed:**

**a) Add `bulk_import` action to the manager's UserViewSet (or create one):**
```
POST /api/v1/manager/users/bulk_import/
```
- Permission: `IsLmsManager` (or equivalent org-manager permission)
- Behaviour: Same CSV parsing logic as superadmin version (`views_superadmin.py` lines 78-211), but:
  - Auto-assign `organization = request.user.organization` to every imported user
  - Only allow roles that a manager can grant (e.g., `learner`, `instructor` — NOT `tasc_admin` or `lms_manager`)
  - Validate that the manager's org hasn't exceeded its user quota (if applicable)
- Response shape must match `BulkImportResult`:
  ```json
  { "created": 5, "total": 8, "successful": 5, "failed": 3, "errors": [{ "row": 2, "message": "..." }] }
  ```

**b) Add `csv_template` action for managers:**
```
GET /api/v1/manager/users/csv_template/
```
- Can reuse the same template as superadmin, or provide a simplified one (without org column since it's auto-assigned)

**c) Refactor shared logic:**
- Extract the CSV parsing/validation from `UserSuperadminViewSet.bulk_import()` into a shared utility (e.g., `apps/accounts/utils/csv_import.py`) so both superadmin and manager views can reuse it without duplication.

**Frontend impact:** Once backend is ready, update `ManagerBulkImportPage` to import from a new `manager.services.ts` bulk import API pointing to `/api/v1/manager/users/...` instead of the superadmin path.

**Also:** Consider adding a superadmin bulk import route in the frontend (`/superadmin/bulk-import`) that reuses the `ManagerBulkImportPage` component — the "Bulk Import" button on `AllUsersPage` currently has no destination page.

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

### 4. DiscussionViewSet — Moderation

**File:** `apps/learning/views.py`

**What works:** Full CRUD + replies. The `Discussion` model already has `is_pinned`, `is_locked`, `is_deleted` boolean fields.

**What's missing — add these as `@action` endpoints:**

**a) Pin/unpin:**
```
POST /api/v1/learning/discussions/{id}/pin/
```
Response: `{ "is_pinned": true }` — toggles pin state. Instructor/manager only.

**b) Lock/unlock:**
```
POST /api/v1/learning/discussions/{id}/lock/
```
Response: `{ "is_locked": true }` — toggles lock state. When locked, no new replies allowed. Instructor/manager only.

**c) Filter by course/session** — add query params to list action:
```
GET /api/v1/learning/discussions/?course=5&session=12&search=networking
```
Currently only basic queryset. Add `course`, `session`, and `search` (title/content) filters.

---

### 5. ModuleViewSet — Bulk Reorder

**File:** `apps/catalogue/views.py`

Currently, reordering requires individual PATCH requests per module. Add a bulk endpoint:

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

Use `transaction.atomic()` and `bulk_update()` for efficiency.

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

### 7. SubmissionViewSet — Remaining Enhancements

**File:** `apps/learning/views.py`

Bulk grade and statistics actions are now implemented. Still missing:

**a) File upload validation:** In `create()`, check `submitted_file_name` extension against `Assignment.allowed_file_types` and file size against `Assignment.max_file_size_mb`.

**b) Resubmission tracking:** Currently allows only one submission per enrollment+assignment. Add `attempt_number` field and allow multiple submissions up to `Assignment.max_attempts`.

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

### 12. Calendar Service — Timezone Silencing
- **File:** `apps/livestream/services/calendar_service.py` (line 57)
- **Problem:** `except Exception: pass` on invalid timezone — events may use wrong timezone silently.
- **Fix:** `logger.warning(f"Invalid timezone {tz}, falling back to UTC")` then set `tz = 'UTC'`.

### 13. Audit Views — Date Parsing
- **File:** `apps/audit/views.py` (lines 79, 89)
- **Problem:** Malformed date filters silently ignored — user gets unfiltered results without knowing.
- **Fix:** Return `400 Bad Request` with message: `"Invalid date format for 'date_from'. Expected YYYY-MM-DD."`.

### 14. Catalogue Views — Category Filter
- **File:** `apps/catalogue/views.py` (line 118)
- **Problem:** Non-numeric category ID silently ignored.
- **Fix:** Return `400` or log warning and skip filter.

### 15. Livestream Webhook Health Check — Misnamed
- **File:** `apps/livestream/views.py`
- **Problem:** `validate_webhook` action returns `{"status": "ok"}` without doing any validation.
- **Fix:** Either rename to `webhook_health` or implement actual webhook signature validation for the configured platform.

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

### 17. Livestream Admin — No admin.py
- `apps/livestream/admin.py` does not exist.
- **Create it** and register: `LivestreamSession`, `LivestreamAttendance`, `LivestreamRecording`, `LivestreamQuestion`
- Example:
```python
@admin.register(LivestreamSession)
class LivestreamSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'platform', 'status', 'scheduled_start', 'created_at')
    list_filter = ('platform', 'status')
    search_fields = ('title',)
```

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
| `livestream` | **0 tests** | **No test file exists** — create `apps/livestream/tests.py` |

**Priority:** Create `apps/livestream/tests.py` with tests for:
- Session CRUD (create, update status, start/end)
- Attendance tracking (mark joined, mark left, duration calculation)
- Zoom webhook handler (mock webhook payloads for each event type)
- LivestreamQuestion CRUD and answer flow

---

## Configuration TODOs

- Set `ZOOM_WEBHOOK_SECRET` in production settings
- Configure Google Meet: `GOOGLE_MEET_SERVICE_ACCOUNT_FILE`, `GOOGLE_MEET_DELEGATED_USER`, `GOOGLE_MEET_CALENDAR_ID` (code is ready, just needs credentials)
- Configure Teams: `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`, `TEAMS_CLIENT_SECRET`, `TEAMS_ORGANIZER_USER_ID` (code is ready, just needs Azure AD app registration)
- Set up SendGrid email templates for production
