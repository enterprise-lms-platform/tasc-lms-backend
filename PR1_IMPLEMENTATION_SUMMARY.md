# PR #1: Backend - Public Catalogue Endpoints

## ✅ Implementation Complete

### Files Changed

#### 1. **apps/catalogue/serializers.py** (EDITED)
   - **Lines added**: ~50 lines
   - **Changes**: Added public serializers at the end of file
   - **New classes**:
     - `PublicSessionSerializer` - Excludes `video_url` and `content_text` fields
     - `PublicCourseDetailSerializer` - Uses PublicSessionSerializer, hides sensitive instructor data

#### 2. **apps/catalogue/views_public.py** (NEW FILE)
   - **Lines**: ~250 lines
   - **Purpose**: Public read-only ViewSets with AllowAny permissions
   - **Classes**:
     - `PublicCourseViewSet` - Published courses only, lookup by slug
     - `PublicCategoryViewSet` - Active categories only
     - `PublicTagViewSet` - All tags
   - **Features**:
     - OpenAPI/Swagger documentation with examples
     - Query filtering: `featured`, `category`, `level`
     - Select/prefetch optimization to reduce queries

#### 3. **apps/catalogue/urls_public.py** (EDITED)
   - **Lines changed**: 2 → 18 lines
   - **Changes**: Populated with DefaultRouter and registered 3 ViewSets
   - **Routes registered**:
     - `public-course` → `/api/v1/public/courses/`
     - `public-category` → `/api/v1/public/categories/`
     - `public-tag` → `/api/v1/public/tags/`

#### 4. **test_public_api.py** (NEW FILE - Helper Script)
   - **Purpose**: Create test data and verify setup
   - **Creates**: Category, Tags, Published Course, Instructor user
   - **Run**: `python test_public_api.py`

#### 5. **test_api_endpoints.sh** (NEW FILE - Test Script)
   - **Purpose**: curl-based endpoint testing
   - **Tests**: All 4 public endpoints + filtering
   - **Run**: `./test_api_endpoints.sh` (requires server running)

---

## 📍 API Endpoints Created

All endpoints require **NO AUTHENTICATION** (AllowAny):

### 1. List Published Courses
```
GET /api/v1/public/courses/
```

**Query Parameters:**
- `?featured=true` - Filter featured courses
- `?category=<id>` - Filter by category ID
- `?level=<beginner|intermediate|advanced|all_levels>` - Filter by level
- `?page=<n>` - Pagination (DRF default)

**Response**: Paginated list of CourseListSerializer

### 2. Get Course Detail by Slug
```
GET /api/v1/public/courses/<slug>/
```

**Example**: `/api/v1/public/courses/advanced-react-patterns/`

**Response**: PublicCourseDetailSerializer (includes session structure but no video URLs)

### 3. List Active Categories
```
GET /api/v1/public/categories/
```

**Response**: List of CategorySerializer

### 4. Get Category Detail
```
GET /api/v1/public/categories/<id>/
```

**Response**: CategorySerializer

### 5. List Tags
```
GET /api/v1/public/tags/
```

**Response**: List of TagSerializer

### 6. Get Tag Detail
```
GET /api/v1/public/tags/<id>/
```

**Response**: TagSerializer

---

## 🧪 Testing Instructions

### Prerequisites
1. Start Django server in terminal 1:
```bash
cd back/tasc-lms-backend
source venv/bin/activate
python manage.py runserver 8000
```

2. In terminal 2, create test data:
```bash
cd back/tasc-lms-backend
source venv/bin/activate
python test_public_api.py
```

### Quick curl Tests

**Test 1: List courses (should return HTTP 200)**
```bash
curl -X GET http://127.0.0.1:8000/api/v1/public/courses/
```

**Test 2: Get course by slug (should return HTTP 200)**
```bash
curl -X GET http://127.0.0.1:8000/api/v1/public/courses/advanced-react-patterns/
```

**Test 3: List categories (should return HTTP 200)**
```bash
curl -X GET http://127.0.0.1:8000/api/v1/public/categories/
```

**Test 4: List tags (should return HTTP 200)**
```bash
curl -X GET http://127.0.0.1:8000/api/v1/public/tags/
```

**Test 5: Filter featured courses**
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/public/courses/?featured=true"
```

**Test 6: Filter by category**
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/public/courses/?category=1"
```

