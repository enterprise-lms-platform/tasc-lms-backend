import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalogue.models import Category, Course, Session, Tag
from apps.learning.models import Certificate, Enrollment, SessionProgress

User = get_user_model()

SEED_COURSE_TITLES = [
    "ISO INTERGRATED MANAGEMENT SYSTEMS-LEAD IMPLEMENTER COURSE",
    "MANUAL HANDLING",
    "WORK AT HEIGHT SAFETY",
    "ROAD SAFETY AWARENESS",
    "COSHH",
    "ISO INTERGRATED MANAGEMENT SYSTEM-INTERNAL AUDITOR",
    "LEADERSHIP",
    "FIRE SAFETY",
    "FIRST AID",
    "WATER SAFETY TRAINING",
    "HYDROGEN SULPHIDE AWARENESS",
    "ENVIRONMENTAL AWARENESS",
    "CRITICAL THINKING",
    "FALL PROTECTION COURSE",
    "FOLK LIFT OPERATOR",
    "ENGINEER LEAD ASSESSMENT",
    "TESTING AND REPAIRS ASSOCIATE ASSESSMENT",
    "NDT/QC PRE-ASSESSMENT",
    "WELDING INSTRUCTOR'S PRE-ASSESSMENT",
    "WELDING COURSE",
]

TAG_NAME_POOL = [
    "Safety",
    "ISO",
    "Compliance",
    "Quality",
    "Leadership",
    "Operations",
    "Risk Management",
    "Technical Skills",
    "Assessment",
    "Workplace Readiness",
]

SESSION_TOPIC_POOL = [
    "Foundations",
    "Core Principles",
    "Applied Practice",
    "Risk Controls",
    "Operational Excellence",
    "Case Study Review",
    "Implementation Workshop",
    "Assessment Preparation",
]


