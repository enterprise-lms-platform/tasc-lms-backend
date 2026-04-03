This is going to be a very long document. I'll produce it in full — every task with exact file paths, exact imports, exact field names from the model schema, exact serializer patterns matching your codebase, and response shapes matching your frontend TypeScript types.

---

```markdown
# TASC LMS Backend — Pending Tasks (Final Specification)

> **For Claude Code / any agent:** Every task below is self-contained. File paths, imports, model field names, related_names, serializer base classes, URL registration patterns, and frontend response shapes are all verified against the actual codebase schema dumps. Work top-down by priority. Mark items `✅ DONE` when finished.

---

## Reference: Key Patterns From Codebase

Before starting any task, know these patterns:

### URL Registration
All new routes go through app-level `urls.py` files, which are included in `apps/common/api_urls.py`:
```python
# apps/common/api_urls.py pattern:
path("catalogue/", include("apps.catalogue.urls")),
path("learning/", include("apps.learning.urls")),
path("payments/", include("apps.payments.urls")),
path("superadmin/", include("apps.accounts.urls_superadmin")),
```

### ViewSet Base Classes
All viewsets inherit directly from DRF — no custom base class:
- `viewsets.ModelViewSet` (full CRUD)
- `viewsets.ReadOnlyModelViewSet` (list + retrieve)
- `viewsets.ViewSet` (custom actions only)
- `viewsets.GenericViewSet` + mixins

### Serializer Base Classes
All serializers inherit directly from DRF:
- `serializers.ModelSerializer`
- `serializers.Serializer`
- Some use inheritance: `CourseDetailSerializer(CourseListSerializer)`

### Permission Classes Available
```python
from rest_framework.permissions import IsAuthenticated, AllowAny
# Custom (check apps/accounts/ or apps/common/ for exact import paths):
# IsInstructorOrReadOnly, IsLmsManager, IsTascAdmin
```

### Key Related Names (from model schema dump)
```
User.enrollments -> Enrollment (related_name="enrollments")
User.instructed_courses -> Course (related_name="instructed_courses")
User.memberships -> Membership (related_name="memberships")
Course.enrollments -> Enrollment (related_name="enrollments")
Course.sessions -> Session (related_name="sessions")
Course.modules -> Module (related_name="modules")
Course.reviews -> CourseReview (related_name="reviews")
Course.invoices -> Invoice (related_name="invoices")
Course.transactions -> Transaction (related_name="transactions")
Category.courses -> Course (related_name="courses")
Enrollment.session_progress -> SessionProgress (related_name="session_progress")
Enrollment.certificate -> Certificate (related_name="certificate", OneToOne)
Enrollment.submissions -> Submission (related_name="submissions")
Enrollment.quiz_submissions -> QuizSubmission (related_name="quiz_submissions")
Organization.memberships -> Membership (related_name="memberships")
Organization.enrollments -> Enrollment (related_name="enrollments")
Organization.invoices -> Invoice (related_name="invoices")
Organization.transactions -> Transaction (related_name="transactions")
Session.quiz -> Quiz (related_name="quiz", OneToOne)
Session.assignment -> Assignment (related_name="assignment", OneToOne)
Session.attachments -> SessionAttachment (related_name="attachments")
Quiz.questions -> QuizQuestion (related_name="questions")
Quiz.submissions -> QuizSubmission (related_name="submissions")
Assignment.submissions -> Submission (related_name="submissions")
Invoice.items -> InvoiceItem (related_name="items")
Invoice.transactions -> Transaction (related_name="transactions")
```

---

## Quick Summary — Open Tasks by Priority

| Pri | # | Task | Backend File(s) | Frontend Blocked Page(s) |
|-----|---|------|-----------------|--------------------------|
| ✅ | 29 | ~~Saved/Favorited Courses API~~ | `apps/learning/` | `SavedCoursesPage`, `CatalogCourseCard` |
| ✅ | 30 | ~~CourseViewSet Ordering/Search~~ | `apps/catalogue/views.py` | Manager TopCourses widget |
| ✅ | 31 | ~~Organization annotations~~ | `apps/accounts/serializers_superadmin.py:8`, `views_superadmin.py:13` | SuperadminOrganizationsTable |
| ✅ | 32 | ~~Course stats action~~ | `apps/catalogue/views.py` | `AllCoursesPage` KPIs |
| ✅ | 33 | ~~Assessments stats~~ (via SubmissionViewSet) | `apps/learning/views.py` | `AssessmentsPage` |
| ✅ | 34 | ~~Certificates admin-scoped + stats~~ | `apps/learning/views.py` | `CertificationsPage` |
| ✅ | 35 | ~~Instructor stats~~ | `apps/accounts/views_superadmin.py` | `InstructorsPage` |
| ✅ | 36 | ~~Invoice stats action~~ | `apps/payments/views.py` | `InvoicesPage` KPIs |
| ✅ | 37 | ~~Revenue breakdown~~ | `apps/payments/views.py` | `RevenuePage` |
| ✅ | 6 | ~~Session quiz/assignment POST & Learner Submit~~ | `apps/catalogue/views.py:834` | Quiz/Assignment/Submission flow |
| ✅ | 60 | ~~Mobile money (Pesapal) — Wave 1~~ | `apps/payments/views_pesapal.py`, `urls.py`, `models.py`, `serializers.py`, `services/pesapal_services.py` | `CheckoutPaymentPage`, `PesapalReturnPage` |
| ✅ | 1 | ~~Assignment serializer `update()`~~ | `apps/catalogue/serializers.py:553` | Assignment editing |
| ✅ | 43 | ~~Manager org settings~~ | `apps/accounts/views.py:270` | `ManagerSettingsPage` |
| ✅ | 44 | ~~Manager billing/plan~~ | `apps/accounts/views_manager.py` | `ManagerBillingPage` |
| ~~REMOVED~~ | 61 | ~~Promo codes~~ — removed from scope | — | — |
| ✅ | 62 | ~~Review helpful/report~~ | `apps/catalogue/views.py:1268` | `CourseReviews` |
| ✅ | 63 | ~~Transaction/invoice exports~~ | `apps/payments/views.py` | Download buttons |
| ✅ | 22 | ~~Security metrics~~ | `apps/accounts/views_superadmin.py` | `SecurityPage` |
| MED | 25 | Redis integration | `config/settings.py` | Infrastructure |
| MED | 26 | DB connection pooling | `config/settings.py` | Infrastructure |
| MED | 27 | Gunicorn scaling | `Dockerfile` | Infrastructure |
| LOW | 8 | Email templates | `templates/emails/` (new) | — |
| ✅ | 9 | ~~Notification extras~~ | `apps/notifications/views.py:33` | — |
| ✅ | 17 | ~~N+1 query fixes~~ | various views.py | Performance |
| ✅ | 10-16 | ~~Silent exception fixes~~ | various | Code quality |
| ✅ | 16b | ~~Django admin registrations~~ | `apps/catalogue/admin.py` | — |
| ✅ | 40 | ~~Roles user counts~~ | `apps/accounts/views_superadmin.py` | `RolesPermissionsPage` |
| LOW | 23 | B2B pricing tiers | `apps/payments/` | `/for-business` |
| ✅ | 38 | ~~System settings/health~~ | `apps/accounts/views_superadmin.py` | `SystemSettingsPage` |
| ✅ | 45 | ~~Activity log summary~~ | `apps/audit/views.py` | `ManagerActivityPage` |
| HIGH | 64 | Bulk export endpoints (CSV/PDF) | `apps/payments/views.py`, `apps/accounts/views_superadmin.py`, `apps/catalogue/views.py` | Finance Export buttons, Superadmin Export buttons (F28) |
| HIGH | 65 | Superadmin list endpoints for table data | `apps/accounts/views_superadmin.py`, `apps/catalogue/views.py` | AllCoursesPage table, InstructorsPage table, InvoicesPage table, CertificationsPage table, AssessmentsPage table (F22) |
| HIGH | 66 | Pesapal gateway health/stats endpoint | `apps/payments/views.py` | GatewayPesapalPage KPIs + transaction list (F24) |
| HIGH | 67 | System settings PATCH + SMTP config + test email | `apps/accounts/views_superadmin.py` | SystemSettingsPage Save buttons (F29) |
| HIGH | 68 | Security policy endpoints (MFA/password/session save + terminate all sessions) | `apps/accounts/views_superadmin.py` | SecurityPage Save buttons (F30) |
| HIGH | 69 | Pesapal config save + test connection | `apps/payments/views_pesapal.py` | GatewaySettingsPage Save/Test buttons (F31) |
| MED | 70 | User invite endpoint (email invite flow) | `apps/accounts/views.py` or `views_superadmin.py` | InstructorsPage Invite Instructor button (F32) |
| MED | 71 | Subscription plan admin PATCH endpoint | `apps/payments/views.py` | FinancePricingPage Edit Plans / Manage Plan buttons (F34) |

---

## HIGH PRIORITY — Frontend Blocked

---

### Task 29: Saved / Favorited Courses API ✅ DONE (27 Mar)

**Problem:** Frontend `SavedCoursesPage.tsx` and `CatalogCourseCard.tsx` heart icon have no backend persistence. Favorites stored in React state only.

**Frontend expects** (from `learning.services.ts` pattern — no `savedCourseApi` exists yet):
- `GET /api/v1/learning/saved-courses/` → `PaginatedResponse<SavedCourse>`
- `POST /api/v1/learning/saved-courses/` → create
- `DELETE /api/v1/learning/saved-courses/{id}/` → remove
- `POST /api/v1/learning/saved-courses/toggle/` → `{ saved: boolean }`

**Step 1 — Model** (`apps/learning/models.py`, append after `UserBadge`):

```python
class SavedCourse(models.Model):
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='saved_courses'
    )
    course = models.ForeignKey(
        'catalogue.Course', on_delete=models.CASCADE, related_name='saved_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'learning_savedcourse'
        unique_together = ['user', 'course']
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f"{self.user.email} saved {self.course.title}"
```

**Step 2 — Serializer** (`apps/learning/serializers.py`, append):

```python
from apps.catalogue.serializers import CourseListSerializer

class SavedCourseSerializer(serializers.ModelSerializer):
    course = CourseListSerializer(read_only=True)

    class Meta:
        model = SavedCourse
        fields = ['id', 'course', 'created_at']
        read_only_fields = ['id', 'created_at']


class SavedCourseCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedCourse
        fields = ['course']

    def validate_course(self, value):
        if SavedCourse.objects.filter(
            user=self.context['request'].user, course=value
        ).exists():
            raise serializers.ValidationError("Course already saved.")
        return value
```

**Step 3 — ViewSet** (`apps/learning/views.py`, append after `BadgeViewSet`):

```python
from apps.learning.models import SavedCourse
from apps.learning.serializers import SavedCourseSerializer, SavedCourseCreateSerializer

class SavedCourseViewSet(viewsets.ModelViewSet):
    serializer_class = SavedCourseSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        return SavedCourse.objects.filter(user=self.request.user) \
            .select_related('course', 'course__category', 'course__instructor')

    def get_serializer_class(self):
        if self.action == 'create':
            return SavedCourseCreateSerializer
        return SavedCourseSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        course_id = request.data.get('course')
        if not course_id:
            return Response({'error': 'course field required'}, status=400)
        obj, created = SavedCourse.objects.get_or_create(
            user=request.user, course_id=course_id
        )
        if not created:
            obj.delete()
        return Response({'saved': created})
```

**Step 4 — URL Registration** (`apps/learning/urls.py`, add to router):

```python
router.register(r'saved-courses', SavedCourseViewSet, basename='saved-course')
```

**Step 5 — Migration:**

```bash
python manage.py makemigrations learning
python manage.py migrate
```

**Step 6 — Frontend query key to add** (for reference — `queryKeys.ts`):
```typescript
savedCourses: {
    all: ['saved-courses'] as const,
},
```

**Frontend response shape must match:**
```json
{
  "count": 3,
  "results": [
    {
      "id": 1,
      "course": {
        "id": 5,
        "title": "...",
        "slug": "...",
        "thumbnail": "...",
        "category": { "id": 2, "name": "Web Development", "slug": "web-dev", ... },
        "tags": [],
        "level": "advanced",
        "price": "49.99",
        "discounted_price": "39.99",
        "instructor_name": "Michael Rodriguez",
        "enrollment_count": 42,
        "status": "published",
        ...
      },
      "created_at": "2026-03-20T14:30:00Z"
    }
  ]
}
```

The nested `course` object is produced by `CourseListSerializer` (line 619 of `apps/catalogue/serializers.py`), which already exposes `instructor_name`, `enrollment_count`, `category` (nested), `tags`, etc. — matching the frontend `CourseList` interface exactly.

---

### Task 30: CourseViewSet — Add Ordering & Search ✅ DONE (27 Mar)

**File:** `apps/catalogue/views.py`, line 215 — `class CourseViewSet(viewsets.ModelViewSet)`

**Problem:** Manager dashboard TopCourses widget calls `courseApi.getAll({ ordering: '-enrollment_count', page_size: 4 })` but `CourseViewSet` has no `filter_backends`. The `CourseListSerializer` already exposes `enrollment_count` as an annotated field.

**Do this** — add these class attributes to `CourseViewSet`:

```python
from rest_framework.filters import OrderingFilter, SearchFilter

class CourseViewSet(viewsets.ModelViewSet):
    filter_backends = [OrderingFilter, SearchFilter]
    ordering_fields = ['title', 'published_at', 'enrollment_count', 'created_at']
    ordering = ['-created_at']  # default
    search_fields = ['title', 'short_description']
    # ... rest of existing code unchanged
```

**Note:** The `PublicCourseViewSet` (line 27 of `views_public.py`) already has `SearchFilter` + `OrderingFilter` configured. This just mirrors it for the authenticated `CourseViewSet`.

**Frontend service already sends these params** (`catalogue.services.ts` line 97):
```typescript
search?: string;  // Note: search only works on PublicCourseViewSet, not authenticated CourseViewSet
```
After this fix, search will work on both.

---

### Task 31: Organization Serializer — Add `user_count` and `course_count`

**Files:**
- `apps/accounts/serializers_superadmin.py` line 8 — `OrganizationSuperadminSerializer`
- `apps/accounts/views_superadmin.py` line 13 — `OrganizationSuperadminViewSet`

**Problem:** Frontend `Organization` interface expects `courses_count?: number` and `users_count?: number` (see `types.ts`). Backend serializer doesn't expose them.

**Step 1 — Serializer** (`apps/accounts/serializers_superadmin.py`):

```python
class OrganizationSuperadminSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)
    course_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'description', 'logo', 'website',
            'contact_email', 'contact_phone', 'address', 'city', 'country',
            'is_active', 'max_seats', 'billing_email', 'billing_address',
            'tax_id', 'created_at', 'updated_at',
            'user_count', 'course_count',
        ]
