from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Invoice(models.Model):
    """
    Invoice represents a billing document for payments.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        OVERDUE = 'overdue', 'Overdue'
        CANCELLED = 'cancelled', 'Cancelled'

    class InvoiceType(models.TextChoices):
        INDIVIDUAL = 'individual', 'Individual Purchase'
        ORGANIZATION = 'organization', 'Organization Purchase'
        SUBSCRIPTION = 'subscription', 'Subscription'

    # Basic Information
    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.INDIVIDUAL)

    # Customer
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices'
    )
    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices'
    )

    # Customer Details Snapshot
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_address = models.TextField(blank=True)
    customer_city = models.CharField(max_length=100, blank=True)
    customer_country = models.CharField(max_length=100, blank=True)

    # Invoice Details
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Financials
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Currency
    currency = models.CharField(max_length=3, default='USD')

    # Notes
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    # PDF
    invoice_pdf_url = models.URLField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['user']),
            models.Index(fields=['organization']),
            models.Index(fields=['status']),
            models.Index(fields=['-issue_date']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer_name}"

    def generate_invoice_number(self):
        """Generate a unique invoice number"""
        import uuid
        timestamp = timezone.now().strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:8].upper()
        return f"INV-{timestamp}-{unique_id}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        super().save(*args, **kwargs)

    @property
    def remaining_amount(self):
        return self.total_amount - self.paid_amount

    @property
    def is_paid(self):
        return self.paid_amount >= self.total_amount


class InvoiceItem(models.Model):
    """
    InvoiceItem represents individual line items in an invoice.
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    
    # Item details
    item_type = models.CharField(
        max_length=50,
        choices=[
            ('course', 'Course'),
            ('subscription', 'Subscription'),
            ('other', 'Other'),
        ],
        default='course'
    )
    item_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.CharField(max_length=255)
    
    # Quantity and pricing
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # References
    enrollment = models.ForeignKey(
        'learning.Enrollment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_items'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.description} - {self.invoice.invoice_number}"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    @property
    def tax_amount(self):
        return self.subtotal * (self.tax_rate / 100)

    @property
    def total(self):
        return self.subtotal + self.tax_amount


class Transaction(models.Model):
    """
    Transaction represents payment transactions.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    class PaymentMethod(models.TextChoices):
        CREDIT_CARD = 'credit_card', 'Credit Card'
        DEBIT_CARD = 'debit_card', 'Debit Card'
        PAYPAL = 'paypal', 'PayPal'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        MOBILE_MONEY = 'mobile_money', 'Mobile Money'
        GOOGLE_PAY = 'google_pay', 'Google Pay'
        APPLE_PAY = 'apple_pay', 'Apple Pay'
        OTHER = 'other', 'Other'

    # Invoice
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    
    # User
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    
    # Transaction details
    transaction_id = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Payment method
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CREDIT_CARD)
    payment_provider = models.CharField(max_length=50, blank=True)  # Stripe, PayPal, etc.
    
    # Gateway details
    gateway_transaction_id = models.CharField(max_length=255, blank=True, null=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['user']),
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.transaction_id} - {self.amount} {self.currency}"

    def generate_transaction_id(self):
        """Generate a unique transaction ID"""
        import uuid
        timestamp = timezone.now().strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:8].upper()
        return f"TXN-{timestamp}-{unique_id}"

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = self.generate_transaction_id()
        super().save(*args, **kwargs)


class PaymentMethod(models.Model):
    """
    PaymentMethod represents saved payment methods for users.
    """
    class MethodType(models.TextChoices):
        CREDIT_CARD = 'credit_card', 'Credit Card'
        DEBIT_CARD = 'debit_card', 'Debit Card'
        PAYPAL = 'paypal', 'PayPal'
        BANK_ACCOUNT = 'bank_account', 'Bank Account'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_methods'
    )
    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='payment_methods'
    )
    
    # Method details
    method_type = models.CharField(max_length=20, choices=MethodType.choices)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Card details (encrypted)
    card_last_four = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=20, blank=True)
    card_expiry_month = models.PositiveIntegerField(null=True, blank=True)
    card_expiry_year = models.PositiveIntegerField(null=True, blank=True)
    
    # PayPal
    paypal_email = models.EmailField(blank=True, null=True)
    
    # Bank account
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_last_four = models.CharField(max_length=4, blank=True)
    
    # Gateway token
    gateway_token = models.CharField(max_length=255, blank=True)
    payment_provider = models.CharField(max_length=50, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        if self.method_type == 'credit_card':
            return f"{self.card_brand} **** {self.card_last_four}"
        elif self.method_type == 'paypal':
            return f"PayPal - {self.paypal_email}"
        return f"{self.method_type}"

    @property
    def is_expired(self):
        """Check if card is expired"""
        if self.method_type in ['credit_card', 'debit_card']:
            if self.card_expiry_month and self.card_expiry_year:
                from datetime import date
                today = date.today()
                expiry_date = date(self.card_expiry_year, self.card_expiry_month, 1)
                return today > expiry_date
        return False


class Subscription(models.Model):
    """
    Subscription represents subscription plans.
    """
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        ARCHIVED = 'archived', 'Archived'

    # Basic Information
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    billing_cycle = models.CharField(
        max_length=20,
        choices=[
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        default='monthly'
    )
    
    # Features and limits
    features = models.JSONField(default=list, blank=True)
    max_courses = models.PositiveIntegerField(null=True, blank=True)
    max_users = models.PositiveIntegerField(null=True, blank=True)
    
    # Trial
    trial_days = models.PositiveIntegerField(default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price', 'name']

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency}/{self.billing_cycle}"


class UserSubscription(models.Model):
    """
    UserSubscription represents user's active subscriptions.
    """
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'

    # User and subscription
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subscriptions'
    )
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name='user_subscriptions')
    
    # Status and dates
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    
    # Auto-renewal
    auto_renew = models.BooleanField(default=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Pricing snapshot
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['organization']),
        ]

    def __str__(self):
        user_name = self.user.email if self.user else self.organization.name
        return f"{user_name} - {self.subscription.name}"

    @property
    def is_trial(self):
        if self.trial_end_date:
            return timezone.now() <= self.trial_end_date
        return False

    @property
    def is_active(self):
        if self.status != self.Status.ACTIVE:
            return False
        if self.end_date and timezone.now() > self.end_date:
            return False
        return True