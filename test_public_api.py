#!/usr/bin/env python
"""
Seed script for public catalogue API with realistic demo data.
Creates 8-12 published courses across all categories with category-based local thumbnails.
Run: python test_public_api.py
"""
import os
import django
from django.utils.text import slugify
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.catalogue.models import Course, Category, Tag
from apps.accounts.models import User

print("=" * 70)
print("🌱 Seeding Demo Catalogue Data")
print("=" * 70)

# ========================================
# 1. Categories (must match frontend slugs exactly)
# ========================================
CATEGORIES = [
    {
        'name': 'Web Development',
        'slug': 'web-development',
        'description': 'Modern web development courses covering frontend, backend, and full-stack development',
    },
    {
        'name': 'Welding',
        'slug': 'welding',
        'description': 'Professional welding training and certification courses',
    },
    {
        'name': 'EHS / Safety',
        'slug': 'ehs-safety',
        'description': 'Environmental Health and Safety training programs',
    },
    {
        'name': 'Scaffolding',
        'slug': 'scaffolding',
        'description': 'Scaffolding safety and construction training',
    },
    {
        'name': 'Electrical',
        'slug': 'electrical',
        'description': 'Electrical systems and safety training',
    },
    {
        'name': 'Plumbing',
        'slug': 'plumbing',
        'description': 'Professional plumbing and piping courses',
    },
    {
        'name': 'Assessment',
        'slug': 'assessment',
        'description': 'Skills assessment and pre-qualification tests',
    },
    {
        'name': 'Certification',
        'slug': 'certification',
        'description': 'Professional certification and compliance courses',
    },
]

# ========================================
# 2. Tags
# ========================================
TAG_NAMES = [
    'React', 'JavaScript', 'Python', 'Safety', 'Health', 
    'Electrical', 'Plumbing', 'Welding', 'ISO', 
    'Scaffolding', 'Assessment', 'Professional Development'
]

# ========================================
# 3. Demo Courses (8-12 courses, at least 1 per category)
# Using deterministic slugs for idempotency
# ========================================
DEMO_COURSES = [
    # Web Development (2 courses - popular category)
    {
        'title': 'React Fundamentals: Build Modern Web Applications',
        'slug': 'demo-react-fundamentals',  # Deterministic slug
        'category_slug': 'web-development',
        'level': 'beginner',
        'hours': 24,
        'sessions': 8,
        'price': '49.99',
        'featured': True,
        'tags': ['React', 'JavaScript', 'Professional Development'],
        'short_desc': 'Learn React from scratch and build interactive web applications',
    },
    {
        'title': 'Full Stack Web Development with Python & Django',
        'slug': 'demo-fullstack-python-django',
        'category_slug': 'web-development',
        'level': 'intermediate',
        'hours': 40,
        'sessions': 12,
        'price': '0.00',  # Free course
        'featured': False,
        'tags': ['Python', 'Professional Development'],
        'short_desc': 'Master full-stack development with Python and Django framework',
    },
    
    # Welding (1 course)
    {
        'title': 'Advanced Welding Techniques & Safety',
        'slug': 'demo-advanced-welding',
        'category_slug': 'welding',
        'level': 'advanced',
        'hours': 32,
        'sessions': 9,
        'price': '199.99',
        'featured': False,
        'tags': ['Welding', 'Safety', 'Professional Development'],
        'short_desc': 'Master advanced welding methods with comprehensive safety training',
    },
    
    # EHS / Safety (2 courses - popular category)
    {
        'title': 'Workplace Safety Essentials',
        'slug': 'demo-workplace-safety-essentials',
        'category_slug': 'ehs-safety',
        'level': 'beginner',
        'hours': 4,
        'sessions': 4,
        'price': '0.00',  # Free course
        'featured': True,
        'tags': ['Safety', 'Health', 'Professional Development'],
        'short_desc': 'Essential workplace safety training for all employees',
    },
    {
        'title': 'Hazard Identification and Risk Assessment',
        'slug': 'demo-hazard-risk-assessment',
        'category_slug': 'ehs-safety',
        'level': 'intermediate',
        'hours': 8,
        'sessions': 5,
        'price': '89.99',
        'featured': False,
        'tags': ['Safety', 'Assessment', 'Professional Development'],
        'short_desc': 'Learn to identify workplace hazards and conduct risk assessments',
    },
    
    # Scaffolding (1 course)
    {
        'title': 'Scaffolding Erection & Inspection',
        'slug': 'demo-scaffolding-erection',
        'category_slug': 'scaffolding',
        'level': 'intermediate',
        'hours': 16,
        'sessions': 6,
        'price': '149.99',
        'featured': False,
        'tags': ['Scaffolding', 'Safety', 'Professional Development'],
        'short_desc': 'Professional training in safe scaffolding practices',
    },
    
    # Electrical (1 course)
    {
        'title': 'Electrical Safety Fundamentals',
        'slug': 'demo-electrical-safety-fundamentals',
        'category_slug': 'electrical',
        'level': 'beginner',
        'hours': 6,
        'sessions': 4,
        'price': '0.00',  # Free course
        'featured': False,
        'tags': ['Electrical', 'Safety', 'Professional Development'],
        'short_desc': 'Essential electrical safety training for technicians',
    },
    
    # Plumbing (1 course)
    {
        'title': 'Industrial Plumbing Systems',
        'slug': 'demo-industrial-plumbing',
        'category_slug': 'plumbing',
        'level': 'advanced',
        'hours': 32,
        'sessions': 9,
        'price': '249.99',
        'featured': False,
        'tags': ['Plumbing', 'Professional Development'],
        'short_desc': 'Advanced training in industrial plumbing and piping systems',
    },
    
    # Assessment (1 course)
    {
        'title': 'Skills Assessment & Pre-Qualification',
        'slug': 'demo-skills-assessment',
        'category_slug': 'assessment',
        'level': 'all_levels',
        'hours': 2,
        'sessions': 2,
        'price': '0.00',  # Free course
        'featured': False,
        'tags': ['Assessment', 'Professional Development'],
        'short_desc': 'Comprehensive skills assessment for trade professionals',
    },
    
    # Certification (2 courses - popular category)
    {
        'title': 'ISO 9001 Quality Management Systems',
        'slug': 'demo-iso-9001-qms',
        'category_slug': 'certification',
        'level': 'intermediate',
        'hours': 24,
        'sessions': 8,
        'price': '299.99',
        'featured': True,
        'tags': ['ISO', 'Certification', 'Professional Development'],
        'short_desc': 'Professional ISO 9001 certification training',
    },
    {
        'title': 'Forklift Operator Certification',
        'slug': 'demo-forklift-certification',
        'category_slug': 'certification',
        'level': 'beginner',
        'hours': 8,
        'sessions': 5,
        'price': '129.99',
        'featured': False,
        'tags': ['Certification', 'Safety', 'Professional Development'],
        'short_desc': 'Get certified as a professional forklift operator',
    },
]

