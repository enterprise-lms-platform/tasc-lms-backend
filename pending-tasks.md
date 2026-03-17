# TASC LMS Backend — Pending Tasks

**Last updated:** 17 March 2026 (revised with full specs)
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

## CRITICAL — Missing Endpoints & Models

### 1. Quiz Submission System (NEW)

**Status:** Model does not exist. No endpoints. This is the #1 backend gap.

**Context:** The frontend `QuizPlayer.tsx` currently grades quizzes client-side using `answer_payload` on each question. We need server-side grading and persistence.

**Models to create in `apps/learning/models.py`:**

```python
class QuizSubmission(models.Model):
    enrollment = models.ForeignKey('Enrollment', on_delete=models.CASCADE, related_name='quiz_submissions')
    quiz = models.ForeignKey('catalogue.Quiz', on_delete=models.CASCADE, related_name='submissions')
    attempt_number = models.PositiveIntegerField(default=1)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    passed = models.BooleanField(default=False)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

class QuizAnswer(models.Model):
    submission = models.ForeignKey(QuizSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey('catalogue.QuizQuestion', on_delete=models.CASCADE)
    selected_answer = models.JSONField()  # matches the answer_payload structure
    is_correct = models.BooleanField(null=True)  # null = needs manual grading
    points_awarded = models.DecimalField(max_digits=5, decimal_places=2, default=0)
```

**Endpoints to create:**

```
POST /api/v1/learning/quiz-submissions/
```
Request body:
```json
{
  "enrollment": 42,
  "quiz": 7,
  "time_spent_seconds": 324,
  "answers": [
    {
      "question": 101,
      "selected_answer": { "selected_option": 2 }
    },
    {
      "question": 102,
      "selected_answer": { "value": true }
    },
    {
      "question": 103,
      "selected_answer": { "text": "HTTP is a stateless protocol" }
    },
    {
      "question": 104,
      "selected_answer": { "blanks": ["TCP", "UDP"] }
    }
  ]
}
```
Response (201):
```json
{
  "id": 1,
  "enrollment": 42,
  "quiz": 7,
  "attempt_number": 1,
  "score": 85.00,
  "max_score": 100.00,
  "passed": true,
  "time_spent_seconds": 324,
  "submitted_at": "2026-03-17T10:30:00Z",
  "answers": [
    {
      "question": 101,
      "selected_answer": { "selected_option": 2 },
      "is_correct": true,
      "points_awarded": 10.00
    }
  ]
}
```

```
GET /api/v1/learning/quiz-submissions/?quiz=7&enrollment=42
```
Response: paginated list of `QuizSubmission` objects (same shape as above).

**Auto-grading logic** (compare `selected_answer` against `QuizQuestion.answer_payload`):
- `multiple-choice`: `answer_payload.options[selected_option].is_correct === true`
- `true-false`: `selected_answer.value === answer_payload.correct_answer`
- `short-answer`: case-insensitive match against `answer_payload.sample_answer` (or contains check)
- `fill-blank`: each `selected_answer.blanks[i]` matches `answer_payload.blanks[i].answer` (case-insensitive)
- `essay`: set `is_correct = null` (needs manual grading)
- `matching`: compare selected pairs against correct pairs in answer_payload

**Files to create/modify:**
- `apps/learning/models.py` — add models
- `apps/learning/serializers.py` — add `QuizSubmissionSerializer`, `QuizSubmissionCreateSerializer`, `QuizAnswerSerializer`
- `apps/learning/views.py` — add `QuizSubmissionViewSet`
- `apps/learning/urls.py` — register `quiz-submissions` route
- New migration file

**Frontend impact:** `QuizPlayer.tsx` does client-side grading only. Once this exists, the frontend can POST answers and get authoritative scores.

---

### 2. Report Generation — Async Implementation (BLOCKED: No Celery)

**File:** `apps/learning/views.py` (lines 355-358)

