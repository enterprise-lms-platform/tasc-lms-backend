"""
Badge evaluation engine.

Central function `check_and_award_badges(user, criteria_types=None)` queries
the user's stats, compares against Badge thresholds, and bulk-creates any
newly earned UserBadge records.
"""
import logging
from django.db.models import Q

logger = logging.getLogger(__name__)


def _get_user_stat(user, criteria_type):
    """
    Return the current numeric value for a given criteria_type.
    """
    from apps.learning.models import (
        Enrollment, Certificate, QuizSubmission, QuizAnswer,
        Discussion, Submission,
    )
    from apps.catalogue.models import CourseReview

    if criteria_type == 'certificates_count' or criteria_type == 'first_certificate':
        return Certificate.objects.filter(enrollment__user=user).count()

    elif criteria_type == 'enrollments_count':
        return Enrollment.objects.filter(user=user).count()

    elif criteria_type == 'quiz_submissions_count':
        return QuizSubmission.objects.filter(enrollment__user=user).count()

    elif criteria_type == 'quiz_perfect_score':
        # Check if any quiz submission scored full marks (score == max_score)
        from django.db.models import F
        perfect = QuizSubmission.objects.filter(
            enrollment__user=user
        ).filter(score=F('max_score'), max_score__gt=0).exists()
        return 1 if perfect else 0

    elif criteria_type == 'quiz_pass_streak':
        # Count consecutive passed quizzes (most recent first)
        submissions = QuizSubmission.objects.filter(
            enrollment__user=user
        ).order_by('-submitted_at').values_list('passed', flat=True)
        streak = 0
        for passed in submissions:
            if passed:
                streak += 1
            else:
                break
        return streak

    elif criteria_type == 'assignment_full_marks':
        # Check if any graded submission got full marks
        full_marks = Submission.objects.filter(
            enrollment__user=user,
            status='graded',
        ).select_related('assignment').all()
        for sub in full_marks:
            if sub.assignment and sub.score is not None:
                if sub.score >= sub.assignment.max_points:
                    return 1
        return 0

    elif criteria_type == 'discussions_count':
        return Discussion.objects.filter(user=user).count()

    elif criteria_type == 'reviews_count':
        return CourseReview.objects.filter(user=user).count()

    elif criteria_type == 'profile_complete':
        # Check avatar, bio, and phone are filled
        has_avatar = bool(getattr(user, 'avatar', None) or getattr(user, 'profile_image', None))
        has_bio = bool(getattr(user, 'bio', ''))
        has_phone = bool(getattr(user, 'phone_number', '') or getattr(user, 'phone', ''))
        return 1 if (has_avatar and has_bio and has_phone) else 0

    elif criteria_type == 'subscriptions_count':
        try:
            from apps.payments.models import UserSubscription
            return UserSubscription.objects.filter(user=user).count()
        except (ImportError, Exception):
            return 0

    elif criteria_type == 'login_streak':
        try:
            from apps.accounts.models import UserSession
            from django.utils import timezone
            from datetime import timedelta

            dates = list(
                UserSession.objects.filter(
                    user=user, is_active=True,
                )
                .values_list('created_at__date', flat=True)
                .distinct()
                .order_by('-created_at__date')[:30]
            )
            if not dates:
                return 0
            today = timezone.now().date()
            streak = 0
            expected = today
            for d in dates:
                if d == expected:
                    streak += 1
                    expected -= timedelta(days=1)
                else:
                    break
            return streak
        except (ImportError, Exception):
            return 0

    return 0


def check_and_award_badges(user, criteria_types=None):
    """
    Evaluate badge criteria for a user and award any newly earned badges.

    Args:
        user: The User instance to evaluate.
        criteria_types: Optional list of criteria_type strings to check.
                       If None, checks all badge criteria.

    Returns:
        List of newly created UserBadge instances.
    """
    from apps.learning.models import Badge, UserBadge

    # Get badges to evaluate
    badges_qs = Badge.objects.all()
    if criteria_types:
        badges_qs = badges_qs.filter(criteria_type__in=criteria_types)

    # Get already earned badge IDs for this user
    already_earned = set(
        UserBadge.objects.filter(user=user).values_list('badge_id', flat=True)
    )

    # Evaluate each badge
    newly_earned = []
    # Cache stats per criteria_type to avoid redundant queries
    stat_cache = {}

    for badge in badges_qs:
        if badge.id in already_earned:
            continue

        ct = badge.criteria_type
        if ct not in stat_cache:
            stat_cache[ct] = _get_user_stat(user, ct)

        if stat_cache[ct] >= badge.criteria_value:
            newly_earned.append(
                UserBadge(user=user, badge=badge)
            )

    # Bulk create, ignoring any race-condition duplicates
    if newly_earned:
        created = UserBadge.objects.bulk_create(newly_earned, ignore_conflicts=True)
        logger.info(
            f"Awarded {len(created)} badge(s) to user {user.id}: "
            f"{[ub.badge.slug for ub in newly_earned]}"
        )

        # Create in-app notifications for each earned badge
        try:
            from apps.notifications.models import Notification
            notifications = []
            for ub in newly_earned:
                badge = ub.badge
                notifications.append(
                    Notification(
                        user=user,
                        type=Notification.Type.MILESTONE,
                        title=f"Badge Unlocked: {badge.name}",
                        description=badge.description,
                        link="/learner/badges",
                    )
                )
            if notifications:
                Notification.objects.bulk_create(notifications, ignore_conflicts=True)
        except Exception as e:
            logger.warning(f"Failed to create badge notifications for user {user.id}: {e}")

        return newly_earned

    return []