# ========================================
# Execution
# ========================================

# Get or create instructor
instructor = User.objects.filter(role='instructor').first()
if not instructor:
    instructor = User.objects.filter(is_superuser=True).first()
if not instructor:
    print("\n👤 Creating demo instructor...")
    instructor = User.objects.create_user(
        username='demoinstructor',
        email='instructor@tasclms.com',
        password='instructor123',
        first_name='Demo',
        last_name='Instructor',
        role='instructor',
        email_verified=True,
        is_active=True
    )
    print(f"  ✓ Created instructor: {instructor.email}")
else:
    print(f"\n✓ Using existing instructor: {instructor.email} (role: {instructor.role})")

# Create/Update categories
print("\n📦 Creating/Updating Categories...")
categories_map = {}
for cat_data in CATEGORIES:
    category, created = Category.objects.get_or_create(
        slug=cat_data['slug'],
        defaults={
            'name': cat_data['name'],
            'description': cat_data['description'],
            'is_active': True,
        }
    )
    # Update name and description if category already exists
    if not created:
        category.name = cat_data['name']
        category.description = cat_data['description']
        category.is_active = True
        category.save()
    
    categories_map[cat_data['slug']] = category
    status = "✓ Created" if created else "✓ Updated"
    print(f"  {status}: {category.name} ({category.slug})")

# Create/Update tags
print("\n🏷️  Creating/Updating Tags...")
tags_map = {}
for tag_name in TAG_NAMES:
    tag, created = Tag.objects.get_or_create(
        slug=slugify(tag_name),
        defaults={'name': tag_name}
    )
    tags_map[tag_name] = tag
    status = "✓ Created" if created else "✓ Exists"
    print(f"  {status}: {tag_name}")

# Create/Update demo courses
print("\n📚 Creating/Updating Demo Courses...")
print(f"Target: {len(DEMO_COURSES)} courses across {len(CATEGORIES)} categories")
print("-" * 70)

created_count = 0
updated_count = 0
courses_by_category = {}

