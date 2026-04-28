# Graph Report - .  (2026-04-22)

## Corpus Check
- 220 files · ~120,172 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3388 nodes · 23947 edges · 116 communities detected
- Extraction: 17% EXTRACTED · 83% INFERRED · 0% AMBIGUOUS · INFERRED: 19804 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `Enrollment` - 638 edges
2. `Course` - 548 edges
3. `UserSubscription` - 387 edges
4. `Quiz` - 366 edges
5. `Session` - 348 edges
6. `Submission` - 328 edges
7. `Category` - 326 edges
8. `Assignment` - 326 edges
9. `QuizSubmission` - 306 edges
10. `QuizQuestion` - 297 edges

## Surprising Connections (you probably didn't know these)
- `Meta` --uses--> `Enrollment`  [INFERRED]
  apps\payments\models.py → apps\learning\models.py
- `@fixture` --uses--> `Organization`  [INFERRED]
  apps\accounts\tests_superadmin_api.py → apps\accounts\models.py
- `@fixture` --uses--> `Organization`  [INFERRED]
  apps\accounts\tests_superadmin_api.py → apps\accounts\models.py
- `@fixture` --uses--> `Organization`  [INFERRED]
  apps\accounts\tests_superadmin_api.py → apps\accounts\models.py
- `@django_db` --uses--> `Organization`  [INFERRED]
  apps\accounts\tests_superadmin_api.py → apps\accounts\models.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.01
