# TASC LMS Backend — Pending Tasks

**Last updated:** 17 March 2026
**Repo:** `tasc-lms-backend`
**Contact for questions:** Coordinate with frontend team on endpoint contracts

---

## How to Use This File

This file tracks all known incomplete work in the backend codebase. Items are grouped by priority. Each includes affected files, what exists, what's missing, and frontend impact. When you pick up a task, update this file.

---

## CRITICAL — Missing Endpoints & Models

### 1. Quiz Submission System (NEW)
- **Status:** Model does not exist. No endpoints.
- **What's needed:**
  - `QuizSubmission` model: links learner + quiz + attempt number + score + submitted_at
  - `QuizAnswer` model: links submission + question + selected answer + is_correct
  - `POST /api/v1/learning/quiz-submissions/` — submit quiz answers
  - `GET /api/v1/learning/quiz-submissions/?quiz={id}` — get attempts for a quiz
  - Auto-grading logic for: multiple-choice, true-false, short-answer, fill-in-blank
  - Manual grading flag for essay and matching types
- **Files to create/modify:**
  - `apps/learning/models.py` — add QuizSubmission, QuizAnswer models
  - `apps/learning/serializers.py` — add submission serializers
  - `apps/learning/views.py` — add QuizSubmissionViewSet
  - `apps/learning/urls.py` — register new routes
  - New migration file
- **Frontend impact:** QuizPlayer currently does client-side grading only. This is the #1 backend gap.

### 2. Report Generation — Async Implementation
- **File:** `apps/learning/views.py` (lines 355-358)
- **Current:** Report status immediately set to READY with empty file. Comment: `# TODO: In production, this would trigger an async task`
- **What's needed:**
  - Celery task integration for report generation
  - Actual data export logic for each report type:
    - USER_ACTIVITY — query session progress, login history
    - COURSE_PERFORMANCE — query enrollments, completions, scores
    - ENROLLMENT — query enrollment data with filters
    - COMPLETION — query completion rates per course/org
    - ASSESSMENT — query submission scores, pass rates
    - REVENUE — query transactions, invoices
  - CSV and PDF output formats
  - File upload to storage backend (S3/Spaces)
  - Progress tracking for long-running reports
- **Frontend impact:** ManagerReportsPage and FinanceExportPage can't download reports

### 3. Bulk User Import — CSV Parsing
- **File:** `apps/accounts/views_superadmin.py` (lines 77-84)
- **Current:** `bulk_import()` action returns dummy response: `{"message": "Bulk import started.", "imported": 0}`
- **Comment:** `# TODO: Implement actual CSV parsing and user creation`
- **What's needed:**
  - CSV file upload and parsing
  - Row validation (email format, required fields, role validation)
  - Bulk user creation with proper password hashing
  - Per-row success/failure tracking
  - Transaction rollback on critical failures
  - Response with import results summary
- **Frontend impact:** ManagerBulkImportPage and ManagerBulkEnrollPage are non-functional

---

## HIGH — Incomplete Models & Serializers

### 4. LivestreamQuestion Model (MISSING)
- **File:** `apps/livestream/serializers.py` (line 68)
- **Current:** `get_question_count()` hardcoded to return 0. Comment: `# TODO: restore when LivestreamQuestion model is created`
- **What's needed:**
  - `LivestreamQuestion` model with fields: `question_text`, `asked_by` (FK User), `session` (FK LivestreamSession), `asked_at`, `is_answered`, `answer_text`, `answered_by` (FK User), `answered_at`
  - ViewSet for CRUD + mark-as-answered action
  - Migration file
- **Frontend impact:** Livestream Q&A during sessions won't work

### 5. Incomplete Serializers — Empty Meta Classes
- **File:** `apps/catalogue/serializers.py`
- **Issues:**
  - `QuizDetailSerializer` (lines 244-250) — only `class Meta`, NO fields defined
  - `QuizSessionSummarySerializer` (lines 236-242) — only `class Meta`, NO fields defined
  - `CourseCreateSerializer` (line 723-725) — empty class, just `pass`
  - `AssignmentCreateUpdateSerializer` (lines 361-445) — has `create()` but no `update()` method
- **What to do:** Define proper field lists, implement missing methods, or remove redundant serializers.

