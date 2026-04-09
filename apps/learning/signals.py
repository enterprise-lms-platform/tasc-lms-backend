from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from datetime import timedelta

from apps.learning.models import Enrollment, Certificate, QuizSubmission, Discussion, Submission

User = get_user_model()


@receiver(post_save, sender=Enrollment)
def auto_create_certificate(sender, instance, **kwargs):
    """
    Auto-create a certificate when an enrollment status becomes 'completed'.
    """
    if instance.status == Enrollment.Status.COMPLETED:
        # Check if a certificate already exists to avoid duplicates
        if not hasattr(instance, 'certificate'):
            expiry_date = timezone.now() + timedelta(days=365) # 1 year validity
            
            certificate = Certificate.objects.create(
                enrollment=instance,
                expiry_date=expiry_date
            )
            
            # Set the verification URL based on the generated certificate number
            certificate.verification_url = f"{settings.FRONTEND_URL}/certificate/verify?number={certificate.certificate_number}"
            certificate.save(update_fields=['verification_url'])


# ── Badge auto-award signals ──────────────────────────────────

def _award_badges_safe(user, criteria_types):
    """Safely run badge evaluation, catching any errors to avoid breaking the main flow."""
    try:
        from apps.learning.badge_engine import check_and_award_badges
        check_and_award_badges(user, criteria_types=criteria_types)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Badge evaluation error for user {user.id}: {e}")


@receiver(post_save, sender=Certificate)
def award_badges_on_certificate(sender, instance, created, **kwargs):
    """Award course completion and certificate badges when a certificate is created."""
    if created:
        user = instance.enrollment.user
        _award_badges_safe(user, ['certificates_count', 'first_certificate'])


@receiver(post_save, sender=Enrollment)
def award_badges_on_enrollment(sender, instance, created, **kwargs):
    """Award enrollment milestone badges when a new enrollment is created."""
    if created:
        _award_badges_safe(instance.user, ['enrollments_count'])


@receiver(post_save, sender=QuizSubmission)
def award_badges_on_quiz(sender, instance, created, **kwargs):
    """Award assessment badges when a quiz is submitted."""
    if created:
        _award_badges_safe(
            instance.enrollment.user,
            ['quiz_submissions_count', 'quiz_perfect_score', 'quiz_pass_streak'],
        )


@receiver(post_save, sender=Discussion)
def award_badges_on_discussion(sender, instance, created, **kwargs):
    """Award engagement badges when a discussion is created."""
    if created:
        _award_badges_safe(instance.user, ['discussions_count'])


@receiver(post_save, sender=Submission)
def award_badges_on_submission_graded(sender, instance, **kwargs):
    """Award assignment badges when a submission is graded with full marks."""
    if instance.status == 'graded' and instance.grade is not None:
        user = instance.enrollment.user
        _award_badges_safe(user, ['assignment_full_marks'])


@receiver(post_save, sender=User)
def award_badges_on_profile_update(sender, instance, **kwargs):  # noqa: ARG001
    """Award profile_complete badge when user saves their profile."""
    _award_badges_safe(instance, ['profile_complete'])