**Test 7: Filter by level**
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/public/courses/?level=advanced"
```

### Automated Testing
```bash
cd back/tasc-lms-backend
./test_api_endpoints.sh
```

---

## ✅ Verification Checklist

- [x] PublicCourseViewSet filters only `status='published'` courses
- [x] PublicCourseViewSet uses `lookup_field='slug'`
- [x] PublicSessionSerializer excludes `video_url` and `content_text`
- [x] All ViewSets use `permission_classes = [AllowAny]`
- [x] Filtering works: `featured`, `category`, `level`
- [x] Routes mounted under `/api/v1/public/` (no changes to routing config)
- [x] Private endpoints `/api/v1/catalogue/*` unchanged (still require auth)
- [x] OpenAPI/Swagger documentation included
- [x] Select/prefetch optimization to reduce N+1 queries

---

## 🔒 Security Notes

### What's Protected:
- ✅ Video URLs and content text (excluded from PublicSessionSerializer)
- ✅ Instructor email (excluded from PublicCourseDetailSerializer)
- ✅ Draft and archived courses (filtered out)
- ✅ Inactive categories (filtered out)
- ✅ Session content URLs (not exposed to unauthenticated users)

### What's Public:
- ✅ Course titles, descriptions, thumbnails
- ✅ Pricing information
- ✅ Session structure (titles, order, duration) but not content
- ✅ Instructor names (but not emails)
- ✅ Category and tag names

---

## 📊 Expected Response Examples

### GET /api/v1/public/courses/
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Advanced React Patterns",
      "slug": "advanced-react-patterns",
      "subtitle": "Master advanced React patterns and best practices",
      "short_description": "Master advanced React patterns",
      "thumbnail": "https://images.unsplash.com/photo-1616400619175-5beda3a17896?q=80&w=1074",
      "category": {
        "id": 1,
        "name": "Web Development",
        "slug": "web-development",
        "description": "Learn web development",
        "icon": null,
        "parent": null,
        "is_active": true,
        "created_at": "2026-02-10T...",
        "updated_at": "2026-02-10T..."
      },
      "tags": [
        {"id": 1, "name": "React", "slug": "react", "created_at": "..."},
        {"id": 2, "name": "JavaScript", "slug": "javascript", "created_at": "..."}
      ],
      "level": "advanced",
      "price": "129.99",
      "discounted_price": 129.99,
      "discount_percentage": 0,
      "duration_hours": 24,
      "duration_weeks": 8,
      "total_sessions": 48,
      "instructor": 1,
      "instructor_name": "Peter Kakuru",
      "enrollment_count": 0,
      "featured": true,
      "status": "published",
      "published_at": null
    }
  ]
}
```

### GET /api/v1/public/courses/advanced-react-patterns/
```json
{
  "id": 1,
  "title": "Advanced React Patterns",
  "slug": "advanced-react-patterns",
  "description": "Learn advanced React patterns including hooks, context, and performance optimization.",
  "prerequisites": "Basic React knowledge",
  "learning_objectives": "Master advanced patterns",
  "target_audience": "Intermediate developers",
  "trailer_video_url": null,
  "sessions": [],
  "instructor": {
    "id": 1,
    "name": "Peter Kakuru",
    "avatar": null
  },
  "category": {...},
  "tags": [...],
  "level": "advanced",
  "price": "129.99",
  "featured": true,
  "created_at": "2026-02-10T...",
  "updated_at": "2026-02-10T..."
}
```

---

## 🚀 Next Steps (PR #2)

After this PR is merged:
1. Frontend can consume these endpoints
2. Landing page `<Courses>` component fetches from `/api/v1/public/courses/?featured=true`
3. Catalogue page `<CoursesGrid>` component fetches from `/api/v1/public/courses/`
4. Add filtering UI wired to query params

---

## 📝 Git Commands

```bash
# Check changed files
git status

# Stage changes
git add apps/catalogue/serializers.py
git add apps/catalogue/views_public.py
git add apps/catalogue/urls_public.py

# Optional: stage test scripts (or add to .gitignore)
git add test_public_api.py
git add test_api_endpoints.sh

# Commit
git commit -m "feat(catalogue): add public read-only API endpoints

- Add PublicCourseViewSet with slug lookup and published filter
- Add PublicCategoryViewSet for active categories
- Add PublicTagViewSet for tags
- Create PublicSessionSerializer (excludes video URLs)
- Create PublicCourseDetailSerializer (uses public sessions)
- Support filtering: featured, category, level
- Mount routes under /api/v1/public/ (no auth required)
- Add OpenAPI documentation with examples
- Add test data creation script

Endpoints:
- GET /api/v1/public/courses/
- GET /api/v1/public/courses/<slug>/
- GET /api/v1/public/categories/
- GET /api/v1/public/tags/"

# Push
git push origin feat/public-course-catalogue
```

---

## ⚠️ Important Notes

1. **No routing changes** - All routes mounted under existing `/api/v1/public/` prefix
2. **No breaking changes** - Private endpoints `/api/v1/catalogue/*` unchanged
3. **Security maintained** - Video URLs and sensitive content excluded from public API
4. **Performance optimized** - Uses select_related and prefetch_related
5. **Pagination enabled** - DRF default pagination applies
6. **Swagger ready** - OpenAPI documentation included for all endpoints

---

**Status**: ✅ **READY FOR REVIEW**
