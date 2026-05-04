from django.core.cache import cache
from django.http import JsonResponse


class MaintenanceModeMiddleware:
    """
    Returns 503 for all non-superadmin API requests when maintenance mode is active.
    Superadmins and unauthenticated requests to public routes pass through unaffected.
    """

    # Paths that always pass through (auth + public)
    EXEMPT_PREFIXES = (
        '/api/v1/auth/',
        '/api/v1/superadmin/',
        '/api/v1/accounts/me/',
        '/admin/',
        '/api/schema/',
        '/api/docs/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if cache.get('system:maintenance_mode', False):
            # Always let exempt paths through
            if not any(request.path.startswith(p) for p in self.EXEMPT_PREFIXES):
                user = getattr(request, 'user', None)
                role = getattr(user, 'role', None) if user and user.is_authenticated else None
                if role != 'tasc_admin':
                    message = cache.get(
                        'system:maintenance_message',
                        'The platform is currently under maintenance. Please check back shortly.',
                    )
                    return JsonResponse({'detail': message, 'maintenance': True}, status=503)

        return self.get_response(request)
