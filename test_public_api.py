#!/usr/bin/env python
"""
Quick test script for public catalogue API endpoints.
Run: python test_public_api.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.catalogue.models import Course, Category, Tag
from apps.accounts.models import User

print("=" * 60)
print("Testing Public Catalogue API Setup")
print("=" * 60)

# Check if we have any data
categories_count = Category.objects.count()
tags_count = Tag.objects.count()
courses_count = Course.objects.count()
published_courses = Course.objects.filter(status='published').count()

print(f"\nDatabase Stats:")
print(f"  Categories: {categories_count}")
print(f"  Tags: {tags_count}")
print(f"  Total Courses: {courses_count}")
print(f"  Published Courses: {published_courses}")

# Create test data if needed
if categories_count == 0:
    print("\n📦 Creating test category...")
    category = Category.objects.create(
        name="Web Development",
        slug="web-development",
        description="Learn web development",
        is_active=True
    )
    print(f"  ✓ Created category: {category.name}")
else:
    category = Category.objects.first()
    print(f"\n✓ Using existing category: {category.name}")

if tags_count == 0:
    print("\n🏷️  Creating test tags...")
    tag1 = Tag.objects.create(name="React", slug="react")
    tag2 = Tag.objects.create(name="JavaScript", slug="javascript")
    print(f"  ✓ Created tags: {tag1.name}, {tag2.name}")
else:
    print(f"✓ Tags already exist: {tags_count} tags")

# Get or create an instructor user
instructor = User.objects.filter(role='instructor').first()
if not instructor:
    instructor = User.objects.filter(is_superuser=True).first()
if not instructor:
    print("\n👤 Creating test instructor...")
    instructor = User.objects.create_user(
        username='testinstructor',
        email='instructor@test.com',
        password='testpass123',
        first_name='Test',
        last_name='Instructor',
        role='instructor',
        email_verified=True,
        is_active=True
    )
    print(f"  ✓ Created instructor: {instructor.email}")
else:
    print(f"\n✓ Using existing instructor: {instructor.email}")

if published_courses == 0:
    print("\n📚 Creating test published course...")
    course = Course.objects.create(
        title="Advanced React Patterns",
        slug="advanced-react-patterns",
        subtitle="Master advanced React patterns and best practices",
        description="Learn advanced React patterns including hooks, context, and performance optimization.",
        short_description="Master advanced React patterns",
        category=category,
        level='advanced',
        price=129.99,
        discount_percentage=0,
        duration_hours=24,
        duration_weeks=8,
        total_sessions=48,
        instructor=instructor,
        created_by=instructor,
        thumbnail="https://images.unsplash.com/photo-1616400619175-5beda3a17896?q=80&w=1074",
        status='published',  # PUBLISHED STATUS
        featured=True,
        prerequisites="Basic React knowledge",
        learning_objectives="Master advanced patterns",
        target_audience="Intermediate developers"
    )
    # Add tags
    if tags_count > 0:
        course.tags.add(*Tag.objects.all()[:2])
    print(f"  ✓ Created published course: {course.title}")
    print(f"  ✓ Status: {course.status}")
    print(f"  ✓ Slug: {course.slug}")
else:
    course = Course.objects.filter(status='published').first()
    print(f"\n✓ Using existing published course: {course.title}")

print("\n" + "=" * 60)
print("✅ Test Data Ready!")
print("=" * 60)
print("\n📍 Public API Endpoints Available:")
print("  • GET /api/v1/public/courses/")
print("  • GET /api/v1/public/courses/advanced-react-patterns/")
print("  • GET /api/v1/public/categories/")
print("  • GET /api/v1/public/tags/")
print("\n🧪 Test Commands:")
print("  curl http://127.0.0.1:8000/api/v1/public/courses/")
print("  curl http://127.0.0.1:8000/api/v1/public/courses/advanced-react-patterns/")
print("  curl http://127.0.0.1:8000/api/v1/public/categories/")
print("  curl http://127.0.0.1:8000/api/v1/public/tags/")
print()