**Current behavior:** `generate` action creates a Report, immediately sets `status = READY` with no file attached. The download action then fails because `report.file` is empty.

**Blocker:** There is **zero Celery infrastructure** in the codebase — no `celery.py`, no task files, no Celery imports anywhere. This must be set up first.

**Step 1 — Set up Celery:**
- Create `config/celery.py` with app configuration
- Add `celery_app` to `config/__init__.py`
- Add `CELERY_BROKER_URL` to settings (Redis recommended)
- Install: `pip install celery redis`

**Step 2 — Create report task in `apps/learning/tasks.py`:**

```python
@shared_task
def generate_report(report_id):
    report = Report.objects.get(id=report_id)
    try:
        # Query data based on report.report_type
        # Generate CSV or PDF
        # Upload to storage
        # Update report.file and report.file_size
        report.status = Report.Status.READY
        report.save()
    except Exception as e:
        report.status = Report.Status.FAILED
        report.save()
```

**Step 3 — Implement data queries for each report type:**

The `Report.Type` choices are already defined in `apps/learning/models.py` (line 339):

| report_type | What to query | Expected CSV columns |
|---|---|---|
| `user_activity` | `SessionProgress` + User login timestamps | user_name, email, course, session, time_spent, last_accessed, completion_pct |
| `course_performance` | `Enrollment` + `SessionProgress` aggregated per course | course_name, enrolled_count, completed_count, avg_score, avg_completion_pct |
| `enrollment` | `Enrollment` filtered by date/course/status | learner_name, email, course, enrolled_at, status, completion_pct |
| `completion` | `Enrollment` where status=completed | learner_name, course, completed_at, score, certificate_issued |
| `assessment` | `Submission` + future `QuizSubmission` | learner_name, assessment_title, type, score, max_score, submitted_at, status |
| `revenue` | `Transaction` + `Invoice` from payments app | transaction_id, learner, course, amount, currency, payment_method, date, status |

**Step 4 — Update the `generate` action** (line 355) to call `generate_report.delay(report.id)` instead of immediately setting READY.

**Frontend expects these endpoints (already exist but need real data):**
```
POST /api/v1/learning/reports/          → { report_type: "enrollment", parameters: { date_from: "...", date_to: "..." } }
GET  /api/v1/learning/reports/          → paginated list, filter by ?report_type=...&status=...
GET  /api/v1/learning/reports/{id}/download/  → { download_url: "https://...", file_size: "2.4 MB" }
```

---

### 3. Bulk User Import — CSV Parsing

**File:** `apps/accounts/views_superadmin.py` (lines 77-84)

**Current behavior:** Returns `{"message": "Bulk import started.", "imported": 0}` with no processing.

**Expected CSV format** (from `ManagerBulkImportPage.tsx`):
```csv
full_name,email_address,user_role,department,manager_email
John Doe,john@example.com,Learner,Engineering,jane@example.com
Jane Smith,jane@example.com,Manager,Engineering,
```

**Constraints shown in frontend UI:**
- Max file size: 10 MB
- Max records: 5,000 per file
- Format: `.csv` only

**Endpoint:**
```
POST /api/v1/admin/users/bulk_import/
Content-Type: multipart/form-data
```
Request: `file` field with CSV attachment

Response (200):
```json
{
  "message": "Bulk import completed.",
  "total_rows": 150,
  "imported": 147,
  "failed": 3,
  "errors": [
    { "row": 12, "email": "bad-email", "error": "Invalid email format" },
    { "row": 45, "email": "duplicate@example.com", "error": "User already exists" },
    { "row": 89, "email": "no-role@example.com", "error": "Invalid role: 'Admin'. Must be one of: learner, instructor, manager" }
  ]
}
```