Nodes (246): AuditLogAdmin, @register(AuditLog), APITestCase, AuditLog, Notification model for user notifications., PageNumberPagination, AuditLogPermission, Read-only access to audit logs by role:     - tasc_admin, lms_manager: can view (+238 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (404): @register(UserSubscription), @register(PesapalIPN), @register(Subscription), PesapalIPNAdmin, SubscriptionAdmin, UserSubscriptionAdmin, FlutterwaveService, Verify a payment with Flutterwave                  Args:             transact (+396 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (342): AssignmentAdmin, BankQuestionAdmin, CategoryAdmin, CourseAdmin, @register(BankQuestion), @register(Quiz), @register(QuizQuestion), @register(Session) (+334 more)

### Community 3 - "Community 3"
Cohesion: 0.02
Nodes (344): @register(LivestreamAttendance), @register(LivestreamRecording), @register(LivestreamQuestion), @register(LivestreamSession), LivestreamAttendanceAdmin, LivestreamQuestionAdmin, LivestreamRecordingAdmin, LivestreamSessionAdmin (+336 more)

### Community 4 - "Community 4"
Cohesion: 0.02
Nodes (292): path('admin/seats/') name='organization-seats', path('admin/users/<int:user_id>/promote/') name='admin-user-promote', path('admin/users/invite/') name='admin-invite-user', path('uploads/presign/') name='uploads-presign', path('uploads/quota/') name='uploads-quota', APIView, change_password(), @api_view(["GET"]) (+284 more)

### Community 5 - "Community 5"
Cohesion: 0.1
Nodes (235): AbstractUser, BadgeAdmin, CertificateAdmin, @register(SessionProgress), @register(Certificate), @register(Submission), @register(QuizSubmission), @register(Discussion) (+227 more)

### Community 6 - "Community 6"
Cohesion: 0.02
Nodes (144): ListModelMixin, AccountUserManager, Action, AssignmentType, attendance_percentage(), ContentSource, Conversation, @property (+136 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (86): DemoRequest, Update recording information after session ends, Tracks user sessions for security monitoring., UserSession, IsTascAdminUser, Custom permission to only allow instructors to edit their sessions., DemoRequestSerializer, Meta (+78 more)

### Community 8 - "Community 8"
Cohesion: 0.03
Nodes (57): @object(PesapalService, "_post"), @object(PesapalService, "verify_payment"), @object(PesapalService, "verify_payment"), @patch("apps.payments.views_pesapal.PesapalService.initialize_recurring_payment"), @patch("apps.payments.views_pesapal.PesapalService.handle_webhook"), @patch("apps.payments.views_pesapal.PesapalService.verify_payment"), @patch("apps.payments.views_pesapal.PesapalService.verify_payment"), @patch("apps.payments.views_pesapal.PesapalService.verify_payment") (+49 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (34): _build_description(), convert_to_user_timezone(), @staticmethod, @staticmethod, @staticmethod, @staticmethod, @staticmethod, @staticmethod (+26 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (7): BaseCommand, Command, Command, Management command to seed all 22 badge definitions. Usage: python manage.py see, Command, Command, Command

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (18): @staticmethod, _format_ddmmyyyy(), _pesapal_billing_address_for_user(), _pesapal_billing_str(), pesapal_get_request_query(), Pesapal v3 Service Mirrors the FlutterwaveService pattern in services/flutterwa, Pesapal recurring expects dates in dd-MM-yyyy., Register an IPN URL with Pesapal.         Returns { success, ipn_id, message }. (+10 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (23): @api_view(['POST']), @api_view(['POST']), @api_view(['GET']), @api_view(['POST']), @extend_schema(
    tags=['Accounts'],
    summary='Google OAuth Login',
    description='A..., @extend_schema(
    tags=['Accounts'],
    summary='Link Google Account',
    description='..., @extend_schema(
    tags=['Accounts'],
    summary='Unlink Google Account',
    description..., @extend_schema(
    tags=['Accounts'],
    summary='Get Google OAuth Status',
    descripti... (+15 more)

### Community 13 - "Community 13"
Cohesion: 0.12
Nodes (22): auto_create_certificate(), award_badges_on_certificate(), award_badges_on_discussion(), award_badges_on_enrollment(), award_badges_on_profile_update(), award_badges_on_quiz(), award_badges_on_review(), award_badges_on_submission_graded() (+14 more)

### Community 14 - "Community 14"
Cohesion: 0.09
Nodes (19): @override_settings(FRONTEND_BASE_URL="https://app.example.com"), @override_settings(FRONTEND_BASE_URL="https://app.example.com"), @override_settings(FRONTEND_BASE_URL="https://app.example.com"), @override_settings(FRONTEND_BASE_URL="https://app.example.com"), @override_settings(FRONTEND_BASE_URL="https://fe.example/"), @patch("apps.payments.views_pesapal.PesapalService.verify_payment"), @patch("apps.payments.views_pesapal.PesapalService.verify_payment"), @patch("apps.payments.views_pesapal.PesapalService.verify_payment") (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.31
Nodes (2): _auth(), SubscriptionMeViewTest

### Community 16 - "Community 16"
Cohesion: 0.29
Nodes (10): AppConfig, AccountsConfig, AuditConfig, CatalogueConfig, CommonConfig, LearningConfig, LivestreamConfig, MessagingConfig (+2 more)

### Community 17 - "Community 17"
Cohesion: 0.35
Nodes (10): _add_attempt_number_if_missing(), _add_unique_triple(), backwards(), _drop_submission_unique_constraints(), forwards(), Migration, Remove all UNIQUE constraints / unique indexes on learning_submission (not the P, Staging drift: table has session_id and unique(enrollment,session), no assignmen (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.31
Nodes (9): detect_provider(), _is_https(), Pure helpers for external video embedding (YouTube, Vimeo, Loom). Uses only std, Return True if URL uses https scheme., Detect video provider from URL. Returns lowercase provider name or None.     On, Convert a watch/share URL to an embed URL.     Returns None for unknown provide, Validate external video URL and return (provider, embed_url).     Raises ValueE, to_embed_url() (+1 more)

### Community 19 - "Community 19"
Cohesion: 0.22
Nodes (9): @extend_schema_field(serializers.CharField), @extend_schema_field(serializers.CharField(allow_null=True)), @extend_schema_field(serializers.CharField), @extend_schema_field(serializers.CharField), @extend_schema_field(serializers.CharField), @extend_schema_field(serializers.CharField), @extend_schema_field(serializers.CharField), @extend_schema_field(serializers.CharField) (+1 more)

### Community 20 - "Community 20"
Cohesion: 0.28
Nodes (6): Celery configuration for TASC LMS., check_and_notify_expiring_subscriptions(), @shared_task(bind=True), expire_overdue_subscriptions(), _generate_csv_data(), generate_report()

### Community 21 - "Community 21"
Cohesion: 0.22
Nodes (8): ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS").split(","), BASE_DIR = Path(__file__).resolve().parent.parent, DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField', DEFAULT_FROM_EMAIL = env(, get_list_from_env(), MAX_LOGIN_ATTEMPTS = env.int("MAX_LOGIN_ATTEMPTS", default=5), Django settings for config project.  Generated by 'django-admin startproject', Helper to parse comma-separated environment variables into a list.

### Community 22 - "Community 22"
Cohesion: 0.25
Nodes (2): get_active_membership_organization(), Return user's active org for org-scoped roles, else None.

### Community 23 - "Community 23"
Cohesion: 0.4
Nodes (4): backfill_content_source_and_external_video(), _derive_provider_embed_url(), Migration, Derive provider and embed URL directly inside migration     so the migration do

### Community 24 - "Community 24"
Cohesion: 0.33
Nodes (2): End the livestream session, Update progress based on completed sessions

### Community 25 - "Community 25"
Cohesion: 0.4
Nodes (2): PasswordComplexityValidator, Enforce uppercase, lowercase, digit, and special character requirements.

### Community 26 - "Community 26"
Cohesion: 0.4
Nodes (2): Migration, Create learning_quizsubmission and learning_quizanswer tables.  Migration 0004

### Community 27 - "Community 27"
Cohesion: 0.4
Nodes (4): organization_has_active_subscription(), Check if user has an active UserSubscription.     Uses is_active logic: status=, Check if organization has an active subscription (for org learners)., user_has_active_subscription()

### Community 28 - "Community 28"
Cohesion: 0.5
Nodes (1): Migration

### Community 29 - "Community 29"
Cohesion: 0.5
Nodes (1): Migration

### Community 30 - "Community 30"
Cohesion: 0.67
Nodes (2): main(), Run administrative tasks.

### Community 31 - "Community 31"
Cohesion: 0.67
Nodes (2): Test Meet creation with OAuth 2.0, test_with_oauth()

### Community 32 - "Community 32"
Cohesion: 0.67
Nodes (2): Migration, State-only migration: register the three livestream models with Django's migrat

### Community 33 - "Community 33"
Cohesion: 0.67
Nodes (2): Migration, No-op migration: 0001_initial already creates User with country, phone_number,

### Community 34 - "Community 34"
Cohesion: 0.67
Nodes (2): Migration, State-only migration: remove LivestreamSession, LivestreamAttendance, and Lives

### Community 35 - "Community 35"
Cohesion: 0.67
Nodes (2): IsEnrolledOrInstructor, Permission to allow access only to enrolled learners or instructor.

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
Nodes (1): Migration

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): Migration

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Migration

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): Migration

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Migration

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): Migration

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Migration

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): Migration

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Migration

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): Migration

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): ASGI config for config project.  It exposes the ASGI callable as a module-leve

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): WSGI config for config project.  It exposes the WSGI callable as a module-leve

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (0): 

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (0): 

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (1): path('')

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (1): path('')

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (1): path('')

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (0): 

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (1): path('')

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (1): path('auth/')

### Community 96 - "Community 96"
Cohesion: 1.0
Nodes (1): path('admin/')

### Community 97 - "Community 97"
Cohesion: 1.0
Nodes (1): path('notifications/')

### Community 98 - "Community 98"
Cohesion: 1.0
Nodes (1): path('superadmin/')

### Community 99 - "Community 99"
Cohesion: 1.0
Nodes (1): path('public/')

### Community 100 - "Community 100"
Cohesion: 1.0
Nodes (1): path('catalogue/')

### Community 101 - "Community 101"
Cohesion: 1.0
Nodes (1): path('learning/')

### Community 102 - "Community 102"
Cohesion: 1.0
Nodes (1): path('learner/')

### Community 103 - "Community 103"
Cohesion: 1.0
Nodes (1): path('payments/')

### Community 104 - "Community 104"
Cohesion: 1.0
Nodes (1): path('livestream/')

### Community 105 - "Community 105"
Cohesion: 1.0
Nodes (1): path('messaging/')

### Community 106 - "Community 106"
Cohesion: 1.0
Nodes (1): path('')

### Community 107 - "Community 107"
Cohesion: 1.0
Nodes (1): path('webhooks/')

### Community 108 - "Community 108"
Cohesion: 1.0
Nodes (1): path('admin/')

### Community 109 - "Community 109"
Cohesion: 1.0
Nodes (1): path('api/schema/') name='schema'

### Community 110 - "Community 110"
Cohesion: 1.0
Nodes (1): path('api/schema.json') name='schema-json'

### Community 111 - "Community 111"
Cohesion: 1.0
Nodes (1): path('api/docs/') name='swagger-ui'

### Community 112 - "Community 112"
Cohesion: 1.0
Nodes (1): path('documentation/') name='documentation'

### Community 113 - "Community 113"
Cohesion: 1.0
Nodes (1): path('api/redoc/') name='redoc'

### Community 114 - "Community 114"
Cohesion: 1.0
Nodes (1): path('api/v1/')

### Community 115 - "Community 115"
Cohesion: 1.0
Nodes (1): path('r"^(?!api/)(?!admin/)(?!documentation/).*$')

## Knowledge Gaps
- **624 isolated node(s):** `Run administrative tasks.`, `Test Meet creation with OAuth 2.0`, `@api_view(["GET"])`, `@permission_classes([AllowAny])`, `@api_view(["POST"])` (+619 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 36`** (2 nodes): `0003_user_email_verified_alter_user_country_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (2 nodes): `0004_user_role.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (2 nodes): `0006_user_failed_login_attempts_account_locked_until.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (2 nodes): `0007_add_login_otp_challenge.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (2 nodes): `0008_alter_user_managers.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (2 nodes): `0009_organization_industry_organization_settings.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (2 nodes): `0010_add_demo_request_model.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (2 nodes): `0011_business_testimonial.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (2 nodes): `0012_user_session.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (2 nodes): `0002_livestreamsession_livestreamrecording_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (2 nodes): `0004_course_access_duration_course_allow_self_enrollment.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (2 nodes): `0004_course_wizard_fields.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (2 nodes): `0005_merge_20260225_0836.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (2 nodes): `0006_alter_course_access_duration.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (2 nodes): `0007_add_session_asset_metadata.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (2 nodes): `0008_add_session_content_source_and_external_video_fields.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (2 nodes): `0010_add_module_model_and_session_module_fk.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (2 nodes): `0011_rename_catalogue_module_course_order_idx_catalogue_m_course__fe6513_idx.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (2 nodes): `0012_add_quiz_models.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (2 nodes): `0013_add_question_bank_models.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (2 nodes): `0014_add_assignment_model.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (2 nodes): `0015_coursereview.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (2 nodes): `0016_add_course_approval_request.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (2 nodes): `0017_course_rejection_reason.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (2 nodes): `0018_rename_catalogue_c_status_9a8f2c_idx_catalogue_c_status_9b807a_idx_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (2 nodes): `0019_quizquestion_explanation.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (2 nodes): `0020_sessionattachment.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (2 nodes): `0021_coursereview_helpful_count_coursereview_report_count.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (2 nodes): `0022_merge_20260328_0303.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (2 nodes): `0022_merge_20260328_0334.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (2 nodes): `0023_merge_20260328_2300.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (2 nodes): `0024_review_add_is_featured_is_rejected_change_default.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (2 nodes): `0002_initial.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (2 nodes): `0003_add_submission_model.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (2 nodes): `0004_quizanswer_quizsubmission_report_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (2 nodes): `0006_badge_userbadge.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (2 nodes): `0007_savedcourse.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (2 nodes): `0008_workshop.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (2 nodes): `0010_workshop_attendance.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (2 nodes): `0011_sessionprogress_video_position_seconds.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (2 nodes): `0002_alter_livestreamsession_platform.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (2 nodes): `0003_livestreamsession_calendar_channel_id_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (2 nodes): `0004_livestreamquestion.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (2 nodes): `0005_add_attended_absent_status.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (2 nodes): `0002_alter_conversation_options.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (2 nodes): `0002_payment_paymentwebhook_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (2 nodes): `0003_alter_payment_currency_alter_payment_payment_method.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (2 nodes): `0004_pesapalipn_alter_payment_currency_and_more.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (2 nodes): `0005_subscription_duration_days.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (2 nodes): `0006_payment_success_email_sent.py`, `Migration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (2 nodes): `asgi.py`, `ASGI config for config project.  It exposes the ASGI callable as a module-leve`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (2 nodes): `wsgi.py`, `WSGI config for config project.  It exposes the WSGI callable as a module-leve`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `test_google_creds.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `test_public_api.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `path('')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `path('')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `path('')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `api_urls.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `path('')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (1 nodes): `path('auth/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 96`** (1 nodes): `path('admin/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 97`** (1 nodes): `path('notifications/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 98`** (1 nodes): `path('superadmin/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 99`** (1 nodes): `path('public/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 100`** (1 nodes): `path('catalogue/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 101`** (1 nodes): `path('learning/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 102`** (1 nodes): `path('learner/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 103`** (1 nodes): `path('payments/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 104`** (1 nodes): `path('livestream/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 105`** (1 nodes): `path('messaging/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 106`** (1 nodes): `path('')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 107`** (1 nodes): `path('webhooks/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 108`** (1 nodes): `path('admin/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 109`** (1 nodes): `path('api/schema/') name='schema'`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 110`** (1 nodes): `path('api/schema.json') name='schema-json'`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 111`** (1 nodes): `path('api/docs/') name='swagger-ui'`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 112`** (1 nodes): `path('documentation/') name='documentation'`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 113`** (1 nodes): `path('api/redoc/') name='redoc'`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 114`** (1 nodes): `path('api/v1/')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 115`** (1 nodes): `path('r"^(?!api/)(?!admin/)(?!documentation/).*$')`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Enrollment` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 8`, `Community 10`, `Community 24`?**
  _High betweenness centrality (0.136) - this node is a cross-community bridge._
- **Why does `Course` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 8`, `Community 10`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `UserSubscription` connect `Community 1` to `Community 0`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 15`, `Community 27`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Are the 634 inferred relationships involving `Enrollment` (e.g. with `ManagerOrganizationSettingsView` and `ManagerBillingPlanView`) actually correct?**
  _`Enrollment` has 634 INFERRED edges - model-reasoned connections that need verification._
- **Are the 545 inferred relationships involving `Course` (e.g. with `QuestionCategoryAdmin` and `BankQuestionAdmin`) actually correct?**
  _`Course` has 545 INFERRED edges - model-reasoned connections that need verification._
- **Are the 384 inferred relationships involving `UserSubscription` (e.g. with `LoginView` and `VerifyOTPView`) actually correct?**
  _`UserSubscription` has 384 INFERRED edges - model-reasoned connections that need verification._
- **Are the 363 inferred relationships involving `Quiz` (e.g. with `OrganizationSuperadminViewSet` and `UserSuperadminViewSet`) actually correct?**
  _`Quiz` has 363 INFERRED edges - model-reasoned connections that need verification._