### 6. Assignment Model — Missing Fields
- **File:** `apps/catalogue/models.py` (lines 383-436)
- **What exists:** Basic assignment fields, rubric JSON, file types
- **What's missing:**
  - `due_date` field (DateTimeField) — frontend expects this
  - `late_submission_allowed` flag
  - `late_penalty_percentage`
  - `file_upload_required` flag
  - `max_file_size_mb`
- **Note:** Some of these may exist in the Assignment config JSON but should be proper model fields for querying.

### 7. Quiz Model — Missing Fields
- **File:** `apps/catalogue/models.py` (lines 365-381)
- **What exists:** Basic quiz fields, passing_score
- **What's missing:**
  - `time_limit_minutes` as a proper model field (may only be in settings JSON)
  - `randomize_questions` boolean
  - `allow_review_after_submission` boolean
  - Per-question `points_value` field on QuizQuestion
  - Per-question `explanation` text field on QuizQuestion
  - Per-question `order` field on QuizQuestion

---

## MEDIUM — Incomplete Views & Actions

### 8. SessionProgressViewSet — Notes Support
- **File:** `apps/learning/views.py` (lines 112-147)
- **Current:** `notes` field exists on model but no dedicated action to update just notes.
- **What's needed:** The frontend is now storing notes as JSON in the `notes` field via `PATCH`. Ensure the field is included in the serializer's writable fields and the PATCH endpoint accepts it.
- **Frontend impact:** Notes tab on CoursePlayerPage now sends `PATCH` with `{ notes: "..." }`.

### 9. ReportViewSet — All Report Types
- **File:** `apps/learning/views.py` (lines 301-385)
- **What works:** CRUD, download action shell
- **What's missing:** Actual data querying and file generation for all 6 report types (see item #2 above)

### 10. SubmissionViewSet — Enhancements
- **File:** `apps/learning/views.py` (lines 419-473)
- **What works:** CRUD, grade action
- **What's missing:**
  - Bulk grade assignment
  - Grade statistics/histogram action
  - File upload validation (size, format)
  - Resubmission tracking (currently single submission per assignment)

### 11. DiscussionViewSet — Moderation
- **File:** `apps/learning/views.py` (lines 205-248)
- **What works:** CRUD
- **What's missing:**
  - Pin/lock discussion action
  - Flag/report action
  - Instructor-only reply badge
  - Search/filter by course/session

### 12. ModuleViewSet — Reorder Action
- **File:** `apps/catalogue/views.py` (lines 551-615)
- **What's missing:** Dedicated `reorder` bulk action endpoint. Frontend currently sends individual PATCH requests for each module's `order` field — a bulk reorder endpoint would be more efficient.

### 13. SessionViewSet — Gaps
- **File:** `apps/catalogue/views.py` (lines 618-801)
- **Issues:**
  - Quiz action (`/sessions/{id}/quiz/`) only supports GET/PATCH, no POST to create quiz
  - Assignment action similarly missing POST
  - No session preview action for non-enrolled users
  - Asset URL presigning may be incomplete

---

## LOW — Webhook Handlers & Services

### 14. Zoom Webhook Handler — Incomplete
- **File:** `apps/livestream/services/zoom_service.py`
- **What exists:** Webhook signature validation
- **What's missing:** Event type handling (meeting started, ended, recording ready, participant joined/left)

### 15. Google Meet Webhook Handler — Incomplete
- **File:** `apps/livestream/services/google_meet_service.py`
- **What exists:** Handler class
- **What's missing:** Calendar event sync, meeting state updates, error recovery

### 16. Teams Webhook Handler — Incomplete
- **File:** `apps/livestream/services/teams_service.py`
- **What exists:** Handler class
- **What's missing:** Change notification parsing, meeting state sync

### 17. Email Templates
- **File:** `config/settings.py` (lines 112-129)
- **Current:** Console-based email in dev, SendGrid in prod
- **What's missing:** HTML email templates for: verification, password reset, enrollment confirmation, certificate issuance, payment receipt

---

## INCOMPLETE MIGRATIONS

### 18. Session Content Source Backfill
- **File:** `apps/catalogue/migrations/0009_backfill_session_content_source_and_external_video_fields.py`
- **Issue:** Data migration has `pass` at line 83 — empty backfill function
- **What to do:** Populate `content_source` field based on existing `video_url` data

---

## TEST COVERAGE GAPS