**Implementation steps:**
1. Parse CSV with `csv.DictReader`
2. Validate each row: email format, required fields (`full_name`, `email_address`, `user_role`), role is valid choice
3. Use `User.objects.bulk_create()` wrapped in `transaction.atomic()`
4. Generate random passwords, hash with `make_password()`
5. Track per-row success/failure
6. Optionally trigger welcome emails (requires email templates — see #14)

---

## HIGH — Incomplete Models & Serializers

### 4. LivestreamQuestion Model (MISSING)

**File:** `apps/livestream/serializers.py` (line 68) — `get_question_count()` hardcoded to return `0`.

**Model to create in `apps/livestream/models.py`:**

```python
class LivestreamQuestion(models.Model):
    session = models.ForeignKey(LivestreamSession, on_delete=models.CASCADE, related_name='questions')
    asked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='livestream_questions')
    question_text = models.TextField()
    asked_at = models.DateTimeField(auto_now_add=True)
    is_answered = models.BooleanField(default=False)
    answer_text = models.TextField(blank=True, default='')
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='answered_questions')
    answered_at = models.DateTimeField(null=True, blank=True)
    upvotes = models.PositiveIntegerField(default=0)
```

**Endpoints needed:**
```
GET    /api/v1/livestream/sessions/{id}/questions/    → list questions for a session
POST   /api/v1/livestream/sessions/{id}/questions/    → { "question_text": "How does X work?" }
POST   /api/v1/livestream/questions/{id}/answer/      → { "answer_text": "X works by..." }
DELETE /api/v1/livestream/questions/{id}/
```

**After creating model**, update `get_question_count()` in serializer to return `self.questions.count()`.

---

### 5. Incomplete Serializers

**File:** `apps/catalogue/serializers.py`

**Remaining issues:**
- `CourseCreateSerializer` (line 723-725) — empty class with just `pass`. If this is used by any POST endpoint, it needs field definitions and validation. If it's unused, delete it.
- `AssignmentCreateUpdateSerializer` (lines 361-445) — has `create()` but no `update()` method. Add `update()` to handle PUT/PATCH on assignments, updating fields like `instructions`, `max_points`, `due_date`, `rubric_criteria`, etc.

---

### 6. Assignment Model — Minor Gaps

**File:** `apps/catalogue/models.py` (lines 383-436)

**Status: Mostly complete.** Fields that already exist: `due_date`, `allow_late`, `late_cutoff_date`, `penalty_type`, `penalty_percent`, `max_file_size_mb`, `max_attempts`, `allowed_file_types`, `rubric_criteria`.

**Only missing:**
- `file_upload_required` (BooleanField, default=True) — frontend currently infers this from `allowed_file_types` being non-empty, but an explicit flag would be cleaner.

**Severity:** LOW.

---

### 7. Quiz Model — Missing Fields

**File:** `apps/catalogue/models.py` (lines 365-381)

**Current Quiz model** has only: `session` (OneToOne), `settings` (JSONField), timestamps.

The quiz settings like `time_limit_minutes`, `shuffle_questions`, `passing_score_percent` are stored inside the `settings` JSON field. The frontend reads them from `QuizDetailResponse.settings`.

**What's actually missing** (not covered by `settings` JSON or `QuizQuestion`):
- `QuizQuestion` already has `order` (line 455) and `points` (line 458) — these are NOT missing
- `QuizQuestion` is missing:
  - `explanation` (TextField, blank=True) — text shown after a question is answered, explaining the correct answer
- Consider promoting frequently-queried settings from JSON to model fields for DB-level filtering:
  - `time_limit_minutes` (PositiveIntegerField, null=True)
  - `randomize_questions` (BooleanField, default=False)

**Severity:** MEDIUM for `explanation` field, LOW for promoting JSON fields.

---

## MEDIUM — Incomplete Views & Actions

### 8. ReportViewSet — Data Queries

**File:** `apps/learning/views.py` (lines 301-385)

Endpoint shell exists (CRUD + download). The actual data querying is the missing piece — see item #2 above for full specs per report type.

---

### 9. SubmissionViewSet — Enhancements

**File:** `apps/learning/views.py` (lines 419-473)

**What works:** CRUD + `grade` action at `POST /submissions/{id}/grade/`

The `grade` action request (already implemented):
```json
POST /api/v1/learning/submissions/{id}/grade/
{
  "grade": 85,
  "feedback": "Good work on the analysis section.",
  "internal_notes": "Late submission but quality is high"
}
```

**What's missing:**

**a) Bulk grade action:**
```
POST /api/v1/learning/submissions/bulk_grade/
```
Request:
```json
{
  "grades": [
    { "submission_id": 1, "grade": 90, "feedback": "Excellent" },
    { "submission_id": 2, "grade": 75, "feedback": "Needs improvement on section 3" },
    { "submission_id": 3, "grade": 60, "feedback": "Missing citations" }
  ]
}
```
Response:
```json
{
  "graded": 3,
  "results": [
    { "submission_id": 1, "status": "success" },
    { "submission_id": 2, "status": "success" },
    { "submission_id": 3, "status": "success" }
  ]
}
```

