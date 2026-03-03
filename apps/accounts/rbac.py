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