class Command(BaseCommand):
    help = "Seed predictable staging data for users and optional catalogue/learning."

    def add_arguments(self, parser):
        parser.add_argument("--profile", choices=["staging", "demo"], default="staging")
        parser.add_argument("--learners", type=int, default=None)
        parser.add_argument("--instructors", type=int, default=None)
        parser.add_argument("--lms_managers", type=int, default=None)
        parser.add_argument("--finance", type=int, default=None)
        parser.add_argument("--tasc_admins", type=int, default=None)
        parser.add_argument("--org_admins", type=int, default=None)
        parser.add_argument("--password", type=str, default="Pass12345!")
        parser.add_argument("--instructor-emails", type=str, default=None)

        parser.add_argument("--with-catalogue", action="store_true", default=None)
        parser.add_argument("--categories", type=int, default=16)
        parser.add_argument("--tags", type=int, default=35)
        parser.add_argument("--courses", type=int, default=None)
        parser.add_argument("--sessions-min", type=int, default=4)
        parser.add_argument("--sessions-max", type=int, default=12)

        parser.add_argument("--with-enrollments", action="store_true", default=None)
        parser.add_argument("--enrollments-min", type=int, default=None)
        parser.add_argument("--enrollments-max", type=int, default=None)
        parser.add_argument("--with-progress", action="store_true")
        parser.add_argument("--with-certificates", action="store_true")

        parser.add_argument("--reset", action="store_true")

    def handle(self, *args, **options):
        options = self._resolve_profile_defaults(options)
        self.profile = options["profile"]
        self.slug_prefix = "stg-seed-" if self.profile == "staging" else "demo-seed-"
        self.rng = random.Random(42)
        self.demo_instructor_emails = []
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
            self._reset_seed_data(options)

        if self.profile == "demo":
            user_index = {
                "learners": [],
                "instructors": [],
                "lms_managers": [],
                "finance": [],
                "tasc_admins": [],
                "org_admins": [],
            }
            instructors = self._get_demo_instructors(options["instructor_emails"])
            self.demo_instructor_emails = [u.email for u in instructors]
        else:
            user_index = self._seed_users(options)
            instructors = user_index["instructors"]

        if options["with_catalogue"]:
            categories = self._seed_categories(options["categories"])
            tags = self._seed_tags(options["tags"])
            courses = self._seed_courses(
                count=options["courses"],
                categories=categories,
                tags=tags,
                instructors=instructors,
                sessions_min=options["sessions_min"],
                sessions_max=options["sessions_max"],
            )
        else:
            courses = list(
                Course.objects.filter(slug__startswith=f"{self.slug_prefix}course-").order_by("id")
            )

        if self.profile == "staging" and options["with_enrollments"]:
            self._seed_enrollments_and_progress(
                learners=user_index["learners"],
                courses=courses,
                enroll_min=options["enrollments_min"],
                enroll_max=options["enrollments_max"],
                with_progress=options["with_progress"],
                with_certificates=options["with_certificates"],
            )

        self._print_summary()

    def _resolve_profile_defaults(self, options):
        profile_defaults = {
            "staging": {
                "learners": 5,
                "instructors": 2,
                "lms_managers": 2,
                "finance": 2,
                "tasc_admins": 2,
                "org_admins": 2,
                "courses": 20,
                "with_catalogue": True,
                "with_enrollments": True,
                "enrollments_min": 3,
                "enrollments_max": 6,
            },
            "demo": {
                "learners": 0,
                "instructors": 0,
                "lms_managers": 0,
                "finance": 0,
                "tasc_admins": 0,
                "org_admins": 0,
                "courses": 20,
                "with_catalogue": True,
                "with_enrollments": False,
                "enrollments_min": 3,
                "enrollments_max": 6,
            },
        }
        fallback_defaults = {
            "learners": 50,
            "instructors": 15,
            "lms_managers": 5,
            "finance": 3,
            "tasc_admins": 2,
            "org_admins": 2,
            "courses": 120,
            "enrollments_min": 3,
            "enrollments_max": 10,
            "with_catalogue": True,
            "with_enrollments": True,
        }

        selected = profile_defaults[options["profile"]]
        for key, fallback in fallback_defaults.items():
            if options.get(key) is None:
                options[key] = selected.get(key, fallback)

        # Demo must never seed users or enrollments.
        if options["profile"] == "demo":
            options["learners"] = 0 if options.get("learners") is None else options["learners"]
            options["instructors"] = 0 if options.get("instructors") is None else options["instructors"]
            options["lms_managers"] = 0 if options.get("lms_managers") is None else options["lms_managers"]
            options["finance"] = 0 if options.get("finance") is None else options["finance"]
            options["tasc_admins"] = 0 if options.get("tasc_admins") is None else options["tasc_admins"]
            options["org_admins"] = 0 if options.get("org_admins") is None else options["org_admins"]
            options["with_enrollments"] = False

        return options

    def _get_demo_instructors(self, emails_csv):
        raw = (emails_csv or "").strip()
        if not raw:
            raise CommandError(
                "profile=demo requires --instructor-emails with comma-separated existing instructor emails."
            )

        requested = [email.strip().lower() for email in raw.split(",") if email.strip()]
        if not requested:
            raise CommandError(
                "No valid emails found in --instructor-emails. Example: --instructor-emails=a@test.com,b@test.com"
            )

        missing = []
        wrong_role = []
        instructors = []
        for email in requested:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                missing.append(email)
                continue
            if user.role != User.Role.INSTRUCTOR:
                wrong_role.append(f"{email} (role={user.role})")
                continue
            instructors.append(user)

        if missing or wrong_role:
            problems = []
            if missing:
                problems.append(f"Missing users: {', '.join(missing)}")
            if wrong_role:
                problems.append(
                    "Users with non-instructor role: "
                    + ", ".join(wrong_role)
                    + f" (expected {User.Role.INSTRUCTOR})"
                )
            raise CommandError(
                "Invalid --instructor-emails for demo profile. "
                + " | ".join(problems)
                + " | Create/fix these users and rerun."
            )
        return instructors

    def _reset_seed_data(self, options):
        self.stdout.write(
            self.style.WARNING(
                f"Resetting seed data for profile={self.profile}, prefix='{self.slug_prefix}'..."
            )
        )
        with transaction.atomic():
            course_qs = Course.objects.filter(slug__startswith=f"{self.slug_prefix}course-")
            deleted_courses, _ = course_qs.delete()
            deleted_categories, _ = Category.objects.filter(
                slug__startswith=f"{self.slug_prefix}cat-"
            ).delete()
            deleted_tags, _ = Tag.objects.filter(
                slug__startswith=f"{self.slug_prefix}tag-"
            ).delete()
            deleted_users = 0

            if self.profile == "staging":
                staged_user_emails = self._staging_user_emails(options)
                if staged_user_emails:
                    deleted_users, _ = User.objects.filter(email__in=staged_user_emails).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Reset complete: "
                f"{deleted_courses} course-related rows, "
                f"{deleted_categories} categories, "
                f"{deleted_tags} tags, "
                f"{deleted_users} users."
            )
        )

    def _staging_user_emails(self, options):
        cohorts = [
            ("stg-learner", options["learners"]),
            ("stg-instructor", options["instructors"]),
            ("stg-manager", options["lms_managers"]),
            ("stg-finance", options["finance"]),
            ("stg-admin", options["tasc_admins"]),
            ("stg-orgadmin", options["org_admins"]),
        ]
        emails = []
        for prefix, count in cohorts:
            for i in range(1, max(0, count) + 1):
                emails.append(f"{prefix}{i}@test.com")
        return emails

    def _seed_users(self, options):
        cohorts = [
            ("stg-learner", "stglearner", "learners", options["learners"], User.Role.LEARNER),
            (
                "stg-instructor",
                "stginstructor",
                "instructors",
                options["instructors"],
                User.Role.INSTRUCTOR,
            ),
            ("stg-manager", "stgmanager", "lms_managers", options["lms_managers"], User.Role.LMS_MANAGER),
            ("stg-finance", "stgfinance", "finance", options["finance"], User.Role.FINANCE),
            ("stg-admin", "stgadmin", "tasc_admins", options["tasc_admins"], User.Role.TASC_ADMIN),
            ("stg-orgadmin", "stgorgadmin", "org_admins", options["org_admins"], User.Role.ORG_ADMIN),
        ]
        password = options["password"]
        index = {k: [] for _, _, k, _, _ in cohorts}

        with transaction.atomic():
            for email_prefix, username_prefix, key, count, role in cohorts:
                for i in range(1, max(0, count) + 1):
                    email = f"{email_prefix}{i}@test.com"
                    username = f"{username_prefix}{i}"
                    first_name = key.rstrip("s").replace("_", " ").title()
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
        parent_names = ["Safety", "Quality", "Leadership", "Operations", "Compliance", "Technical Skills"]
        child_names = [
            "Foundations",
            "Practitioner",
            "Advanced",
            "Assessment",
            "Implementation",
            "Best Practices",
        ]

        with transaction.atomic():
            for i in range(1, parent_count + 1):
                slug = f"{self.slug_prefix}cat-p{i}"
                name = parent_names[(i - 1) % len(parent_names)]
                cat, created = Category.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": f"{name} learning tracks and professional development paths.",
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

            child_idx = 1
            parent_idx = 0
            while child_idx <= child_target:
                parent = parents[parent_idx % len(parents)]
                parent_number = parent_idx % len(parents) + 1
                child_number = (child_idx - 1) // len(parents) + 1
                slug = f"{self.slug_prefix}cat-p{parent_number}-c{child_number}"
                base = child_names[(child_idx - 1) % len(child_names)]
                name = f"{parent.name} - {base}"
                cat, created = Category.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": f"{name} courses for practical capability building.",
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
                slug = f"{self.slug_prefix}tag-{i:03d}"
                name = TAG_NAME_POOL[(i - 1) % len(TAG_NAME_POOL)]
                if i > len(TAG_NAME_POOL):
                    name = f"{name} {i}"
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

        all_courses = []
        with transaction.atomic():
            for i in range(1, count + 1):
                slug = f"{self.slug_prefix}course-{i:04d}"
                title = self._course_title_for(i)
                category = categories[(i - 1) % len(categories)]
                instructor = instructors[(i - 1) % len(instructors)]
                is_published = i <= 12
                objectives = [
                    f"Apply {title.lower()} principle {j} in workplace scenarios."
                    for j in range(1, 5)
                ]
                defaults = {
                    "title": title,
                    "subtitle": f"Professional training pathway #{i}",
                    "description": f"Comprehensive training content for {title}.",
                    "short_description": f"Practical overview and outcomes for {title}.",
                    "subcategory": f"track-{(i % 8) + 1}",
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
                    "thumbnail": f"https://cdn.example.com/seed/{slug}.jpg"
                    if is_published
                    else None,
                    "banner": f"https://cdn.example.com/seed/{slug}-banner.jpg",
                    "trailer_video_url": f"https://cdn.example.com/seed/{slug}-trailer.mp4",
                    "prerequisites": "Basic foundational knowledge.",
                    "learning_objectives": "\n".join(objectives),
                    "learning_objectives_list": objectives,
                    "target_audience": "Professionals and learners seeking certified capability growth.",
                    "status": Course.Status.PUBLISHED if is_published else Course.Status.DRAFT,
                    "featured": self.rng.random() < 0.2,
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
                    "meta_keywords": "training,safety,quality,professional",
                }
                if hasattr(Course, "instructor"):
                    defaults["instructor"] = instructor
                if hasattr(Course, "created_by"):
                    defaults["created_by"] = instructor
                course, created = Course.objects.update_or_create(slug=slug, defaults=defaults)
                all_courses.append(course)
                if created:
                    self.summary["courses_created"] += 1
                else:
                    self.summary["courses_updated"] += 1

                if is_published and course.published_at is None:
                    course.published_at = timezone.now()
                    course.save(update_fields=["published_at"])
                elif not is_published and course.published_at is not None:
                    course.published_at = None
                    course.save(update_fields=["published_at"])

                min_tags = 1
                max_tags = min(8, len(tags))
                tag_count = self.rng.randint(min_tags, max_tags)
                course.tags.set(self.rng.sample(tags, tag_count))

                session_count = self.rng.randint(sessions_min, sessions_max)
                self._seed_sessions_for_course(course, session_count)

        return all_courses

    def _course_title_for(self, index):
        if index <= len(SEED_COURSE_TITLES):
            return SEED_COURSE_TITLES[index - 1]
        return f"TASC Course {index:03d}"

    def _seed_sessions_for_course(self, course, session_count):
        for order in range(1, session_count + 1):
            topic = SESSION_TOPIC_POOL[(order - 1) % len(SESSION_TOPIC_POOL)]
            defaults = {
                "title": f"Module {order}: {topic}",
                "description": f"{topic} module for {course.title}.",
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

        published_courses = list(
            Course.objects.filter(
                slug__startswith=f"{self.slug_prefix}course-",
                status=Course.Status.PUBLISHED,
            ).order_by("id")
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
        self.stdout.write(f"  - profile: {self.profile}")
        self.stdout.write(f"  - prefix: {self.slug_prefix}")
        if self.profile == "demo":
            used = ", ".join(self.demo_instructor_emails) if self.demo_instructor_emails else "(none)"
            self.stdout.write(f"  - demo_instructors: {used}")
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