**b) Grade statistics action** (for `GradebookPage.tsx` histogram):
```
GET /api/v1/learning/submissions/statistics/?course={courseId}
```
Response:
```json
{
  "total_submissions": 45,
  "graded": 40,
  "pending": 5,
  "average_grade": 78.5,
  "distribution": [
    { "range": "90-100", "label": "A", "count": 8, "percentage": 20 },
    { "range": "80-89", "label": "B", "count": 12, "percentage": 30 },
    { "range": "70-79", "label": "C", "count": 10, "percentage": 25 },
    { "range": "60-69", "label": "D", "count": 6, "percentage": 15 },
    { "range": "0-59", "label": "F", "count": 4, "percentage": 10 }
  ]
}
```

**c) File upload validation:** In `create()`, check `submitted_file_name` extension against `Assignment.allowed_file_types` and file size against `Assignment.max_file_size_mb`.

**d) Resubmission tracking:** Currently allows only one submission per enrollment+assignment. Add `attempt_number` field and allow multiple submissions up to `Assignment.max_attempts`.

---

### 10. DiscussionViewSet — Moderation

**File:** `apps/learning/views.py` (lines 205-248)

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

### 11. ModuleViewSet — Bulk Reorder

**File:** `apps/catalogue/views.py` (lines 551-615)

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

### 12. SessionViewSet — Gaps

**File:** `apps/catalogue/views.py` (lines 618-801)

**a) Quiz creation via API:**
Currently `/sessions/{id}/quiz/` only supports GET (fetch quiz) and PATCH (update settings). Add POST to create a new Quiz for a session:
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

## LOW — Remaining Services & Templates

### 13. Email Templates

**File:** `config/settings.py` (lines 112-129)

**Current:** Console backend in dev, SendGrid configured for prod.

**Templates to create in `templates/emails/`:**

| Template | Trigger | Key variables |
|---|---|---|
| `verification.html` | User registration | `user_name`, `verification_url` |
| `password_reset.html` | Password reset request | `user_name`, `reset_url`, `expiry_hours` |
| `enrollment_confirmation.html` | Successful enrollment | `user_name`, `course_title`, `start_date` |
| `certificate_issued.html` | Course completion | `user_name`, `course_title`, `certificate_url` |
| `payment_receipt.html` | Successful payment | `user_name`, `course_title`, `amount`, `currency`, `transaction_id`, `date` |

---

## INCOMPLETE MIGRATIONS

### 14. Session Content Source Backfill

**File:** `apps/catalogue/migrations/0009_backfill_session_content_source_and_external_video_fields.py` (line 83)

**Issue:** Empty `backfill()` function with just `pass`.