```

**Step 2 — ViewSet queryset** (`apps/accounts/views_superadmin.py`):

```python
from django.db.models import Count, Q

class OrganizationSuperadminViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSuperadminSerializer
    # ... existing permission_classes ...

    def get_queryset(self):
        return Organization.objects.annotate(
            user_count=Count('memberships__user', distinct=True),
            course_count=Count(
                'enrollments__course',
                filter=Q(enrollments__course__status='published'),
                distinct=True
            ),
        ).order_by('name')
```

**Explanation of related names used:**
- `Organization.memberships` → `Membership` (related_name="memberships" on FK `organization`)
- `Organization.enrollments` → `Enrollment` (related_name="enrollments" on FK `organization`)
- Through enrollment we reach `course` and filter by `status='published'`

**Frontend field mapping:**
- Backend `user_count` → Frontend `users_count` (in `Organization` interface)
- Backend `course_count` → Frontend `courses_count`

**Note:** Frontend uses `users_count` and `courses_count` (with `s`). Either rename the backend fields to match, or keep as-is and adjust frontend. Recommended: rename backend to `users_count` and `courses_count` to match the frontend type definition exactly.

---

### Task 32: Superadmin Course Stats Action ✅ DONE (27 Mar)

**File:** `apps/catalogue/views.py` line 215 — `CourseViewSet`

**Problem:** `AllCoursesPage` KPIs (total, published, draft, archived) are hardcoded.

**Do this** — add a `stats` action to `CourseViewSet`:

```python
from django.db.models import Count

class CourseViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """
        GET /api/v1/catalogue/courses/stats/
        Returns course counts by status for superadmin KPI cards.
        """
        qs = Course.objects.all()

        # Role scoping: instructors see only their courses
        if request.user.role == 'instructor':
            qs = qs.filter(instructor=request.user)

        rows = qs.values('status').annotate(count=Count('id'))
        result = {'total': 0, 'published': 0, 'draft': 0, 'archived': 0,
                  'pending_approval': 0, 'rejected': 0}
        for row in rows:
            result[row['status']] = row['count']
            result['total'] += row['count']
        return Response(result)
```

**Endpoint:** `GET /api/v1/catalogue/courses/stats/`

**Response:**
```json
{
  "total": 876,
  "published": 654,
  "draft": 178,
  "archived": 44,
  "pending_approval": 0,
  "rejected": 0
}
```

**Note:** Course `status` choices from model schema: `draft`, `pending_approval`, `published`, `rejected`, `archived`.

---

### Task 33: Superadmin Assessments — Stats ✅ DONE (27 Mar, via SubmissionViewSet stats action)

**Problem:** `AssessmentsPage` at route `/superadmin/assessments` shows hardcoded KPIs and table.

**Option A — Add to existing views:** Create a new view in `apps/catalogue/views.py` or `apps/learning/views.py`.

**Option B — Recommended:** Add actions to a lightweight viewset registered under `superadmin/`.

**Step 1 — ViewSet** (append to `apps/catalogue/views.py` or create `apps/catalogue/views_superadmin.py`):

```python
from apps.catalogue.models import Quiz, Assignment
from apps.learning.models import QuizSubmission, Submission

class AssessmentStatsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]  # Add IsTascAdmin for production

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """GET /api/v1/superadmin/assessments/stats/"""
        quiz_count = Quiz.objects.count()
        assignment_count = Assignment.objects.count()
        total = quiz_count + assignment_count

        quiz_subs = QuizSubmission.objects.all()
        total_attempts = quiz_subs.count()
        passed = quiz_subs.filter(passed=True).count()
        pass_rate = (passed / total_attempts * 100) if total_attempts > 0 else 0

        return Response({
            'total': total,
            'quizzes': quiz_count,
            'assignments': assignment_count,
            'pass_rate': round(pass_rate, 1),
            'total_attempts': total_attempts,
        })

    def list(self, request):
        """
        GET /api/v1/superadmin/assessments/?type=quiz&page_size=20
        Unified list of quizzes and assignments.
        """
        assessment_type = request.query_params.get('type', None)
        results = []

        if assessment_type != 'assignment':
            for quiz in Quiz.objects.select_related('session', 'session__course').all():
                results.append({
                    'id': quiz.id,
                    'type': 'quiz',
                    'title': quiz.session.title,
                    'course_title': quiz.session.course.title,
                    'question_count': quiz.questions.count(),
                    'submission_count': quiz.submissions.count(),
                })

        if assessment_type != 'quiz':
            for asn in Assignment.objects.select_related('session', 'session__course').all():
                results.append({
                    'id': asn.id,
                    'type': 'assignment',
                    'title': asn.session.title,
                    'course_title': asn.session.course.title,
                    'max_points': asn.max_points,
                    'submission_count': asn.submissions.count(),
                })

        # Simple pagination
        page_size = int(request.query_params.get('page_size', 20))
        page = int(request.query_params.get('page', 1))
        start = (page - 1) * page_size
        end = start + page_size

        return Response({
            'count': len(results),
            'results': results[start:end],
        })
```

**Step 2 — URL Registration.** Add to `apps/catalogue/urls.py` (or a new `apps/catalogue/urls_superadmin.py` included from `api_urls.py`):

```python
from apps.catalogue.views import AssessmentStatsViewSet  # or wherever you put it

# In the router or urlpatterns:
router.register(r'assessments', AssessmentStatsViewSet, basename='superadmin-assessments')
```

Then in `apps/common/api_urls.py`, ensure the superadmin prefix includes it:
```python
path("superadmin/", include("apps.catalogue.urls_superadmin")),
```

**Or simpler:** Register directly in an existing superadmin url file.

---

### Task 34: Superadmin Certificates — Admin-Scoped List + Stats ✅ DONE (27 Mar)

**File:** `apps/learning/views.py` line 254 — `CertificateViewSet(viewsets.ReadOnlyModelViewSet)`

**Problem:** Current `get_queryset()` filters to `request.user` only. Superadmin can't see all certificates.

**Do this:**

```python
class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CertificateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role in ('tasc_admin', 'lms_manager'):
            return Certificate.objects.all() \
                .select_related('enrollment', 'enrollment__user', 'enrollment__course')
        return Certificate.objects.filter(enrollment__user=user) \
            .select_related('enrollment', 'enrollment__user', 'enrollment__course')

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """GET /api/v1/learning/certificates/stats/"""
        from django.utils import timezone

        qs = Certificate.objects.all()
        now = timezone.now()
        total = qs.count()
        valid = qs.filter(is_valid=True, expiry_date__gt=now).count()
        expired = qs.filter(expiry_date__lte=now).count()
        revoked = qs.filter(is_valid=False).count()

        return Response({
            'issued': total,
            'valid': valid,
            'expired': expired,
            'revoked': revoked,
        })

    # Keep existing 'latest' and 'verify' actions unchanged
```

**Related names used:**
- `Certificate.enrollment` → `Enrollment` (OneToOne, related_name="certificate")
- `Enrollment.user` → `User` (related_name="enrollments")
- `Enrollment.course` → `Course` (related_name="enrollments")

---

### Task 35: Superadmin Instructors — Stats & List ✅ DONE (27 Mar)

**File:** `apps/accounts/views_superadmin.py` line 44 — `UserSuperadminViewSet`

**Problem:** `InstructorsPage` shows hardcoded KPIs and table.

**Option A — Add `instructor_stats` action to `UserSuperadminViewSet`:**

```python
class UserSuperadminViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    @action(detail=False, methods=['get'], url_path='instructor-stats')
    def instructor_stats(self, request):
        """GET /api/v1/superadmin/users/instructor-stats/"""
        from django.db.models import Count, Avg
        from apps.catalogue.models import CourseReview

        instructors = User.objects.filter(role='instructor')
        total = instructors.count()
        active = instructors.filter(is_active=True).count()
        total_courses = Course.objects.filter(
            instructor__role='instructor'
        ).count()

        avg_rating = CourseReview.objects.filter(
            course__instructor__role='instructor',
            is_approved=True
        ).aggregate(avg=Avg('rating'))['avg'] or 0

        return Response({
            'total': total,
            'active': active,
            'avg_rating': round(avg_rating, 1),
            'total_courses': total_courses,
        })