for course_data in DEMO_COURSES:
    # Get category
    category = categories_map.get(course_data['category_slug'])
    if not category:
        print(f"  ⚠️  Category '{course_data['category_slug']}' not found, skipping course")
        continue
    
    # Create or update course (idempotent using deterministic slug)
    course, created = Course.objects.update_or_create(
        slug=course_data['slug'],
        defaults={
            'title': course_data['title'],
            'subtitle': f"Professional {category.name} training",
            'description': f"<p>Comprehensive training in {course_data['title'].lower()}.</p><p>This course covers essential skills, best practices, and industry standards.</p>",
            'short_description': course_data['short_desc'],
            'category': category,
            'level': course_data['level'],
            'price': Decimal(course_data['price']),
            'discount_percentage': 0,
            'duration_hours': course_data['hours'],
            'duration_weeks': max(1, course_data['hours'] // 10),
            'total_sessions': course_data['sessions'],
            'instructor': instructor,
            'created_by': instructor,
            'thumbnail': None,  # Use None so frontend displays category-based local images
            'status': 'published',
            'featured': course_data['featured'],
            'prerequisites': 'None' if course_data['level'] == 'beginner' else f"Basic {category.name.lower()} knowledge recommended",
            'learning_objectives': f"• Understand key concepts\n• Apply practical skills\n• Meet industry standards",
            'target_audience': f"{course_data['level'].replace('_', ' ').title()} level professionals in {category.name.lower()}",
        }
    )
    
    # Update tags (clear existing and add new)
    course.tags.clear()
    for tag_name in course_data['tags']:
        if tag_name in tags_map:
            course.tags.add(tags_map[tag_name])
    
    # Track stats
    if created:
        created_count += 1
        status_icon = "✓"
    else:
        updated_count += 1
        status_icon = "↻"
    
    # Group by category for summary
    cat_name = category.name
    if cat_name not in courses_by_category:
        courses_by_category[cat_name] = []
    courses_by_category[cat_name].append({
        'title': course.title,
        'slug': course.slug,
        'price': course.price,
        'featured': course.featured,
        'thumbnail': course.thumbnail,
    })
    
    price_display = 'Free' if course.price == 0 else f'${course.price}'
    featured_badge = ' [FEATURED]' if course.featured else ''
    print(f"  {status_icon} {course.title[:50]:<50} | {price_display:>10}{featured_badge}")

# Final summary
print("\n" + "=" * 70)
print("📊 Database Summary")
print("=" * 70)

total_published = Course.objects.filter(status='published').count()
total_featured = Course.objects.filter(status='published', featured=True).count()
total_free = Course.objects.filter(status='published', price=0).count()
total_paid = Course.objects.filter(status='published', price__gt=0).count()

print(f"\n✅ Created: {created_count} new courses")
print(f"↻  Updated: {updated_count} existing courses")
print(f"\n📈 Total Statistics:")
print(f"  • Total published courses: {total_published}")
print(f"  • Featured courses: {total_featured}")
print(f"  • Free courses: {total_free}")
print(f"  • Paid courses: {total_paid}")

print(f"\n📂 Courses by Category:")
for cat_name in sorted(courses_by_category.keys()):
    courses = courses_by_category[cat_name]
    print(f"\n  {cat_name} ({len(courses)} courses):")
    for course in courses:
        price_str = 'Free' if course['price'] == 0 else f'${course["price"]}'
        featured_str = ' ⭐' if course['featured'] else ''
        thumb_str = ' [ext]' if course['thumbnail'] else ' [local]'
        print(f"    • {course['title'][:45]:<45} | {price_str:>10}{featured_str}{thumb_str}")
        print(f"      slug: {course['slug']}")

print(f"\n📊 Courses by Level:")
for level in ['beginner', 'intermediate', 'advanced', 'all_levels']:
    count = Course.objects.filter(status='published', level=level).count()
    if count > 0:
        level_display = level.replace('_', ' ').title()
        print(f"  • {level_display}: {count} courses")

print("\n" + "=" * 70)
print("✅ Seed Complete!")
print("=" * 70)
print("\n📍 Test Public API Endpoints:")
print("  • All courses:      GET http://127.0.0.1:8000/api/v1/public/courses/")
print("  • Featured courses: GET http://127.0.0.1:8000/api/v1/public/courses/?featured=true")
print("  • By category:      GET http://127.0.0.1:8000/api/v1/public/courses/?category=1")
print("  • Categories:       GET http://127.0.0.1:8000/api/v1/public/categories/")
print("  • Tags:             GET http://127.0.0.1:8000/api/v1/public/tags/")
print("\n🧪 Quick Test:")
print("  curl -s http://127.0.0.1:8000/api/v1/public/courses/ | python -m json.tool | head -80")
print("\n💡 Note: All courses have thumbnail=None, so frontend will display category-based local images.")
print()