**What to implement:**
```python
def backfill(apps, schema_editor):
    Session = apps.get_model('catalogue', 'Session')
    for session in Session.objects.filter(content_source=''):
        if session.video_url:
            if 'youtube.com' in session.video_url or 'youtu.be' in session.video_url:
                session.content_source = 'youtube'
            elif 'vimeo.com' in session.video_url:
                session.content_source = 'vimeo'
            else:
                session.content_source = 'external_url'
            session.save(update_fields=['content_source'])
```

---

## TEST COVERAGE GAPS

| App | Current Tests | Major Gaps |
|---|---|---|
| `learning` | 27 tests | Quiz submission tests missing, report generation not tested |
| `catalogue` | 95 tests | Quiz creation/update minimal, assignment tests basic |
| `payments` | 8 tests | Webhook handlers not tested |
| `accounts` | 48 tests | CSV bulk import not tested |
| `audit` | 6 tests | Minimal |
| `notifications` | 2 tests | Only email provider routing tested; CRUD and mark_read not tested |
| `livestream` | **0 tests** | **No test file exists** — create `apps/livestream/tests.py` |

**Priority:** Create `apps/livestream/tests.py` with tests for:
- Session CRUD (create, update status, start/end)
- Attendance tracking (mark joined, mark left, duration calculation)
- Zoom webhook handler (mock webhook payloads for each event type)

---

## Endpoints the Frontend Expects But Backend Doesn't Have

| Endpoint | Method | Purpose | Expected Response Shape | Frontend File |
|---|---|---|---|---|
| `/api/v1/learning/quiz-submissions/` | POST | Submit quiz answers | See item #1 above | QuizPlayer.tsx |
| `/api/v1/learning/quiz-submissions/?quiz={id}` | GET | Get attempts for a quiz | Paginated list of QuizSubmission | QuizPlayer.tsx |
| `/api/v1/learning/submissions/statistics/?course={id}` | GET | Grade histogram & stats | See item #9b above | GradebookPage.tsx |
| `/api/v1/learning/submissions/bulk_grade/` | POST | Grade multiple at once | See item #9a above | GradebookPage.tsx |
| `/api/v1/uploads/quota/` | GET | Storage usage | `{ "used_bytes": 5368709120, "total_bytes": 10737418240 }` | ContentUploadPage.tsx |
| `/api/v1/public/stats/` | GET | Platform metrics | `{ "courses": 150, "learners": 12000, "instructors": 85, "certificates": 8500 }` | StatsBanner.tsx |
| `/api/v1/catalogue/courses/{id}/reviews/` | GET | Course reviews | `{ "average": 4.8, "total": 234, "distribution": [78,15,5,1,1], "reviews": [{ "user_name": "...", "rating": 5, "content": "...", "created_at": "..." }] }` | CourseReviews.tsx |
| `/api/v1/public/clients/` | GET | Trusted-by logos | `[{ "name": "Acme Corp", "logo_url": "https://..." }]` | TrustedBy.tsx |

**Note:** The analytics pages (`ManagerAnalyticsPage`) currently compute all metrics client-side from existing `/enrollments/`, `/courses/`, and `/certificates/` endpoints. No dedicated analytics endpoint is strictly needed, but a server-side aggregation endpoint would improve performance at scale.

---

## LOW — Silent Exception Handling & Code Quality

### 15. Payment Webhook Handlers — Silent `pass`
- **File:** `apps/payments/utils/webhook_handlers.py` (lines 271, 317)
- **Problem:** `_handle_failed_payment()` and `_handle_refund()` silently ignore `Payment.DoesNotExist`.
- **Fix:** Replace `pass` with `logger.warning(f"Payment not found for transaction {transaction_id}")`.

### 16. Payment Validators — Silent Validation
- **File:** `apps/payments/utils/payment_validators.py` (line 328)
- **Problem:** Invalid phone number silently swallowed.
- **Fix:** Add `logger.info(f"Phone validation skipped for {phone}: {e}")`.

