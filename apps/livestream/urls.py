from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LivestreamSessionViewSet,
    LivestreamAttendanceViewSet,
    LivestreamWebhookView,
    TimezoneViewSet
)

# Create router for main endpoints
router = DefaultRouter()
router.register(r'livestreams', LivestreamSessionViewSet, basename='livestream')
router.register(r'livestream-attendance', LivestreamAttendanceViewSet, basename='livestream-attendance')
router.register(r'timezone', TimezoneViewSet, basename='timezone')

urlpatterns = [
    # Include all router URLs
    path('', include(router.urls)),
    
    # Webhook endpoints (no authentication)
    path('webhooks/', include([
        path('zoom/', LivestreamWebhookView.as_view({'post': 'zoom_webhook'}), name='zoom-webhook'),
        path('validate/', LivestreamWebhookView.as_view({'get': 'validate_webhook'}), name='webhook-validate'),
    ])),
    
    # Calendar ICS download (public for sharing)
    path('livestreams/<uuid:pk>/ics/', 
         LivestreamSessionViewSet.as_view({'get': 'download_ics'}), 
         name='livestream-ics'),
    
    # Join links (redirects to Zoom)
    path('livestreams/<uuid:pk>/join/', 
         LivestreamSessionViewSet.as_view({'get': 'join'}), 
         name='livestream-join'),
]