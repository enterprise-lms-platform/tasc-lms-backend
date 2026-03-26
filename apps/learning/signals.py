from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

from apps.learning.models import Enrollment, Certificate

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