### 17. Calendar Service — Timezone Silencing
- **File:** `apps/livestream/services/calendar_service.py` (line 57)
- **Problem:** `except Exception: pass` on invalid timezone — events may use wrong timezone silently.
- **Fix:** `logger.warning(f"Invalid timezone {tz}, falling back to UTC")` then set `tz = 'UTC'`.

### 18. Audit Views — Date Parsing
- **File:** `apps/audit/views.py` (lines 79, 89)
- **Problem:** Malformed date filters silently ignored — user gets unfiltered results without knowing.
- **Fix:** Return `400 Bad Request` with message: `"Invalid date format for 'date_from'. Expected YYYY-MM-DD."`.

### 19. Catalogue Views — Category Filter
- **File:** `apps/catalogue/views.py` (line 118)
- **Problem:** Non-numeric category ID silently ignored.
- **Fix:** Return `400` or log warning and skip filter.

### 20. Livestream Webhook Health Check — Misnamed
- **File:** `apps/livestream/views.py` (lines 876-882)
- **Problem:** `validate_webhook` action returns `{"status": "ok"}` without doing any validation.
- **Fix:** Either rename to `webhook_health` or implement actual webhook signature validation for the configured platform.

### 21. Notifications ViewSet — Limited
- **File:** `apps/notifications/views.py`
- **Works:** CRUD + `mark_read` + `mark_all_read`
- **Missing:**
  - Date range filter: `?created_after=2026-03-01&created_before=2026-03-17`
  - Bulk delete: `POST /notifications/bulk_delete/` with `{ "ids": [1, 2, 3] }`
  - Notification preferences: `GET/PUT /notifications/preferences/` → `{ "email_enabled": true, "push_enabled": false, "types": { "enrollment": true, "system": true, "milestone": false } }`

---

## Django Admin Gaps

### 22. Catalogue Admin — Missing Model Registrations
- **File:** `apps/catalogue/admin.py`
- **Registered:** `QuestionCategory`, `BankQuestion`, `Assignment`, `Quiz`, `QuizQuestion`, `Module`
- **NOT registered:** `Course`, `Session`, `Category`, `Tag`
- **Fix:** Add `@admin.register(Course)`, etc. with appropriate `list_display`, `list_filter`, `search_fields`.

### 23. Livestream Admin — No admin.py
- `apps/livestream/admin.py` does not exist.
- **Create it** and register: `LivestreamSession`, `LivestreamAttendance`, `LivestreamRecording`
- Example:
```python
@admin.register(LivestreamSession)
class LivestreamSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'platform', 'status', 'scheduled_start', 'created_at')
    list_filter = ('platform', 'status')
    search_fields = ('title',)
```

### 24. Payments Model — Silent ImportError
- **File:** `apps/payments/models.py` (lines 100-102)
- **Problem:** `except ImportError: pass` for Enrollment model import.
- **Fix:** Use `apps.get_model('learning', 'Enrollment')` pattern or Django's lazy reference string `'learning.Enrollment'` in ForeignKey.

---

## Configuration TODOs

- **CRITICAL: Set up Celery** — no `celery.py`, no task files, no broker config exists anywhere. Required for: async reports (#2), bulk imports (#3), email sending. Need: `config/celery.py`, Redis broker, `apps/*/tasks.py` files. See item #2 for setup steps.
- Set `ZOOM_WEBHOOK_SECRET` in production settings
- Configure Google Meet: `GOOGLE_MEET_SERVICE_ACCOUNT_FILE`, `GOOGLE_MEET_DELEGATED_USER`, `GOOGLE_MEET_CALENDAR_ID` (code is ready, just needs credentials)
- Configure Teams: `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`, `TEAMS_CLIENT_SECRET`, `TEAMS_ORGANIZER_USER_ID` (code is ready, just needs Azure AD app registration)
- Set up SendGrid email templates for production