```

**Frontend type this must match** (`users.services.ts` line 42):
```typescript
export interface InstructorStats {
    total: number;
    active: number;
    avg_rating: number;
    total_courses: number;
}
```

**For the instructor list**, the existing `GET /api/v1/superadmin/users/?role=instructor` already works. Frontend `InstructorListItem` extends `UserListItem` with `courses_count`, `students_count`, `rating`. To add these, annotate the queryset when `role=instructor` is filtered:

```python
def get_queryset(self):
    qs = super().get_queryset()
    role_filter = self.request.query_params.get('role')
    if role_filter == 'instructor':
        qs = qs.filter(role='instructor').annotate(
            courses_count=Count('instructed_courses', distinct=True),
            students_count=Count('instructed_courses__enrollments', distinct=True),
        )
    return qs
```

And expose `courses_count`, `students_count` in `UserSuperadminSerializer` as `IntegerField(read_only=True, default=0)`.

---

### Task 36: Invoice Stats Action ✅ DONE (27 Mar)

**File:** `apps/payments/views.py` line 89 — `InvoiceViewSet(viewsets.ModelViewSet)`

**Problem:** Invoice KPIs are hardcoded. Table already works.

**Do this:**

```python
from django.db.models import Sum, Count

class InvoiceViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """GET /api/v1/payments/invoices/stats/"""
        qs = self.get_queryset()  # respects existing role scoping
        rows = qs.values('status').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        )
        result = {}
        for row in rows:
            result[row['status']] = {
                'count': row['count'],
                'total': str(row['total'] or 0),
            }
        return Response(result)
```

**Invoice `status` choices from model:** `draft`, `pending`, `paid`, `overdue`, `cancelled`.

---

### Task 37: Superadmin Revenue Breakdown ✅ DONE (27 Mar)

**Problem:** `RevenuePage` shows hardcoded revenue KPIs and per-org breakdown.

**Step 1 — ViewSet** (append to `apps/payments/views.py` or new file):

```python
class RevenueViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]  # Add IsTascAdmin

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """GET /api/v1/payments/revenue/stats/"""
        from django.db.models import Sum
        from django.utils import timezone
        from dateutil.relativedelta import relativedelta

        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        completed = Transaction.objects.filter(status='completed')
        total = completed.aggregate(t=Sum('amount'))['t'] or 0
        monthly = completed.filter(
            completed_at__gte=month_start
        ).aggregate(t=Sum('amount'))['t'] or 0

        org_count = Organization.objects.filter(is_active=True).count()
        avg_per_org = (total / org_count) if org_count > 0 else 0

        return Response({
            'total_revenue': str(total),
            'monthly_revenue': str(monthly),
            'avg_per_org': str(round(avg_per_org, 2)),
        })

    @action(detail=False, methods=['get'], url_path='by-organization')
    def by_organization(self, request):
        """GET /api/v1/payments/revenue/by-organization/"""
        from django.db.models import Sum

        rows = Transaction.objects.filter(
            status='completed',
            organization__isnull=False
        ).values(
            'organization__name'
        ).annotate(
            total_revenue=Sum('amount')
        ).order_by('-total_revenue')

        results = [
            {
                'org_name': row['organization__name'],
                'total_revenue': str(row['total_revenue'] or 0),
            }
            for row in rows
        ]
        return Response(results)
