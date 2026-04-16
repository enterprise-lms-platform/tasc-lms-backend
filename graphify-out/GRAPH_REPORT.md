# Graph Report - .  (2026-04-15)

## Corpus Check
- 211 files · ~99,808 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2458 nodes · 14327 edges · 100 communities detected
- Extraction: 22% EXTRACTED · 78% INFERRED · 0% AMBIGUOUS · INFERRED: 11226 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `Enrollment` - 434 edges
2. `Course` - 418 edges
3. `Quiz` - 316 edges
4. `Session` - 295 edges
5. `UserSubscription` - 276 edges
6. `Assignment` - 272 edges
7. `Category` - 265 edges
8. `QuizQuestion` - 256 edges
9. `Subscription` - 231 edges
10. `Tag` - 227 edges

## Surprising Connections (you probably didn't know these)
- `Meta` --uses--> `Enrollment`  [INFERRED]
  apps\payments\models.py → apps\learning\models.py
- `Return user's active org for org-scoped roles, else None.` --uses--> `Membership`  [INFERRED]
  apps\accounts\rbac.py → apps\accounts\models.py
- `Permissions for subscription-gated content access.` --uses--> `UserSubscription`  [INFERRED]
  apps\payments\permissions.py → apps\payments\models.py
- `Status` --uses--> `Enrollment`  [INFERRED]
  apps\payments\models.py → apps\learning\models.py
- `SubmissionAdmin` --uses--> `Submission`  [INFERRED]
  apps\learning\admin.py → apps\learning\models.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.01
