"""
Management command to seed all 22 badge definitions.
Usage: python manage.py seed_badges
"""
from django.core.management.base import BaseCommand
from apps.learning.models import Badge


BADGE_SEED_DATA = [
    # ── Course Completion ──
    {'slug': 'first-course', 'name': 'First Steps', 'description': 'Completed your first course', 'category': 'course_completion', 'criteria_type': 'certificates_count', 'criteria_value': 1, 'icon_url': '/badges/first-course.png', 'order': 1},
    {'slug': 'three-courses', 'name': 'Knowledge Seeker', 'description': 'Completed 3 courses', 'category': 'course_completion', 'criteria_type': 'certificates_count', 'criteria_value': 3, 'icon_url': '/badges/three-courses.png', 'order': 2},
    {'slug': 'five-courses', 'name': 'Dedicated Learner', 'description': 'Completed 5 courses', 'category': 'course_completion', 'criteria_type': 'certificates_count', 'criteria_value': 5, 'icon_url': '/badges/five-courses.png', 'order': 3},
    {'slug': 'ten-courses', 'name': 'Knowledge Master', 'description': 'Completed 10 courses', 'category': 'course_completion', 'criteria_type': 'certificates_count', 'criteria_value': 10, 'icon_url': '/badges/ten-courses.png', 'order': 4},
    {'slug': 'twenty-courses', 'name': 'Scholar', 'description': 'Completed 20 courses', 'category': 'course_completion', 'criteria_type': 'certificates_count', 'criteria_value': 20, 'icon_url': '/badges/twenty-courses.png', 'order': 5},

    # ── Enrollment Milestones ──
    {'slug': 'first-enrollment', 'name': 'Early Bird', 'description': 'Enrolled in your first course', 'category': 'enrollment', 'criteria_type': 'enrollments_count', 'criteria_value': 1, 'icon_url': '/badges/first-enrollment.png', 'order': 1},
    {'slug': 'five-enrollments', 'name': 'Curious Mind', 'description': 'Enrolled in 5 courses', 'category': 'enrollment', 'criteria_type': 'enrollments_count', 'criteria_value': 5, 'icon_url': '/badges/five-enrollments.png', 'order': 2},
    {'slug': 'ten-enrollments', 'name': 'Course Explorer', 'description': 'Enrolled in 10 courses', 'category': 'enrollment', 'criteria_type': 'enrollments_count', 'criteria_value': 10, 'icon_url': '/badges/ten-enrollments.png', 'order': 3},

    # ── Subscription Loyalty ──
    {'slug': 'first-subscription', 'name': 'Supporter', 'description': 'Subscribed for the first time', 'category': 'subscription', 'criteria_type': 'subscriptions_count', 'criteria_value': 1, 'icon_url': '/badges/first-subscription.png', 'order': 1},
    {'slug': 'third-subscription', 'name': 'Loyal Learner', 'description': 'Renewed subscription 3 times', 'category': 'subscription', 'criteria_type': 'subscriptions_count', 'criteria_value': 3, 'icon_url': '/badges/third-subscription.png', 'order': 2},
    {'slug': 'fifth-subscription', 'name': 'Platinum Member', 'description': 'Renewed subscription 5 times', 'category': 'subscription', 'criteria_type': 'subscriptions_count', 'criteria_value': 5, 'icon_url': '/badges/fifth-subscription.png', 'order': 3},

    # ── Assessment Excellence ──
    {'slug': 'first-quiz', 'name': 'Quiz Taker', 'description': 'Completed your first quiz', 'category': 'assessment', 'criteria_type': 'quiz_submissions_count', 'criteria_value': 1, 'icon_url': '/badges/first-quiz.png', 'order': 1},
    {'slug': 'perfect-score', 'name': 'Perfect Score', 'description': 'Scored 100% on any quiz', 'category': 'assessment', 'criteria_type': 'quiz_perfect_score', 'criteria_value': 1, 'icon_url': '/badges/perfect-score.png', 'order': 2},
    {'slug': 'quiz-streak', 'name': 'Quiz Streak', 'description': 'Passed 5 quizzes in a row', 'category': 'assessment', 'criteria_type': 'quiz_pass_streak', 'criteria_value': 5, 'icon_url': '/badges/quiz-streak.png', 'order': 3},
    {'slug': 'assignment-ace', 'name': 'Assignment Ace', 'description': 'Received full marks on an assignment', 'category': 'assessment', 'criteria_type': 'assignment_full_marks', 'criteria_value': 1, 'icon_url': '/badges/assignment-ace.png', 'order': 4},

    # ── Engagement ──
    {'slug': 'first-discussion', 'name': 'Conversation Starter', 'description': 'Posted in a course discussion', 'category': 'engagement', 'criteria_type': 'discussions_count', 'criteria_value': 1, 'icon_url': '/badges/first-discussion.png', 'order': 1},
    {'slug': 'ten-discussions', 'name': 'Community Voice', 'description': 'Made 10 discussion posts', 'category': 'engagement', 'criteria_type': 'discussions_count', 'criteria_value': 10, 'icon_url': '/badges/ten-discussions.png', 'order': 2},
    {'slug': 'first-review', 'name': 'Reviewer', 'description': 'Left your first course review', 'category': 'engagement', 'criteria_type': 'reviews_count', 'criteria_value': 1, 'icon_url': '/badges/first-review.png', 'order': 3},

    # ── Milestones ──
    {'slug': 'profile-complete', 'name': 'Identity', 'description': 'Completed your profile', 'category': 'milestone', 'criteria_type': 'profile_complete', 'criteria_value': 1, 'icon_url': '/badges/profile-complete.png', 'order': 1},
    {'slug': 'seven-day-streak', 'name': 'Week Warrior', 'description': 'Active for 7 consecutive days', 'category': 'milestone', 'criteria_type': 'login_streak', 'criteria_value': 7, 'icon_url': '/badges/seven-day-streak.png', 'order': 2},
    {'slug': 'first-certificate', 'name': 'Certified', 'description': 'Earned your first certificate', 'category': 'milestone', 'criteria_type': 'first_certificate', 'criteria_value': 1, 'icon_url': '/badges/first-certificate.png', 'order': 3},
    {'slug': 'three-certificates', 'name': 'Certificate Collector', 'description': 'Earned 3 certificates', 'category': 'milestone', 'criteria_type': 'certificates_count', 'criteria_value': 3, 'icon_url': '/badges/three-certificates.png', 'order': 4},
]


class Command(BaseCommand):
    help = 'Seed all 22 badge definitions into the Badge table.'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for badge_data in BADGE_SEED_DATA:
            badge, created = Badge.objects.update_or_create(
                slug=badge_data['slug'],
                defaults=badge_data,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Done! {created_count} badges created, {updated_count} updated. '
                f'Total: {Badge.objects.count()} badges in database.'
            )
        )