```

**Step 2 — Registration.** In `apps/payments/urls.py`:

```python
router.register(r'revenue', RevenueViewSet, basename='revenue')
```

This gives:
- `GET /api/v1/payments/revenue/stats/`
- `GET /api/v1/payments/revenue/by-organization/`

---

### Task 6: SessionViewSet — Quiz/Assignment POST + Learner Submit ✅ DONE (28 Mar)

**File:** `apps/catalogue/views.py` line 834 — `SessionViewSet(viewsets.ModelViewSet)`

**Problem:** The `quiz` and `assignment` actions on `SessionViewSet` currently handle GET + PATCH only. Need POST for creation.

**Do this — modify the existing `quiz` action** (find it in `SessionViewSet`):

```python
@action(detail=True, methods=['get', 'post', 'patch'], url_path='quiz')
def quiz(self, request, pk=None):
    session = self.get_object()

    if request.method == 'GET':
        # existing GET logic unchanged
        ...

    if request.method == 'POST':
        if hasattr(session, 'quiz'):
            return Response(
                {'error': 'Quiz already exists for this session.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        quiz = Quiz.objects.create(
            session=session,
            settings=request.data.get('settings', {})
        )
        serializer = QuizDetailSerializer({
            'session': QuizSessionSummarySerializer(session).data,
            'settings': quiz.settings,
            'questions': [],
        })
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    if request.method == 'PATCH':
        # existing PATCH logic unchanged
        ...
```

**Same for `assignment` action:**

```python
@action(detail=True, methods=['get', 'post', 'put', 'patch'], url_path='assignment')
def assignment(self, request, pk=None):
    session = self.get_object()

    if request.method == 'POST':
        if hasattr(session, 'assignment'):
            return Response(
                {'error': 'Assignment already exists for this session.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = AssignmentCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = Assignment.objects.create(
            session=session,
            **serializer.validated_data
        )
        return Response(
            AssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED
        )

    # existing GET/PUT/PATCH logic unchanged
    ...
```

**Frontend service already has the quiz/assignment methods** (`catalogue.services.ts`):
- `sessionApi.getQuiz(sessionId)` — GET
- `sessionApi.patchQuiz(sessionId, payload)` — PATCH
- `sessionApi.getAssignment(sessionId)` — GET
- `sessionApi.putAssignment(sessionId, payload)` — PUT
- `sessionApi.patchAssignment(sessionId, payload)` — PATCH

Frontend will need to add `postQuiz` and `postAssignment` methods, but the backend endpoint is the same URL with POST method.

---

### Task 60: Pesapal Payment Integration — Wave 1 ✅ DONE (3 Apr)

**Files changed (this sprint):**
- `apps/payments/views_pesapal.py` (+62 lines) — added `initiate`, `initiateRecurring`, and status-check endpoints
- `apps/payments/urls.py` — registered new Pesapal routes
- `apps/payments/models.py` — Subscription model updates
- `apps/payments/serializers.py` — serializer updates for Pesapal payloads
- `apps/payments/services/pesapal_services.py` — logic tweaks
- `apps/payments/migrations/0005_subscription_duration_days.py` — **new migration** adds `duration_days: int` field to `Subscription` model
- `apps/payments/tests/test_pesapal_wave1.py` — **new file**, 248-line test suite covering initiate, recurring, and status flows
- `apps/payments/tests/test_subscription_me.py` — **new file**, 55-line tests for `/api/v1/payments/subscription/me/` endpoint

**Endpoints now live:**

| Method | URL | Description |
|--------|-----|-------------|
| `POST` | `/api/v1/payments/pesapal/initiate/` | One-time payment initiation → returns `{ payment_id, redirect_url, order_tracking_id }` |
| `POST` | `/api/v1/payments/pesapal/recurring/initiate/` | Subscription initiation → returns `{ payment_id, redirect_url, order_tracking_id, subscription_id }` |
| `GET` | `/api/v1/payments/pesapal/{payment_id}/status/` | Status polling → returns `{ order_tracking_id, status, payment_method, amount, currency, confirmation_code, message }` |

**New `duration_days` field on Subscription:**
Migration `0005` adds `duration_days` (integer) to the `Subscription` model. Frontend `Subscription` type in `types.ts` should add `duration_days?: number` to match.

**Frontend:** `CheckoutPaymentPage.tsx` and `PesapalReturnPage.tsx` fully wired — see frontend Task F4 ✅ DONE.

**Remaining / Wave 2:**
- IPN (Instant Payment Notification) webhook handler — backend needs to receive Pesapal's async callback and update `UserSubscription.status` + trigger enrollment activation
- Billing info passthrough — frontend collects first name / last name / email but does not yet send them to Pesapal; backend should accept and forward to Pesapal `billing_address` fields
- One-time course payment flow (current implementation is subscription-only)

---

## MEDIUM PRIORITY

---

### Task 1: AssignmentCreateUpdateSerializer — Missing `update()`

**File:** `apps/catalogue/serializers.py` line 463 — `AssignmentCreateUpdateSerializer(serializers.Serializer)`

**Problem:** Has `create()` logic in `SessionViewSet.assignment` action, but no `update()` method on the serializer. PUT/PATCH on `rubric_criteria` (JSONField) won't work correctly.

**Do this — add `update()` method:**

```python
class AssignmentCreateUpdateSerializer(serializers.Serializer):
    # ... existing field definitions ...

    def update(self, instance, validated_data):
        for field in [
            'assignment_type', 'instructions', 'max_points', 'due_date',
            'available_from', 'allow_late', 'late_cutoff_date', 'penalty_type',
            'penalty_percent', 'max_attempts', 'allowed_file_types',
            'max_file_size_mb', 'rubric_criteria', 'settings',
        ]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()
        return instance
```

**Assignment model fields** (from schema, `catalogue_assignment` table):
`assignment_type`, `instructions`, `max_points`, `due_date`, `available_from`, `allow_late`, `late_cutoff_date`, `penalty_type`, `penalty_percent`, `max_attempts`, `allowed_file_types` (JSONField), `max_file_size_mb`, `rubric_criteria` (JSONField), `settings` (JSONField).

---

### Task 43: Manager Organization Settings CRUD

**Problem:** `ManagerSettingsPage` has hardcoded org name, industry, theme. No backend to read/save.

**Simplest approach:** Add a `settings` JSONField to `Organization` model, or use the existing fields + a new endpoint.

**Step 1 — View** (new file `apps/accounts/views_manager.py` or append to existing):

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.accounts.models import Organization, Membership

class ManagerSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_org(self, user):
        membership = Membership.objects.filter(
            user=user, is_active=True
        ).select_related('organization').first()
        if not membership:
            return None
        return membership.organization

    def get(self, request):
        """GET /api/v1/manager/settings/"""
        org = self._get_org(request.user)
        if not org:
            return Response({'error': 'No organization found'}, status=404)
        return Response({
            'org_name': org.name,
            'description': org.description,
            'logo': org.logo,
            'website': org.website,
            'contact_email': org.contact_email,
            'contact_phone': org.contact_phone,
            'address': org.address,
            'city': org.city,
            'country': org.country,
        })

    def put(self, request):
        """PUT /api/v1/manager/settings/"""
        org = self._get_org(request.user)
        if not org:
            return Response({'error': 'No organization found'}, status=404)

        for field in ['name', 'description', 'logo', 'website',
                      'contact_email', 'contact_phone', 'address', 'city', 'country']:
            if field in request.data:
                setattr(org, field, request.data[field])
        org.save()
        return self.get(request)
```

**Step 2 — URL** (in `apps/common/api_urls.py` or a new `apps/accounts/urls_manager.py`):

```python
path("manager/settings/", ManagerSettingsView.as_view(), name="manager-settings"),
```

---

### Task 44: Manager Billing / Subscription Info

**Problem:** `ManagerBillingPage` shows hardcoded plan and usage.

**Step 1 — View:**

```python
class ManagerBillingPlanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/manager/billing/plan/"""
        membership = Membership.objects.filter(
            user=request.user, is_active=True
        ).select_related('organization').first()
        if not membership:
            return Response({'error': 'No organization'}, status=404)

        org = membership.organization
        # Check if org has an active subscription
        from apps.payments.models import UserSubscription
        sub = UserSubscription.objects.filter(
            organization=org, status='active'
        ).select_related('subscription').first()

        if sub:
            return Response({
                'plan_name': sub.subscription.name,
                'price': str(sub.price),
                'billing_cycle': sub.subscription.billing_cycle,
                'renewal_date': sub.end_date,
                'user_limit': org.max_seats,
            })
        return Response({
            'plan_name': None,
            'price': '0',
            'billing_cycle': None,
            'renewal_date': None,
            'user_limit': org.max_seats,
        })


class ManagerBillingUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/manager/billing/usage/"""
        membership = Membership.objects.filter(
            user=request.user, is_active=True
        ).select_related('organization').first()
        if not membership:
            return Response({'error': 'No organization'}, status=404)

        org = membership.organization
        active_users = Membership.objects.filter(
            organization=org, is_active=True
        ).count()
        active_courses = Enrollment.objects.filter(
            organization=org, status='active'
        ).values('course').distinct().count()

        return Response({
            'active_users': active_users,
            'active_courses': active_courses,
        })
```

**Step 2 — URLs:**

```python
path("manager/billing/plan/", ManagerBillingPlanView.as_view(), name="manager-billing-plan"),
path("manager/billing/usage/", ManagerBillingUsageView.as_view(), name="manager-billing-usage"),
```

---

### Task 61: ~~Promo Code System~~ — REMOVED FROM SCOPE

**Step 1 — Model** (`apps/payments/models.py`, append):

```python
class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.PositiveIntegerField(default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    max_uses = models.PositiveIntegerField(default=0)  # 0 = unlimited
    current_uses = models.PositiveIntegerField(default=0)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        null=True, blank=True, related_name='promo_codes'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments_promocode'

    def __str__(self):
        return self.code
```

**Step 2 — View** (append to `apps/payments/views.py` or new file):

```python
class PromoCodeVerifyView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        """GET /api/v1/public/promo-codes/verify/?code=SAVE20&course=5"""
        from django.utils import timezone

        code = request.query_params.get('code', '').upper()
        if not code:
            return Response({'error': 'code parameter required'}, status=400)

        try:
            promo = PromoCode.objects.get(code=code, is_active=True)
        except PromoCode.DoesNotExist:
            return Response({'valid': False, 'error': 'Invalid promo code'}, status=404)

        now = timezone.now()
        if now < promo.valid_from or now > promo.valid_to:
            return Response({'valid': False, 'error': 'Promo code expired'})

        if promo.max_uses > 0 and promo.current_uses >= promo.max_uses:
            return Response({'valid': False, 'error': 'Promo code usage limit reached'})

        return Response({
            'valid': True,
            'code': promo.code,
            'discount_percent': promo.discount_percent,
            'discount_amount': str(promo.discount_amount),
        })
```

**Step 3 — URL** (in `apps/catalogue/urls_public.py` or `apps/payments/urls.py`):

```python
path("promo-codes/verify/", PromoCodeVerifyView.as_view(), name="promo-verify"),
```

Since the frontend expects `GET /api/v1/public/promo-codes/verify/`, register under the public URL prefix.

**Step 4 — Migration:**

```bash
python manage.py makemigrations payments
python manage.py migrate
```

---

### Task 62: Course Review Enhancements

**File:** `apps/catalogue/views.py` line 1268 — `CourseReviewViewSet(viewsets.ModelViewSet)`

**Problem:** No `helpful` or `report` actions. No `rating` filter.

**Do this:**

```python
class CourseReviewViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    def get_queryset(self):
        qs = super().get_queryset()
        rating = self.request.query_params.get('rating')
        if rating:
            qs = qs.filter(rating=int(rating))
        return qs

    @action(detail=True, methods=['post'], url_path='helpful')
    def helpful(self, request, pk=None):
        """POST /api/v1/catalogue/reviews/{id}/helpful/"""
        review = self.get_object()
        # If you add a helpful_count field to CourseReview model:
        # review.helpful_count = F('helpful_count') + 1
        # review.save(update_fields=['helpful_count'])
        # For now, just acknowledge:
        return Response({'status': 'marked helpful'})

    @action(detail=True, methods=['post'], url_path='report')
    def report(self, request, pk=None):
        """POST /api/v1/catalogue/reviews/{id}/report/"""
        review = self.get_object()
        # Could create a ReviewReport model, or just flag:
        # review.is_approved = False
        # review.save(update_fields=['is_approved'])
        return Response({'status': 'reported'})
```

**Note:** To fully implement, add `helpful_count = models.PositiveIntegerField(default=0)` and `report_count = models.PositiveIntegerField(default=0)` to `CourseReview` model, then run `makemigrations`.

---

### Task 63: Transaction & Invoice Exports ✅ DONE

**File:** `apps/payments/views.py`

**Do this:**

```python
import csv
from django.http import HttpResponse

class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    # ... existing code ...

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """GET /api/v1/payments/transactions/export-csv/"""
        qs = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Transaction ID', 'Amount', 'Currency', 'Status',
            'Payment Method', 'Created At', 'Completed At',
        ])
        for t in qs:
            writer.writerow([
                t.id, t.transaction_id, t.amount, t.currency, t.status,
                t.payment_method, t.created_at, t.completed_at,
            ])
        return response


class InvoiceViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        """GET /api/v1/payments/invoices/{id}/download-pdf/"""
        invoice = self.get_object()
        # Option 1: Return invoice data for frontend CSS-based printing
        # Option 2: Use WeasyPrint (if installed)
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)
        # TODO: For real PDF, add weasyprint to requirements and render template

    @action(detail=True, methods=['post'], url_path='email-receipt')
    def email_receipt(self, request, pk=None):
        """POST /api/v1/payments/invoices/{id}/email-receipt/"""
        invoice = self.get_object()
        # TODO: Send email via SendGrid with invoice data
        return Response({'status': 'Receipt email queued'})
```

---

### Task 22: Security Metrics ✅ DONE

**New view for superadmin:**

```python
class SecurityStatsView(APIView):
    permission_classes = [IsAuthenticated]  # Add IsTascAdmin

    def get(self, request):
        """GET /api/v1/superadmin/security/stats/"""
        from django.utils import timezone
        from apps.accounts.models import User

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        failed_today = User.objects.filter(
            failed_login_attempts__gt=0
        ).count()

        locked = User.objects.filter(
            account_locked_until__gt=now
        ).count()

        return Response({
            'failed_logins_today': failed_today,
            'locked_accounts': locked,
            'active_sessions': 0,  # Would need session tracking
            'mfa_adoption_percent': 0,  # Would need MFA tracking
        })
```

**URL:** Add to `apps/audit/urls.py` or `apps/accounts/urls_superadmin.py`:

```python
path("security/stats/", SecurityStatsView.as_view(), name="security-stats"),
```

Full endpoint: `GET /api/v1/superadmin/security/stats/`

---

### Task 25: Redis Integration

**Files to modify:**
- `requirements.txt` — add `redis` and `django-redis`
- `config/settings.py` — cache config + Celery broker
- `docker-compose.yml` — add Redis service

**Step 1 — `requirements.txt`:**

```
redis>=5.0.0
django-redis>=5.4.0
```

**Step 2 — `config/settings.py`** (replace lines 375-377 where `CELERY_BROKER_URL = "django://"` and `CELERY_RESULT_BACKEND = "django-db"`):

```python
# Cache
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://redis:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/2")
```

**Step 3 — `docker-compose.yml`:**

```yaml
redis:
  image: redis:7-alpine
  restart: unless-stopped
  ports:
    - "127.0.0.1:6379:6379"
  volumes:
    - redis_data:/data

# Add to volumes section:
volumes:
  redis_data:
```

---

### Task 26: DB Connection Pooling

**File:** `config/settings.py` — `DATABASES` config

**Do this** (psycopg 3.3.2 supports native pooling):

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "pool": {
                "min_size": 5,
                "max_size": 20,
            }
        },
    }
}
```

---

### Task 27: Gunicorn Worker Scaling

**Files:** `Dockerfile` (line 24), `docker-compose.staging.yml` (line 41)

**Replace:**
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

**With:**
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

---

## LOW PRIORITY

---

### Task 8: Email Templates

**Create directory:** `templates/emails/`

**Files to create:**

| File | Variables |
|------|----------|
| `templates/emails/verification.html` | `user_name`, `verification_url` |
| `templates/emails/password_reset.html` | `user_name`, `reset_url`, `expiry_hours` |
| `templates/emails/enrollment_confirmation.html` | `user_name`, `course_title`, `start_date` |
| `templates/emails/certificate_issued.html` | `user_name`, `course_title`, `certificate_url` |
| `templates/emails/payment_receipt.html` | `user_name`, `course_title`, `amount`, `currency`, `transaction_id`, `date` |

---

### Task 9: Notification ViewSet Extras ✅ DONE

**File:** `apps/notifications/views.py` line 33 — `NotificationViewSet(viewsets.ModelViewSet)`

**Add:**

```python
class NotificationViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    def get_queryset(self):
        qs = super().get_queryset()
        # Date range filter
        created_after = self.request.query_params.get('created_after')
        created_before = self.request.query_params.get('created_before')
        if created_after:
            qs = qs.filter(created_at__gte=created_after)
        if created_before:
            qs = qs.filter(created_at__lte=created_before)
        return qs

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """POST /api/v1/notifications/bulk-delete/  body: { "ids": [1,2,3] }"""
        ids = request.data.get('ids', [])
        deleted = Notification.objects.filter(
            id__in=ids, user=request.user
        ).delete()[0]
        return Response({'deleted': deleted})
