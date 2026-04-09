from django.contrib.auth import get_user_model

User = get_user_model()


def is_tasc_admin(user) -> bool:
    return getattr(user, "role", None) == User.Role.TASC_ADMIN


def is_lms_manager(user) -> bool:
    return getattr(user, "role", None) == User.Role.LMS_MANAGER


def is_admin_like(user) -> bool:
    return getattr(user, "role", None) in [User.Role.TASC_ADMIN, User.Role.LMS_MANAGER]


def is_instructor(user) -> bool:
    return getattr(user, "role", None) == User.Role.INSTRUCTOR


def is_course_writer(user) -> bool:
    return getattr(user, "role", None) in [
        User.Role.INSTRUCTOR,
        User.Role.LMS_MANAGER,
        User.Role.TASC_ADMIN,
    ]


def get_active_membership_organization(user):
    """Return user's active org for org-scoped roles, else None."""
    from .models import Membership

    membership = (
        user.memberships.filter(
            role__in=[Membership.Role.ORG_ADMIN, Membership.Role.ORG_MANAGER],
            is_active=True,
        )
        .select_related("organization")
        .first()
    )
    return membership.organization if membership else None