Nodes (217): AuditLogAdmin, APIView, _log_otp_send_failure(), LoginView, password_reset_confirm(), password_reset_request(), post(), Wrapper around SimpleJWT refresh view so Swagger tagging works. (+209 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (264): AssignmentAdmin, BankQuestionAdmin, CategoryAdmin, CourseAdmin, ModuleAdmin, QuestionCategoryAdmin, QuizAdmin, QuizQuestionAdmin (+256 more)

### Community 2 - "Community 2"
Cohesion: 0.04
Nodes (199): PesapalIPNAdmin, SubscriptionAdmin, UserSubscriptionAdmin, FlutterwaveService, Verify a payment with Flutterwave                  Args:             transact, Handle Flutterwave webhook                  Args:             request: Django, Get headers for Flutterwave API requests, Process successful payment from webhook (+191 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (148): LivestreamAttendanceAdmin, LivestreamQuestionAdmin, LivestreamRecordingAdmin, LivestreamSessionAdmin, CalendarService, Service for calendar integration.     Generates calendar files and links for Go, Service for timezone conversion and display., TimezoneService (+140 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (146): check_and_award_badges(), _get_user_stat(), Badge evaluation engine.  Central function `check_and_award_badges(user, criteri, Return the current numeric value for a given criteria_type., Evaluate badge criteria for a user and award any newly earned badges.      Args:, BadgeSerializer, Meta, Badge serializers for the learning app. (+138 more)

### Community 5 - "Community 5"
Cohesion: 0.02
Nodes (17): _auth(), CategoryManagerCrudTest, CertificateViewSetScopeTest, CourseApprovalPhase2Test, CourseApprovalWorkflowTest, EnrollmentListScopeAndFiltersTest, ExternalVideoEmbeddingTest, LmsManagerAnalyticsPlatformWideTest (+9 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (95): BasePermission, Session attachment (Resource) for downloading course materials., SessionAttachment, CanDeleteCourse, CanEditBankQuestion, CanEditCourse, CanEditModuleCourse, CanEditQuestionCategory (+87 more)

### Community 7 - "Community 7"
Cohesion: 0.02
Nodes (53): AbstractUser, AccountUserManager, Action, AssignmentType, ContentSource, Conversation, GradingType, Icon (+45 more)

### Community 8 - "Community 8"
Cohesion: 0.02
Nodes (42): AuditLogPermission, Read-only access to audit logs by role:     - tasc_admin, lms_manager: can view, get_active_membership_organization(), Return user's active org for org-scoped roles, else None., AuditLogListSerializer, Response shape matching frontend needs., create_boto3_client(), delete_spaces_object() (+34 more)

### Community 9 - "Community 9"
Cohesion: 0.1
Nodes (6): BaseCommand, Command, Management command to seed all 22 badge definitions. Usage: python manage.py see, Command, Command, Command

### Community 10 - "Community 10"
Cohesion: 0.15
Nodes (21): google_oauth_link(), google_oauth_login(), google_oauth_status(), google_oauth_unlink(), Link Google Account Endpoint.          Expects a JSON body with:     {, Unlink Google Account Endpoint.          Unlinks the Google account from the c, Get Google OAuth Status Endpoint.          Returns the current user's Google O, Google OAuth Login Endpoint.          Expects a JSON body with:     { (+13 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (6): PesapalFlowWave1Test, test_onetime_initiate_pending_provider_does_not_unblock(), test_onetime_initiate_reconciles_completed_and_still_blocks(), test_onetime_initiate_reconciles_failed_provider_and_allows_retry(), test_onetime_initiate_reconciles_invalid_provider_and_allows_retry(), test_onetime_initiate_verify_failure_does_not_unblock()

### Community 12 - "Community 12"
Cohesion: 0.15
Nodes (16): ListModelMixin, LearnerEnrollmentResponseSerializer, LearnerMyCourseCourseSerializer, LearnerMyCourseSerializer, Learner-specific serializers for Learner Flow v1., Nested course summary for my-courses., Response shape for GET /learner/my-courses/., Response shape for POST /learner/courses/<slug>/enroll/. (+8 more)

### Community 13 - "Community 13"
Cohesion: 0.31
Nodes (2): _auth(), SubscriptionMeViewTest

### Community 14 - "Community 14"
Cohesion: 0.27
Nodes (10): _build_description(), convert_to_user_timezone(), format_for_user(), generate_ics_file(), get_all_calendar_links(), get_apple_calendar_url(), get_google_calendar_url(), get_outlook_calendar_url() (+2 more)

### Community 15 - "Community 15"
Cohesion: 0.29
Nodes (10): AppConfig, AccountsConfig, AuditConfig, CatalogueConfig, CommonConfig, LearningConfig, LivestreamConfig, MessagingConfig (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.35
Nodes (10): _add_attempt_number_if_missing(), _add_unique_triple(), backwards(), _drop_submission_unique_constraints(), forwards(), Migration, Remove all UNIQUE constraints / unique indexes on learning_submission (not the P, Staging drift: table has session_id and unique(enrollment,session), no assignmen (+2 more)

### Community 17 - "Community 17"
Cohesion: 0.31
Nodes (9): detect_provider(), _is_https(), Pure helpers for external video embedding (YouTube, Vimeo, Loom). Uses only std, Return True if URL uses https scheme., Detect video provider from URL. Returns lowercase provider name or None.     On, Convert a watch/share URL to an embed URL.     Returns None for unknown provide, Validate external video URL and return (provider, embed_url).     Raises ValueE, to_embed_url() (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.25
Nodes (7): generate_otp(), hash_otp(), OTP generation and verification utilities. Plain OTP is never stored; only hash, Generate a numeric OTP using configured length (zero-padded)., Hash OTP for secure storage using Django's make_password., Verify OTP against stored hash using check_password., verify_otp()

### Community 19 - "Community 19"
Cohesion: 0.4
Nodes (4): backfill_content_source_and_external_video(), _derive_provider_embed_url(), Migration, Derive provider and embed URL directly inside migration     so the migration do

### Community 20 - "Community 20"
Cohesion: 0.4
Nodes (2): PasswordComplexityValidator, Enforce uppercase, lowercase, digit, and special character requirements.

### Community 21 - "Community 21"
Cohesion: 0.4
Nodes (2): Migration, Create learning_quizsubmission and learning_quizanswer tables.  Migration 0004

### Community 22 - "Community 22"
Cohesion: 0.5
Nodes (1): Migration

### Community 23 - "Community 23"
Cohesion: 0.5
Nodes (3): get_list_from_env(), Django settings for config project.  Generated by 'django-admin startproject', Helper to parse comma-separated environment variables into a list.

### Community 24 - "Community 24"
Cohesion: 0.67
Nodes (2): main(), Run administrative tasks.

### Community 25 - "Community 25"
Cohesion: 0.67
Nodes (2): Test Meet creation with OAuth 2.0, test_with_oauth()

### Community 26 - "Community 26"
Cohesion: 0.67
Nodes (2): Migration, State-only migration: register the three livestream models with Django's migrat

### Community 27 - "Community 27"
Cohesion: 0.67
Nodes (2): Migration, No-op migration: 0001_initial already creates User with country, phone_number,

### Community 28 - "Community 28"
Cohesion: 0.67
Nodes (2): Migration, State-only migration: remove LivestreamSession, LivestreamAttendance, and Lives

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Celery configuration for TASC LMS.

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Migration

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Migration

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Migration

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Migration

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Migration

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Migration

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Migration

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Migration

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Migration

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Migration

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Migration

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Migration

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Migration

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Migration

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Migration

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Migration

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Migration

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Migration

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Migration

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Migration

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Migration

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Migration

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Migration

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Migration

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Migration

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Migration

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Migration

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Migration

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Migration

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Migration

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Migration

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Migration

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Migration

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Migration

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Migration

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Migration

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Migration

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): Migration

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Migration

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Migration

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Migration

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Migration

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Migration

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Migration

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Migration

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Migration

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): ASGI config for config project.  It exposes the ASGI callable as a module-leve

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): WSGI config for config project.  It exposes the WSGI callable as a module-leve

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (0): 

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (0): 

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (0): 

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): Grade a submission (instructor/admin only)

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Bulk grade submissions (instructor/admin only)

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): Return start time in ISO format for APIs

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Return end time in ISO format for APIs

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): Calculate percentage of session attended

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): Take action on a session (start/end/cancel/remind)

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): Answer a question (instructor only)

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (1): Generate .ics file content for calendar import.          Args:             se

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (1): Build rich description for calendar event

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (1): Generate Google Calendar URL for adding event.          Args:             ses

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (1): Generate Outlook Calendar URL for adding event.          Args:             se

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (1): Generate Apple Calendar URL (uses webcal protocol).          Args:

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (1): Generate Yahoo Calendar URL.          Args:             session: LivestreamSe

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (1): Get all calendar links for a session.          Args:             session: Liv

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (1): Get timezone conversion helper.         Returns list of common timezones for us

### Community 96 - "Community 96"
Cohesion: 1.0
Nodes (1): Convert datetime to user's timezone.          Args:             dt: Datetime

### Community 97 - "Community 97"
Cohesion: 1.0
Nodes (1): Format datetime for display in user's timezone.          Args:             dt

### Community 98 - "Community 98"
Cohesion: 1.0
Nodes (1): Get list of timezone choices for forms.

### Community 99 - "Community 99"
Cohesion: 1.0
Nodes (1): Pesapal recurring expects dates in dd-MM-yyyy.

## Knowledge Gaps
- **192 isolated node(s):** `Run administrative tasks.`, `Test Meet creation with OAuth 2.0`, `Google OAuth Login Endpoint.          Expects a JSON body with:     {`, `Link Google Account Endpoint.          Expects a JSON body with:     {`, `Unlink Google Account Endpoint.          Unlinks the Google account from the c` (+187 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 30`** (2 nodes): `0003_user_email_verified_alter_user_country_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (2 nodes): `0004_user_role.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `0006_user_failed_login_attempts_account_locked_until.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (2 nodes): `0007_add_login_otp_challenge.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (2 nodes): `0008_alter_user_managers.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (2 nodes): `0009_organization_industry_organization_settings.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (2 nodes): `0010_add_demo_request_model.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (2 nodes): `0011_business_testimonial.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (2 nodes): `0002_livestreamsession_livestreamrecording_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (2 nodes): `0004_course_access_duration_course_allow_self_enrollment.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (2 nodes): `0004_course_wizard_fields.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (2 nodes): `0005_merge_20260225_0836.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (2 nodes): `0006_alter_course_access_duration.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (2 nodes): `0007_add_session_asset_metadata.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (2 nodes): `0008_add_session_content_source_and_external_video_fields.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (2 nodes): `0010_add_module_model_and_session_module_fk.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (2 nodes): `0011_rename_catalogue_module_course_order_idx_catalogue_m_course__fe6513_idx.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (2 nodes): `0012_add_quiz_models.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (2 nodes): `0013_add_question_bank_models.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (2 nodes): `0014_add_assignment_model.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (2 nodes): `0015_coursereview.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (2 nodes): `0016_add_course_approval_request.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (2 nodes): `0017_course_rejection_reason.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (2 nodes): `0018_rename_catalogue_c_status_9a8f2c_idx_catalogue_c_status_9b807a_idx_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (2 nodes): `0019_quizquestion_explanation.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (2 nodes): `0020_sessionattachment.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (2 nodes): `0021_coursereview_helpful_count_coursereview_report_count.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (2 nodes): `0022_merge_20260328_0303.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (2 nodes): `0022_merge_20260328_0334.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (2 nodes): `0023_merge_20260328_2300.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (2 nodes): `0024_review_add_is_featured_is_rejected_change_default.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (2 nodes): `0002_initial.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (2 nodes): `0003_add_submission_model.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (2 nodes): `0004_quizanswer_quizsubmission_report_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (2 nodes): `0006_badge_userbadge.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (2 nodes): `0007_savedcourse.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (2 nodes): `0008_workshop.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (2 nodes): `0002_alter_livestreamsession_platform.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (2 nodes): `0003_livestreamsession_calendar_channel_id_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (2 nodes): `0004_livestreamquestion.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (2 nodes): `0005_add_attended_absent_status.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (2 nodes): `0002_alter_conversation_options.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (2 nodes): `0002_payment_paymentwebhook_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (2 nodes): `0003_alter_payment_currency_alter_payment_payment_method.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (2 nodes): `0004_pesapalipn_alter_payment_currency_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (2 nodes): `0005_subscription_duration_days.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (2 nodes): `asgi.py`, `ASGI config for config project.  It exposes the ASGI callable as a module-leve`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (2 nodes): `wsgi.py`, `WSGI config for config project.  It exposes the WSGI callable as a module-leve`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `test_google_creds.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `test_public_api.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `api_urls.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `Grade a submission (instructor/admin only)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `Bulk grade submissions (instructor/admin only)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `Return start time in ISO format for APIs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `Return end time in ISO format for APIs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `Calculate percentage of session attended`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `Take action on a session (start/end/cancel/remind)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `Answer a question (instructor only)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `Generate .ics file content for calendar import.          Args:             se`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `Build rich description for calendar event`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `Generate Google Calendar URL for adding event.          Args:             ses`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `Generate Outlook Calendar URL for adding event.          Args:             se`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `Generate Apple Calendar URL (uses webcal protocol).          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `Generate Yahoo Calendar URL.          Args:             session: LivestreamSe`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `Get all calendar links for a session.          Args:             session: Liv`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (1 nodes): `Get timezone conversion helper.         Returns list of common timezones for us`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 96`** (1 nodes): `Convert datetime to user's timezone.          Args:             dt: Datetime`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 97`** (1 nodes): `Format datetime for display in user's timezone.          Args:             dt`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 98`** (1 nodes): `Get list of timezone choices for forms.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 99`** (1 nodes): `Pesapal recurring expects dates in dd-MM-yyyy.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Enrollment` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 9`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.110) - this node is a cross-community bridge._
- **Why does `Course` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 9`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `LivestreamSession` connect `Community 3` to `Community 1`, `Community 2`, `Community 4`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 430 inferred relationships involving `Enrollment` (e.g. with `ManagerOrganizationSettingsView` and `ManagerBillingPlanView`) actually correct?**
  _`Enrollment` has 430 INFERRED edges - model-reasoned connections that need verification._
- **Are the 415 inferred relationships involving `Course` (e.g. with `QuestionCategoryAdmin` and `BankQuestionAdmin`) actually correct?**
  _`Course` has 415 INFERRED edges - model-reasoned connections that need verification._
- **Are the 313 inferred relationships involving `Quiz` (e.g. with `OrganizationSuperadminViewSet` and `UserSuperadminViewSet`) actually correct?**
  _`Quiz` has 313 INFERRED edges - model-reasoned connections that need verification._
- **Are the 292 inferred relationships involving `Session` (e.g. with `QuestionCategoryAdmin` and `BankQuestionAdmin`) actually correct?**
  _`Session` has 292 INFERRED edges - model-reasoned connections that need verification._