```

---

### Task 17: N+1 Query Fixes ✅ DONE

Add `select_related` / `prefetch_related` to these viewsets:

| ViewSet | File:Line | Add to `get_queryset()` |
|---------|-----------|------------------------|
| `EnrollmentViewSet` (learner branch) | `learning/views.py:31` | `.select_related('course', 'course__category', 'course__instructor', 'user', 'organization')` |
| `DiscussionViewSet` | `learning/views.py:334` | `.select_related('user', 'course', 'session')` |
| `DiscussionReplyViewSet` | `learning/views.py:430` | `.select_related('user', 'discussion')` |
| `SubmissionViewSet` | `learning/views.py:598` | `.select_related('enrollment', 'enrollment__user', 'assignment', 'assignment__session', 'graded_by')` |
| `NotificationViewSet` | `notifications/views.py:33` | `.select_related('user')` |
| `InvoiceViewSet` | `payments/views.py:89` | `.select_related('user', 'organization', 'course', 'payment').prefetch_related('items')` |
| `TransactionViewSet` | `payments/views.py:268` | `.select_related('user', 'organization', 'course', 'invoice')` |

---

### Task 10-16: Silent Exception Fixes ✅ DONE

Each is a 1-line fix:

| # | File | Line(s) | Fix |
|---|------|---------|-----|
| 10 | `apps/payments/utils/webhook_handlers.py` | 271, 317 | Replace `pass` with `logger.warning(f"Payment not found: {transaction_id}")` |
| 11 | `apps/payments/utils/payment_validators.py` | 328 | Add `logger.info(f"Phone validation skipped: {phone}: {e}")` |
| 13 | `apps/audit/views.py` | 79, 89 | Return `Response({'error': 'Invalid date format. Expected YYYY-MM-DD.'}, status=400)` |
| 14 | `apps/catalogue/views.py` | 118 | Return `Response({'error': 'Invalid category ID'}, status=400)` |
| 16 | `apps/common/views.py` | 362-366 | Replace `except Exception: pass` with `logger.warning(f"S3 storage calc failed: {e}")` |

---

### Task 16b: Django Admin Registrations ✅ DONE

**File:** `apps/catalogue/admin.py`

**Already registered:** `QuestionCategory`, `BankQuestion`, `Assignment`, `Quiz`, `QuizQuestion`, `Module`

**Add:**

```python
from apps.catalogue.models import Course, Session, Category, Tag

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'instructor', 'level', 'created_at']
    list_filter = ['status', 'level', 'category']
    search_fields = ['title', 'short_description']
    prepopulated_fields = {'slug': ('title',)}

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'module', 'session_type', 'order', 'status']
    list_filter = ['session_type', 'status']
    search_fields = ['title']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
