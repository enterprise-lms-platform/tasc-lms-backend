from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid

User = get_user_model()


class Payment(models.Model):
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    )
    
    PAYMENT_METHODS = (
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('pesapal', 'PesaPal'),
        ('mpesa', 'M-Pesa'),
    )
    
    CURRENCIES = (
        ('USD', 'US Dollar'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, choices=CURRENCIES, default='USD')
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    
    # Payment provider references
    provider_payment_id = models.CharField(max_length=255, blank=True, null=True)
    provider_order_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Card/Account details (encrypted)
    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=50, blank=True)
    
    # Webhook tracking
    webhook_received = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'course']),
            models.Index(fields=['provider_payment_id']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.amount} {self.currency}"
    
    def mark_completed(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
        
        # Enroll user in course
        self.course.enrolled_users.add(self.user)


class PaymentWebhook(models.Model):
    """Store webhook events for debugging"""
    provider = models.CharField(max_length=20)
    event_type = models.CharField(max_length=100)
    event_id = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.provider} - {self.event_type}"