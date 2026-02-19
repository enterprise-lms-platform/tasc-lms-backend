"""Audit logging service."""


def log_event(
    *,
    actor=None,
    action,
    resource,
    details="",
    request=None,
    resource_id=None,
    metadata=None,
    organization=None,
):
    """
    Create an AuditLog entry.
    - actor: User instance or None (system actions)
    - action: one of login, logout, created, updated, deleted
    - resource: one of user, course, organization, payment
    - details: free-text description
    - request: HttpRequest (used to capture IP)
    - resource_id: optional resource identifier
    - metadata: optional JSON dict
    - organization: optional Organization (inferred from actor if not provided)
    """
    from .models import AuditLog

    actor_name = ""
    actor_email = ""
    if actor:
        fn = getattr(actor, "get_full_name", None)
        actor_name = (fn() if callable(fn) else "") or getattr(actor, "email", "") or ""
        actor_email = getattr(actor, "email", "") or ""
        if organization is None and hasattr(actor, "memberships"):
            m = actor.memberships.first()
            if m:
                organization = m.organization

    ip_address = None
    if request:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            ip_address = xff.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR")

    AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        actor_email=actor_email,
        action=action,
        resource=resource,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        organization=organization,
        metadata=metadata,
    )