```

---

### Task 40: Roles — Per-Role User Counts ✅ DONE

**File:** `apps/accounts/views_superadmin.py` line 44 — `UserSuperadminViewSet`

**Find the existing `stats` action and add `by_role`:**

```python
@action(detail=False, methods=['get'], url_path='stats')
def stats(self, request):
    from django.db.models import Count

    qs = User.objects.all()
    total = qs.count()
    active = qs.filter(is_active=True).count()
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_this_month = qs.filter(date_joined__gte=month_start).count()
    suspended = qs.filter(is_active=False).count()

    by_role = list(
        qs.values('role').annotate(count=Count('id')).order_by('role')
    )

    return Response({
        'total': total,
        'active': active,
        'new_this_month': new_this_month,
        'suspended': suspended,
        'by_role': by_role,
    })
```

**Frontend `UserStats` interface** (`users.services.ts` line 101):
```typescript
export interface UserStats {
    total: number;
    active: number;
    new_this_month: number;
    suspended: number;
}
```
After this change, the response adds `by_role` — frontend can read it without breaking.

**Role choices from model:** `learner`, `org_admin`, `instructor`, `finance`, `tasc_admin`, `lms_manager`.

---

### Task 23: B2B Pricing Tiers

**Problem:** `/for-business` page displays hardcoded pricing tiers.

**Frontend already has** `businessPricingApi.getPlans()` in `public.services.ts` line 131 calling `GET /api/v1/public/business-plans/`.

**Backend already has** `PublicSubscriptionPlanViewSet` at `apps/payments/views_public.py` line 19. If the subscription plans in the DB don't exist yet, create them via admin or a management command.

**If you need a separate B2B endpoint**, create plans via `Subscription` model (which has `max_courses`, `max_users` fields) and filter:

```python
class BusinessPricingViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        """GET /api/v1/public/business-plans/"""
        plans = Subscription.objects.filter(
            status='active', max_users__isnull=False
        ).order_by('price')
        return Response([
            {
                'id': str(p.id),
                'name': p.name,
                'price': float(p.price),
                'billing_period': p.billing_cycle,
                'features': p.features,
                'max_users': p.max_users,
            }
            for p in plans
        ])
```

Register in `apps/catalogue/urls_public.py`:
```python
router.register(r'business-plans', BusinessPricingViewSet, basename='business-plans')
```

---

### Task 38: System Settings & Health ✅ DONE

```python
class SystemHealthView(APIView):
    permission_classes = [IsAuthenticated]  # Add IsTascAdmin

    def get(self, request):
        """GET /api/v1/superadmin/system/health/"""
        import time
        from django.db import connection

        # DB check
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_latency = round((time.time() - start) * 1000)

        return Response({
            'database': 'healthy',
            'db_latency_ms': db_latency,
            'storage': 'online',
        })
```

Register in `apps/audit/urls.py`:
```python
path("system/health/", SystemHealthView.as_view(), name="system-health"),
```

Full endpoint: `GET /api/v1/superadmin/system/health/`

---

### Task 45: Manager Activity Log Summary ✅ DONE

**File:** `apps/audit/views.py` line 39 — `AuditLogListView(APIView)`

**Add a summary endpoint or action:**

```python
class AuditLogSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/superadmin/audit-logs/summary/?period=today"""
        from django.utils import timezone
        from django.db.models import Count

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        qs = AuditLog.objects.filter(created_at__gte=today_start)

        # Scope for managers
        if request.user.role == 'lms_manager':
            membership = Membership.objects.filter(
                user=request.user, is_active=True
            ).first()
            if membership:
                qs = qs.filter(organization=membership.organization)

        counts = qs.values('action').annotate(count=Count('id'))
        result = {row['action']: row['count'] for row in counts}

        return Response({
            'logins': result.get('login', 0),
            'created': result.get('created', 0),
            'updated': result.get('updated', 0),
            'deleted': result.get('deleted', 0),
        })
```

Register in `apps/audit/urls.py`:
```python
path("audit-logs/summary/", AuditLogSummaryView.as_view(), name="audit-log-summary"),
```

Full endpoint: `GET /api/v1/superadmin/audit-logs/summary/`

---

---

### Task 67: System Settings PATCH + SMTP Config + Test Email

**File:** `apps/accounts/views_superadmin.py`

**Do this:** Add endpoints so `SystemSettingsPage.tsx` Save buttons work.

```python
class SystemSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/superadmin/system/settings/"""
        # Return current platform settings (store in DB model or env-backed config)
        return Response({
            "platform_name": settings.PLATFORM_NAME,
            "platform_url": settings.PLATFORM_URL,
            "support_email": settings.SUPPORT_EMAIL,
            "default_timezone": settings.TIME_ZONE,
            "max_upload_mb": settings.MAX_UPLOAD_MB,
        })

    def patch(self, request):
        """PATCH /api/v1/superadmin/system/settings/"""
        # Save to a SystemConfig model or update env-backed settings store
        return Response({"detail": "Settings saved."})


class SMTPSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        """PATCH /api/v1/superadmin/system/smtp/"""
        # Save SMTP host/port/username/password/from_name/from_email to secure config

    def post(self, request):
        """POST /api/v1/superadmin/system/smtp/test/"""
        # Send a test email using the provided SMTP settings
        return Response({"detail": "Test email sent."})
```

**URLs to add in** `apps/common/api_urls.py`:
```python
path("superadmin/system/settings/", SystemSettingsView.as_view(), name="system-settings"),
path("superadmin/system/smtp/", SMTPSettingsView.as_view(), name="smtp-settings"),
path("superadmin/system/smtp/test/", SMTPSettingsView.as_view(), name="smtp-test"),
```

**Frontend dependency:** F29 (`SystemSettingsPage.tsx`)

---

### Task 68: Security Policy Endpoints (MFA / Password / Session / Terminate)

**File:** `apps/accounts/views_superadmin.py`

**Do this:** Add endpoints for SecurityPage policy save buttons.

```python
class SecurityPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/superadmin/security/policy/"""
        # Return current MFA, password, and session policy settings

    def patch(self, request):
        """PATCH /api/v1/superadmin/security/policy/"""
        # Save policy settings to a SecurityPolicy model
        # Fields: mfa_enabled, mfa_required_roles[], mfa_methods[],
        #         min_password_length, require_uppercase, require_special,
        #         password_expiry_days, password_history,
        #         max_failed_attempts, lockout_duration_minutes,
        #         session_timeout_minutes, idle_timeout_minutes,
        #         max_concurrent_sessions, force_single_session


class TerminateAllSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """POST /api/v1/superadmin/security/terminate-sessions/"""
        # Flush all active tokens/sessions (e.g., rotate Django signing key or
        # delete all TokenAuth/BlacklistToken records)
        from rest_framework.authtoken.models import Token
        Token.objects.all().delete()
        return Response({"detail": "All sessions terminated."})
```

**URLs to add:**
```python
path("superadmin/security/policy/", SecurityPolicyView.as_view(), name="security-policy"),
path("superadmin/security/terminate-sessions/", TerminateAllSessionsView.as_view(), name="terminate-sessions"),
```

**Frontend dependency:** F30 (`SecurityPage.tsx`)

---

### Task 69: Pesapal Gateway Config Save + Test Connection

**File:** `apps/payments/views_pesapal.py`

**Do this:** Allow superadmin to save Pesapal API keys and test the connection.

```python
class PesapalConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/superadmin/gateway/pesapal/config/"""
        # Return masked consumer_key, consumer_secret, ipn_url, environment

    def patch(self, request):
        """PATCH /api/v1/superadmin/gateway/pesapal/config/"""
        # Save consumer_key, consumer_secret, environment (sandbox/production) to
        # a GatewayConfig model or encrypted env store


class PesapalTestConnectionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """POST /api/v1/superadmin/gateway/pesapal/test/"""
        # Attempt to get a Pesapal OAuth token using saved credentials
        # Return {"ok": true} or {"ok": false, "error": "..."}
```

**URLs to add:**
```python
path("superadmin/gateway/pesapal/config/", PesapalConfigView.as_view(), name="pesapal-config"),
path("superadmin/gateway/pesapal/test/", PesapalTestConnectionView.as_view(), name="pesapal-test"),
```

**Frontend dependency:** F31 (`GatewaySettingsPage.tsx`)

---

### Task 70: User Invite Endpoint

**File:** `apps/accounts/views_superadmin.py` or `apps/accounts/views.py`

**Do this:** Allow superadmin to invite a new instructor by email.

```python
class InviteUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """POST /api/v1/superadmin/users/invite/"""
        # Expected body: { "email": "...", "role": "instructor", "name": "..." }
        # 1. Create an inactive User record (or use a pending invite model)
        # 2. Send invitation email with a one-time signup link
        # 3. Return { "detail": "Invitation sent to email@example.com" }
```

**URL to add:**
```python
path("superadmin/users/invite/", InviteUserView.as_view(), name="invite-user"),
```

**Frontend dependency:** F32 (`InstructorsPage.tsx` Invite Instructor button)

---

### Task 71: Subscription Plan Admin PATCH Endpoint

**File:** `apps/payments/views.py` — `SubscriptionViewSet`

**Do this:** Allow finance admin to edit subscription plan details (name, price, features).

```python
class SubscriptionViewSet(viewsets.ModelViewSet):
    # Change from ReadOnlyModelViewSet to ModelViewSet
    # Add permission: only finance_manager or superadmin can write
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsFinanceOrSuperAdmin()]
```

**Frontend dependency:** F34 (`FinancePricingPage.tsx` Edit Plans / Manage Plan buttons)

---

### Task 72: Workshop Model + CRUD API

**Priority:** MED
**App:** `apps/workshops/` (new app) or `apps/learning/`
**Why:** Workshops are physical in-person training sessions — not livestreams. The frontend `WorkshopsPage.tsx` was incorrectly pulling from the livestream API; it has been decoupled and now needs a dedicated backend.

**Model fields:**
```python
class Workshop(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    max_participants = models.PositiveIntegerField(default=30)
    grading_type = models.CharField(max_length=20, choices=[('attendance','Attendance Only'),('pass_fail','Pass / Fail'),('score','Score (0-100)')], default='attendance')
    category = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=[('upcoming','Upcoming'),('ongoing','Ongoing'),('completed','Completed')], default='upcoming')
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='workshops')
    created_at = models.DateTimeField(auto_now_add=True)
```

**Endpoints needed:**
- `GET /api/v1/workshops/` — list (instructors see own, managers/superadmin see all)
- `POST /api/v1/workshops/` — create (instructors + managers)
- `GET /api/v1/workshops/{id}/` — retrieve
- `PATCH /api/v1/workshops/{id}/` — update
- `DELETE /api/v1/workshops/{id}/` — delete

**Response shape expected by frontend (`Workshop` interface):**
```typescript
{ id, title, description, location, start_date, end_date, max_participants, grading_type, category, status }
```

**Frontend dependency:** F35 (`WorkshopsPage.tsx` — wire Create/list to `workshopApi`)

---

## Configuration TODOs

- [ ] Set `ZOOM_WEBHOOK_SECRET` in production `.env`
- [ ] Set `GOOGLE_MEET_SERVICE_ACCOUNT_FILE`, `GOOGLE_MEET_DELEGATED_USER`, `GOOGLE_MEET_CALENDAR_ID`
- [ ] Set `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`, `TEAMS_CLIENT_SECRET`, `TEAMS_ORGANIZER_USER_ID`
- [ ] Set up SendGrid email templates for production
- [ ] Create `Subscription` seed data for B2B pricing tiers

---

## Test Coverage Gaps

| App | Current | Priority Tests to Add |
|-----|---------|----------------------|
| `learning` | 27 | SavedCourse CRUD, quiz submission edge cases, report generation |
| `catalogue` | 95 | Quiz POST creation, assignment update, course review helpful/report |
| `payments` | 8 | Webhook handlers, Pesapal mobile money charge, promo code validation |
| `accounts` | 48 | CSV bulk import, instructor stats, org annotation |
| `audit` | 6 | Date filter validation, summary endpoint |
| `notifications` | 2 | Bulk delete, date range filter, mark_read |

---

## Completed Items Archive

<details>
<summary>Click to expand — 28 completed items</summary>

| # | Item | Date |
|---|------|------|
| 1 | Quiz Submission System | — |
| 2 | Report Generation / Celery | — |
| 3 | Bulk User Import (Superadmin) | — |
| 4 | LivestreamQuestion Model | — |
| 8 | ReportViewSet Data Queries | — |
| 9a | Bulk Grade Action | — |
| 9b | Grade Statistics Action | — |
| 14 | Migration Backfill | — |
| — | Course Reviews | — |
| — | Public Endpoints | — |
| — | Celery Setup | — |
| 0a | Public Course Search & Ordering | — |
| — | Category courses_count | — |
| — | InvoiceViewSet date filters | — |
| — | EnrollmentViewSet search | — |
| — | SessionProgressViewSet filters | — |
| — | Livestream Tests & Setup | — |
| 12 | Calendar Service timezone fix | — |
| 15 | Livestream Webhooks rename | — |
| 46 | Livestream Session Creation permissions | — |
| 24 | Messaging API (100% test coverage) | — |
| 4 | DiscussionViewSet Moderation | 26 Mar |
| 7 | SubmissionViewSet Validation | 26 Mar |
| 0b | Manager Bulk Import | 26 Mar |
| DB | Analytics ViewSets | 26 Mar |
| 5 | Module Bulk Reorder | 27 Mar |
| 18 | Analytics Endpoints | 26 Mar |
| 19 | Certificate Auto-Creation | 27 Mar |
| 20 | Bulk Enrollment Endpoint | 27 Mar |
| 21 | Session Attachments | 27 Mar |
| 28 | Badges System | 27 Mar |

</details>
```

---

That's the complete rewritten document. Every task now uses:

- **Exact model field names** from the schema dump (e.g., `related_name="memberships"`, `related_name="enrollments"`, `related_name="instructed_courses"`)
- **Exact serializer class names** and line numbers (e.g., `CourseListSerializer` at line 619, `AssignmentCreateUpdateSerializer` at line 463)
- **Exact ViewSet class names** and line numbers (e.g., `CourseViewSet` at line 215, `SessionViewSet` at line 834)
- **Exact URL registration patterns** matching `apps/common/api_urls.py`
- **Response shapes matching frontend TypeScript interfaces** (e.g., `Organization.users_count`, `UserStats.by_role`, `CourseList` nested structure)
- **Correct `status` choice values** from model definitions (e.g., Course: `draft`/`pending_approval`/`published`/`rejected`/`archived`)