| App | Current Tests | Major Gaps |
|-----|--------------|------------|
| `learning` | 27 tests | Quiz submission tests missing, notes API not tested |
| `catalogue` | 95 tests | Quiz creation/update minimal, assignment tests basic |
| `payments` | 8 tests | Webhook handlers not tested |
| `accounts` | 48 tests | CSV bulk import not tested |
| `audit` | 6 tests | Minimal |
| `notifications` | 2 tests | Severely limited |
| `livestream` | **0 tests** | **No test file exists at all** |

**Priority:** Create `apps/livestream/tests.py` with session creation, attendance tracking, and webhook tests.

---

## Endpoints the Frontend Expects But Backend Doesn't Have

| Endpoint | Purpose | Frontend File |
|----------|---------|---------------|
| `POST /api/v1/learning/quiz-submissions/` | Submit quiz answers | QuizPlayer.tsx |
| `GET /api/v1/learning/grades/distribution/` | Grade histogram | GradebookPage.tsx |
| `GET /api/v1/learning/grades/students/` | Student grade list | GradebookPage.tsx |
| `GET /api/v1/learning/analytics/enrollments/` | Enrollment trends | All analytics pages |
| `GET /api/v1/learning/analytics/engagement/` | Engagement metrics | All analytics pages |
| `GET /api/v1/uploads/quota/` | Storage usage | ContentUploadPage.tsx |
| Async report generation | Generate CSV/PDF files | ManagerReportsPage.tsx |
| `GET /api/v1/public/stats/` | Platform metrics (courses, learners, instructors, certs) | StatsBanner.tsx, BusinessStatsSection.tsx |
| `GET /api/v1/catalogue/courses/{id}/reviews/` | Course reviews and ratings | CourseReviews.tsx |
| `GET /api/v1/public/clients/` | Trusted-by company logos | TrustedBy.tsx |

---

## LOW — Silent Exception Handling & Code Quality

### 19. Payment Webhook Handlers — Silent `pass` on Missing Records
- **File:** `apps/payments/utils/webhook_handlers.py` (lines 271, 317)
- **Issue:** `_handle_failed_payment()` and `_handle_refund()` silently ignore `PaymentDoesNotExist` with bare `pass`.
- **What to do:** Add `logger.warning()` instead of silent pass.

### 20. Payment Validators — Silent Validation Failures
- **File:** `apps/payments/utils/payment_validators.py` (line 328)
- **Issue:** Invalid phone number validation catches `ValidationError` with silent `pass`.
- **What to do:** Add logging for failed validations.

### 21. Calendar Service — Timezone Exception Silencing
- **File:** `apps/livestream/services/calendar_service.py` (line 57)
- **Issue:** `except Exception: pass` for invalid timezone conversion. Calendar events may silently use wrong timezone.
- **What to do:** Log warning and fall back to UTC explicitly.

### 22. Audit Views — Date Parsing Silenced
- **File:** `apps/audit/views.py` (lines 79, 89)
- **Issue:** ValueError on date parsing silently caught with `pass`. Users won't know their date filters are malformed.
- **What to do:** Return 400 error or log warning.

### 23. Catalogue Views — Category Filter Silenced
- **File:** `apps/catalogue/views.py` (line 118)
- **Issue:** ValueError when parsing category ID silently ignored.
- **What to do:** Return meaningful error or skip filter with logging.

### 24. Livestream Webhook Validation — Misnamed Endpoint
- **File:** `apps/livestream/views.py` (lines 876-882)
- **Issue:** `validate_webhook` action returns hardcoded `{"status": "ok"}` without actual validation. It's a health check, not a validator.
- **What to do:** Rename to `webhook_health` or implement actual signature validation.

### 25. Notifications ViewSet — Limited Functionality
- **File:** `apps/notifications/views.py`
- **Issue:** Only basic CRUD + mark_read/mark_all_read. No date filtering, bulk delete, or preference management.
- **What to do:** Add notification preferences, date filters, bulk delete.

---

## Configuration TODOs

- Ensure `ZOOM_WEBHOOK_SECRET` is set in production settings
- Ensure Google Meet service account credentials are configured
- Add Celery + Redis/RabbitMQ for async task processing (reports, bulk imports)
- Configure email templates for SendGrid in production
- Add HTML email templates for: verification, password reset, enrollment confirmation, certificate issuance, payment receipt
