import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalogue.models import Category, Course, Session, Tag
from apps.learning.models import Certificate, Enrollment, SessionProgress

User = get_user_model()


class Command(BaseCommand):
    help = "Seed predictable staging data for users and optional catalogue/learning."

    def add_arguments(self, parser):
        parser.add_argument("--learners", type=int, default=50)
        parser.add_argument("--instructors", type=int, default=15)
        parser.add_argument("--lms_managers", type=int, default=5)
        parser.add_argument("--finance", type=int, default=3)
        parser.add_argument("--tasc_admins", type=int, default=2)
        parser.add_argument("--org_admins", type=int, default=2)
        parser.add_argument("--password", type=str, default="Pass12345!")

        parser.add_argument("--with-catalogue", action="store_true")
        parser.add_argument("--categories", type=int, default=16)
        parser.add_argument("--tags", type=int, default=35)
        parser.add_argument("--courses", type=int, default=120)
        parser.add_argument("--published-ratio", type=float, default=0.7)
        parser.add_argument("--sessions-min", type=int, default=4)
        parser.add_argument("--sessions-max", type=int, default=12)

        parser.add_argument("--with-enrollments", action="store_true")
        parser.add_argument("--enrollments-min", type=int, default=3)
        parser.add_argument("--enrollments-max", type=int, default=10)
        parser.add_argument("--with-progress", action="store_true")
        parser.add_argument("--with-certificates", action="store_true")

        parser.add_argument("--reset", action="store_true")

    def handle(self, *args, **options):
        self.rng = random.Random(42)
        self.summary = {
            "users_created": 0,
            "users_updated": 0,
            "users_skipped": 0,
            "categories_created": 0,
            "categories_updated": 0,
            "tags_created": 0,
            "tags_updated": 0,
            "courses_created": 0,
            "courses_updated": 0,
            "sessions_created": 0,
            "sessions_updated": 0,
            "enrollments_created": 0,
            "enrollments_existing": 0,
            "progress_created": 0,
            "progress_updated": 0,
            "certificates_created": 0,
            "certificates_existing": 0,
        }

        if options["reset"]:
            self._reset_seed_data()

        user_index = self._seed_users(options)

        if options["with_catalogue"]:
            categories = self._seed_categories(options["categories"])
            tags = self._seed_tags(options["tags"])
            courses = self._seed_courses(
                count=options["courses"],
                categories=categories,
                tags=tags,
                instructors=user_index["instructors"],
                published_ratio=options["published_ratio"],
                sessions_min=options["sessions_min"],
                sessions_max=options["sessions_max"],
            )
        else:
            courses = list(Course.objects.filter(slug__startswith="seed-").order_by("id"))

        if options["with_enrollments"]:
            self._seed_enrollments_and_progress(
                learners=user_index["learners"],
                courses=courses,
                enroll_min=options["enrollments_min"],
                enroll_max=options["enrollments_max"],
                with_progress=options["with_progress"],
                with_certificates=options["with_certificates"],
            )

        self._print_summary()

    def _reset_seed_data(self):
        self.stdout.write(self.style.WARNING("Resetting seed data (safe scope only)..."))
        with transaction.atomic():
            course_qs = Course.objects.filter(slug__startswith="seed-")
            deleted_courses, _ = course_qs.delete()
            users_qs = User.objects.filter(email__iendswith="@test.com")
            deleted_users, _ = users_qs.delete()
            Category.objects.filter(slug__startswith="seed-cat-").delete()
            Tag.objects.filter(slug__startswith="seed-tag-").delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Reset complete: deleted {deleted_courses} course-related rows, {deleted_users} user-related rows."
            )
        )

    def _seed_users(self, options):
        cohorts = [
            ("learner", "learners", options["learners"], User.Role.LEARNER),
            ("instructor", "instructors", options["instructors"], User.Role.INSTRUCTOR),
            ("manager", "lms_managers", options["lms_managers"], User.Role.LMS_MANAGER),
            ("finance", "finance", options["finance"], User.Role.FINANCE),
            ("admin", "tasc_admins", options["tasc_admins"], User.Role.TASC_ADMIN),
            ("orgadmin", "org_admins", options["org_admins"], User.Role.ORG_ADMIN),
        ]
        password = options["password"]
        index = {k: [] for _, k, _, _ in cohorts}

        with transaction.atomic():
            for prefix, key, count, role in cohorts:
                for i in range(1, max(0, count) + 1):
                    email = f"{prefix}{i}@test.com"
                    username = f"{prefix}{i}"
                    first_name = prefix.capitalize()
                    last_name = str(i)

                    user = User.objects.filter(email__iexact=email).first()
                    if user is None:
                        user = User(
                            email=email.lower(),
                            username=self._unique_username(username),
                            first_name=first_name,
                            last_name=last_name,
                        )
                        user.role = role
                        user.email_verified = True
                        user.is_active = True
                        user.set_password(password)
                        user.save()
                        self.summary["users_created"] += 1
                    else:
                        changed = False
                        if user.role != role:
                            user.role = role
                            changed = True
                        if not user.is_active:
                            user.is_active = True
                            changed = True
                        if hasattr(user, "email_verified") and not user.email_verified:
                            user.email_verified = True
                            changed = True
                        if user.username != username and not User.objects.filter(
                            username=username
                        ).exclude(pk=user.pk).exists():
                            user.username = username
                            changed = True
                        if changed:
                            user.set_password(password)
                            user.save()
                            self.summary["users_updated"] += 1
                        else:
                            self.summary["users_skipped"] += 1

                    index[key].append(user)

        return index

    def _seed_categories(self, count):
        count = max(2, count)
        parent_count = max(1, count // 4)
        child_target = max(0, count - parent_count)
        categories = []
        parents = []

        with transaction.atomic():
            # Parents
            for i in range(1, parent_count + 1):
                slug = f"seed-cat-p{i}"
                name = f"Seed Category Parent {i}"
                cat, created = Category.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": f"Seed parent category {i}",
                        "is_active": True,
                        "parent": None,
                    },
                )
                categories.append(cat)
                parents.append(cat)
                if created:
                    self.summary["categories_created"] += 1
                else:
                    self.summary["categories_updated"] += 1

            # Children
            child_idx = 1
            parent_idx = 0
            while child_idx <= child_target:
                parent = parents[parent_idx % len(parents)]
                slug = f"seed-cat-p{parent_idx % len(parents) + 1}-c{(child_idx - 1) // len(parents) + 1}"
                name = f"Seed Category Child {child_idx}"
                cat, created = Category.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": f"Seed child category {child_idx}",
                        "is_active": True,
                        "parent": parent,
                    },
                )
                categories.append(cat)
                if created:
                    self.summary["categories_created"] += 1
                else:
                    self.summary["categories_updated"] += 1
                child_idx += 1
                parent_idx += 1

        return categories

    def _seed_tags(self, count):
        count = max(1, count)
        tags = []
        with transaction.atomic():
            for i in range(1, count + 1):
                slug = f"seed-tag-{i}"
                name = f"Seed Tag {i}"
                tag, created = Tag.objects.update_or_create(slug=slug, defaults={"name": name})
                tags.append(tag)
                if created:
                    self.summary["tags_created"] += 1
                else:
                    self.summary["tags_updated"] += 1
        return tags

    def _seed_courses(
        self,
        *,
        count,
        categories,
        tags,
        instructors,
        published_ratio,
        sessions_min,
        sessions_max,
    ):
        count = max(0, count)
        if not instructors:
            self.stdout.write(self.style.WARNING("No instructors found; skipping catalogue seeding."))
            return []
        if not categories:
            self.stdout.write(self.style.WARNING("No categories available; skipping catalogue seeding."))
            return []
        if not tags:
            self.stdout.write(self.style.WARNING("No tags available; skipping catalogue seeding."))
            return []

        sessions_min = max(1, sessions_min)
        sessions_max = max(sessions_min, sessions_max)
        published_ratio = min(max(0.0, published_ratio), 1.0)

        all_courses = []
        with transaction.atomic():
            for i in range(1, count + 1):
                slug = f"seed-course-{i:04d}"
                title = f"Seed Course {i:04d}"
                category = categories[(i - 1) % len(categories)]
                instructor = instructors[(i - 1) % len(instructors)]
                is_published = self.rng.random() < published_ratio
                objectives = [
                    f"Understand core concept {j} for {title}"
                    for j in range(1, 5)
                ]
                defaults = {
                    "title": title,
                    "subtitle": f"Production-like seed course {i}",
                    "description": f"Seeded long-form description for {title}.",
                    "short_description": f"Short summary for {title}.",
                    "subcategory": f"seed-subcategory-{(i % 8) + 1}",
                    "category": category,
                    "level": self.rng.choice(
                        [Course.Level.BEGINNER, Course.Level.INTERMEDIATE, Course.Level.ADVANCED]
                    ),
                    "price": Decimal(str(self.rng.choice([0, 19.99, 29.99, 49.99, 79.99, 129.99]))),
                    "currency": "USD",
                    "discount_percentage": self.rng.choice([0, 0, 0, 10, 15, 20]),
                    "duration_hours": self.rng.randint(2, 48),
                    "duration_minutes": self.rng.randint(0, 59),
                    "duration_weeks": self.rng.randint(1, 12),
                    "total_sessions": 0,  # updated after session seeding
                    "instructor": instructor,
                    "created_by": instructor,
                    "thumbnail": f"https://cdn.example.com/seed/{slug}.jpg"
                    if is_published
                    else None,
                    "banner": f"https://cdn.example.com/seed/{slug}-banner.jpg",
                    "trailer_video_url": f"https://cdn.example.com/seed/{slug}-trailer.mp4",
                    "prerequisites": "Basic foundational knowledge.",
                    "learning_objectives": "\n".join(objectives),
                    "learning_objectives_list": objectives,
                    "target_audience": "Professionals and learners in staging demos.",
                    "status": Course.Status.PUBLISHED if is_published else Course.Status.DRAFT,
                    "featured": self.rng.random() < 0.2,
                    "published_at": timezone.now() if is_published else None,
                    "access_duration": "lifetime",
                    "allow_self_enrollment": True,
                    "is_public": is_published,
                    "certificate_on_completion": self.rng.random() < 0.6,
                    "enable_discussions": True,
                    "sequential_learning": self.rng.random() < 0.5,
                    "enrollment_limit": None,
                    "start_date": None,
                    "end_date": None,
                    "grading_config": {},
                    "meta_title": f"{title} | Seed",
                    "meta_description": f"Meta description for {title}",
                    "meta_keywords": "seed,staging,course",
                }
                course, created = Course.objects.update_or_create(slug=slug, defaults=defaults)
                all_courses.append(course)
                if created:
                    self.summary["courses_created"] += 1
                else:
                    self.summary["courses_updated"] += 1

                tag_count = self.rng.randint(3, min(8, len(tags)))
                course.tags.set(self.rng.sample(tags, tag_count))

                session_count = self.rng.randint(sessions_min, sessions_max)
                self._seed_sessions_for_course(course, session_count)

        return all_courses

    def _seed_sessions_for_course(self, course, session_count):
        for order in range(1, session_count + 1):
            defaults = {
                "title": f"{course.title} - Session {order}",
                "description": f"Seed session {order} for {course.title}",
                "session_type": Session.SessionType.VIDEO,
                "status": Session.Status.PUBLISHED
                if course.status == Course.Status.PUBLISHED
                else Session.Status.DRAFT,
                "video_duration_seconds": self.rng.randint(300, 3600),
                "video_url": f"https://cdn.example.com/seed/{course.slug}/session-{order}.mp4",
                "content_text": f"Learning content for session {order}.",
                "is_free_preview": order == 1,
                "is_mandatory": True,
            }
            session, created = Session.objects.get_or_create(
                course=course, order=order, defaults=defaults
            )
            if not created:
                for field, value in defaults.items():
                    setattr(session, field, value)
                session.save()
                self.summary["sessions_updated"] += 1
            else:
                self.summary["sessions_created"] += 1

        # Keep course total in sync.
        real_count = course.sessions.count()
        if course.total_sessions != real_count:
            course.total_sessions = real_count
            course.save(update_fields=["total_sessions"])

    def _seed_enrollments_and_progress(
        self,
        *,
        learners,
        courses,
        enroll_min,
        enroll_max,
        with_progress,
        with_certificates,
    ):
        if not learners:
            self.stdout.write(self.style.WARNING("No learners found; skipping enrollment seeding."))
            return
        # Enrollments should mimic production behavior by targeting only published
        # seed courses, even if the incoming `courses` list contains drafts.
        published_courses = list(
            Course.objects.filter(slug__startswith="seed-", status=Course.Status.PUBLISHED).order_by("id")
        )
        if not published_courses:
            self.stdout.write(
                self.style.WARNING("No published seed courses found; skipping enrollment seeding.")
            )
            return

        enroll_min = max(1, enroll_min)
        enroll_max = max(enroll_min, enroll_max)

        with transaction.atomic():
            for learner in learners:
                available_count = len(published_courses)
                if available_count == 0:
                    continue

                lower_bound = min(enroll_min, available_count)
                upper_bound = min(enroll_max, available_count)
                count = self.rng.randint(lower_bound, upper_bound)
                selected_courses = self.rng.sample(published_courses, count)
                for course in selected_courses:
                    enrollment, created = Enrollment.objects.get_or_create(
                        user=learner,
                        course=course,
                        defaults={
                            "status": Enrollment.Status.ACTIVE,
                            "paid_amount": course.price,
                            "currency": course.currency,
                            "organization": None,
                        },
                    )
                    if created:
                        self.summary["enrollments_created"] += 1
                    else:
                        self.summary["enrollments_existing"] += 1

                    completed_ratio = 0.0
                    if with_progress:
                        completed_ratio = self._seed_progress(enrollment)

                    if with_certificates and completed_ratio >= 0.9:
                        self._ensure_certificate(enrollment)

    def _seed_progress(self, enrollment):
        sessions = list(enrollment.course.sessions.order_by("order"))
        if not sessions:
            return 0.0

        complete_count = self.rng.randint(0, len(sessions))
        for idx, session in enumerate(sessions):
            is_completed = idx < complete_count
            progress, created = SessionProgress.objects.get_or_create(
                enrollment=enrollment,
                session=session,
                defaults={
                    "is_started": True,
                    "is_completed": is_completed,
                    "time_spent_seconds": self.rng.randint(120, 3600),
                    "notes": "",
                    "started_at": timezone.now(),
                    "completed_at": timezone.now() if is_completed else None,
                },
            )
            if created:
                self.summary["progress_created"] += 1
            else:
                progress.is_started = True
                progress.is_completed = is_completed
                progress.time_spent_seconds = max(progress.time_spent_seconds, self.rng.randint(120, 3600))
                progress.started_at = progress.started_at or timezone.now()
                progress.completed_at = timezone.now() if is_completed else None
                progress.save()
                self.summary["progress_updated"] += 1

        ratio = complete_count / len(sessions)
        enrollment.progress_percentage = Decimal(str(round(ratio * 100, 2)))
        if ratio >= 0.9:
            enrollment.status = Enrollment.Status.COMPLETED
            enrollment.completed_at = timezone.now()
        else:
            enrollment.status = Enrollment.Status.ACTIVE
            enrollment.completed_at = None
        enrollment.save(update_fields=["progress_percentage", "status", "completed_at"])
        return ratio

    def _ensure_certificate(self, enrollment):
        if enrollment.status != Enrollment.Status.COMPLETED:
            return

        certificate, created = Certificate.objects.get_or_create(enrollment=enrollment)
        if created:
            self.summary["certificates_created"] += 1
        else:
            self.summary["certificates_existing"] += 1

        if not enrollment.certificate_issued:
            enrollment.certificate_issued = True
            enrollment.certificate_issued_at = certificate.issued_at
            enrollment.save(update_fields=["certificate_issued", "certificate_issued_at"])

    def _unique_username(self, base):
        candidate = slugify(base).replace("-", "")[:150] or "seeduser"
        if not User.objects.filter(username=candidate).exists():
            return candidate
        i = 2
        while User.objects.filter(username=f"{candidate}{i}").exists():
            i += 1
        return f"{candidate}{i}"

    def _print_summary(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seeding complete. Summary:"))
        for key in [
            "users_created",
            "users_updated",
            "users_skipped",
            "categories_created",
            "categories_updated",
            "tags_created",
            "tags_updated",
            "courses_created",
            "courses_updated",
            "sessions_created",
            "sessions_updated",
            "enrollments_created",
            "enrollments_existing",
            "progress_created",
            "progress_updated",
            "certificates_created",
            "certificates_existing",
        ]:
            self.stdout.write(f"  - {key}: {self.summary[key]}")
