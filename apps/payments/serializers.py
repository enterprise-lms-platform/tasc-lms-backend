from decimal import Decimal

from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from .models import (
    Payment, Invoice, InvoiceItem, Transaction, 
    PaymentMethod, Subscription, UserSubscription, PaymentWebhook
)
from .models import Payment, PesapalIPN  # Import PesapalIPN model for IPN serializer


class PaymentSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    course_title = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'user_email', 'course', 'course_title', 'organization_name',
            'amount', 'currency', 'payment_method', 'status',
            'provider_payment_id', 'provider_order_id',
            'metadata', 'description',
            'created_at', 'completed_at', 'updated_at',
            'card_last4', 'card_brand', 'webhook_received'
        ]
        read_only_fields = [
            'id', 'created_at', 'completed_at', 'updated_at',
            'metadata', 'user', 'course_title', 'organization_name'
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_course_title(self, obj):
        return obj.course.title if obj.course else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_organization_name(self, obj):
        org = getattr(obj.user, 'organization', None)
        return org.name if org else None


class CreatePaymentSerializer(serializers.Serializer):
    course_id = serializers.UUIDField(required=False)
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHODS)
    currency = serializers.ChoiceField(
        choices=Payment.CURRENCIES, 
        default='USD',
        required=False
    )
    
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        min_value=Decimal('0.01'),
        required=False
    )
    description = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        from apps.catalogue.models import Course
        
        # If course_id provided, validate it exists
        course_id = data.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(id=course_id)
                data['course'] = course
                
                # If amount not provided, use course price
                if 'amount' not in data or data['amount'] is None:
                    data['amount'] = course.price
                    
            except Course.DoesNotExist:
                raise serializers.ValidationError({"course_id": "Course not found"})
        
        # If amount is still not set, require it
        if 'amount' not in data or data['amount'] is None:
            raise serializers.ValidationError({"amount": "Amount is required"})
        
        return data


class PaymentConfirmationSerializer(serializers.Serializer):
    payment_intent_id = serializers.CharField(required=False)
    order_id = serializers.CharField(required=False)
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHODS)


class PaymentWebhookSerializer(serializers.ModelSerializer):
    """Serializer for PaymentWebhook model"""
    
    class Meta:
        model = PaymentWebhook
        fields = [
            'id', 'provider', 'event_type', 'event_id',
            'payload', 'processed', 'processed_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class PaymentStatusSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    details = serializers.JSONField(required=False)


class InvoiceItemSerializer(serializers.ModelSerializer):
    """Serializer for InvoiceItem model."""
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'invoice', 'item_type', 'item_id', 'course',
            'description', 'quantity', 'unit_price', 'tax_rate',
            'subtotal', 'tax_amount', 'total', 'enrollment', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'subtotal', 'tax_amount', 'total']


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model."""
    items = InvoiceItemSerializer(many=True, read_only=True)
    user_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    is_paid = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'invoice_type',
            'user', 'user_name', 'organization', 'organization_name',
            'course', 'course_title', 'payment',
            'customer_name', 'customer_email', 'customer_address',
            'customer_city', 'customer_country',
            'issue_date', 'due_date', 'status',
            'subtotal', 'tax_amount', 'total_amount', 'paid_amount',
            'remaining_amount', 'is_paid',
            'currency', 'notes', 'internal_notes', 'invoice_pdf_url',
            'created_at', 'updated_at', 'paid_at', 'items'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at', 'paid_at']
    
    @extend_schema_field(serializers.CharField)
    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else obj.customer_name
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_course_title(self, obj):
        return obj.course.title if obj.course else None
    
    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_remaining_amount(self, obj):
        return obj.remaining_amount
    
    @extend_schema_field(serializers.BooleanField)
    def get_is_paid(self, obj):
        return obj.is_paid


class InvoiceCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating invoices."""
    
    class Meta:
        model = Invoice
        fields = [
            'user', 'organization', 'course', 'payment', 'invoice_type',
            'customer_name', 'customer_email', 'customer_address',
            'customer_city', 'customer_country',
            'issue_date', 'due_date', 'status',
            'subtotal', 'tax_amount', 'total_amount', 'paid_amount',
            'currency', 'notes', 'internal_notes'
        ]


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model."""
    user_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'invoice', 'invoice_number',
            'user', 'user_name', 'organization', 'organization_name',
            'course', 'course_title',
            'transaction_id', 'amount', 'currency',
        'status', 'payment_method', 'payment_provider',
        'gateway_transaction_id',
        'created_at', 'updated_at', 'completed_at',
            'card_last4', 'card_brand', 'webhook_received'
        ]
        read_only_fields = [
            'id', 'transaction_id', 'created_at', 
            'updated_at', 'completed_at'
        ]
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_user_name(self, obj):
        return obj.user.email if obj.user else obj.organization.name if obj.organization else None
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_course_title(self, obj):
        return obj.course.title if obj.course else None
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_invoice_number(self, obj):
        return obj.invoice.invoice_number if obj.invoice else None


class TransactionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating transactions."""
    
    class Meta:
        model = Transaction
        fields = [
            'invoice', 'user', 'organization', 'course',
            'amount', 'currency', 'payment_method', 'payment_provider',
            'gateway_transaction_id', 'gateway_response'
        ]


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for PaymentMethod model."""
    user_email = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'user', 'user_email', 'organization', 'organization_name',
            'method_type', 'is_default', 'is_active',
            'display_name', 'is_expired',
            'card_last_four', 'card_brand', 'card_expiry_month', 'card_expiry_year',
            'paypal_email', 'bank_name', 'bank_account_last_four',
            'gateway_token', 'payment_provider',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_user_email(self, obj):
        return obj.user.email if obj.user else None
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    @extend_schema_field(serializers.CharField)
    def get_display_name(self, obj):
        return str(obj)
    
    @extend_schema_field(serializers.BooleanField)
    def get_is_expired(self, obj):
        return obj.is_expired


class PaymentMethodCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payment methods."""
    
    class Meta:
        model = PaymentMethod
        fields = [
            'method_type', 'is_default', 'is_active',
            'card_last_four', 'card_brand', 'card_expiry_month', 'card_expiry_year',
            'paypal_email', 'bank_name', 'bank_account_last_four',
            'gateway_token', 'payment_provider'
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for Subscription model."""
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'name', 'description',
            'price', 'currency', 'billing_cycle',
            'duration_days', 'features', 'max_courses', 'max_users', 'trial_days',
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PublicSubscriptionPlanSerializer(serializers.ModelSerializer):
    """Minimal serializer for public landing page pricing. No internal/admin fields."""

    class Meta:
        model = Subscription
        fields = ['id', 'name', 'description', 'price', 'currency', 'billing_cycle', 'features', 'status']


class SubscriptionCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating subscriptions."""

    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.00'))
    trial_days = serializers.IntegerField(min_value=0, required=False)
    duration_days = serializers.IntegerField(min_value=1, required=False)
    max_courses = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    max_users = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    
    class Meta:
        model = Subscription
        fields = [
            'name', 'description',
            'price', 'currency', 'billing_cycle',
            'duration_days', 'features', 'max_courses', 'max_users', 'trial_days',
            'status'
        ]

    def validate_currency(self, value):
        valid_currencies = {choice for choice, _label in Payment.CURRENCIES}
        if value not in valid_currencies:
            raise serializers.ValidationError('Unsupported currency.')
        return value

    def validate_billing_cycle(self, value):
        valid_cycles = {choice for choice, _label in Subscription._meta.get_field('billing_cycle').choices}
        if value not in valid_cycles:
            raise serializers.ValidationError('Unsupported billing cycle.')
        return value

    def validate_status(self, value):
        valid_statuses = {choice for choice, _label in Subscription.Status.choices}
        if value not in valid_statuses:
            raise serializers.ValidationError('Unsupported subscription status.')
        return value

    def validate_features(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('Features must be a list of strings.')
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise serializers.ValidationError('Features must contain only non-empty strings.')
        return [item.strip() for item in value]


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for UserSubscription model."""
    user_email = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    subscription_name = serializers.SerializerMethodField()
    billing_cycle = serializers.SerializerMethodField()
    max_users = serializers.SerializerMethodField()
    is_trial = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'user_email', 'organization', 'organization_name',
            'subscription', 'subscription_name', 'billing_cycle', 'max_users',
            'status', 'start_date', 'end_date', 'trial_end_date',
            'auto_renew', 'cancelled_at', 'cancellation_reason', 'price', 'currency',
            'is_trial', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_user_email(self, obj):
        return obj.user.email if obj.user else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None

    @extend_schema_field(serializers.CharField)
    def get_subscription_name(self, obj):
        return obj.subscription.name

    @extend_schema_field(serializers.CharField)
    def get_billing_cycle(self, obj):
        return obj.subscription.get_billing_cycle_display()

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_max_users(self, obj):
        return obj.subscription.max_users

    @extend_schema_field(serializers.BooleanField)
    def get_is_trial(self, obj):
        return obj.is_trial

    @extend_schema_field(serializers.BooleanField)
    def get_is_active(self, obj):
        return obj.is_active


class SubscriptionStatusSerializer(serializers.Serializer):
    has_active_subscription = serializers.BooleanField()
    status = serializers.CharField()
    is_trial = serializers.BooleanField()
    start_date = serializers.DateTimeField(allow_null=True)
    end_date = serializers.DateTimeField(allow_null=True)
    days_remaining = serializers.IntegerField(allow_null=True)
    in_grace_period = serializers.BooleanField(required=False, default=False)
    grace_days_remaining = serializers.IntegerField(allow_null=True, required=False, default=None)
    approaching_grace_period = serializers.BooleanField(required=False, default=False)
    plan = serializers.DictField(allow_null=True)


class UserSubscriptionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating user subscriptions."""
    is_trial = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = UserSubscription
        fields = [
            'subscription', 'organization',
            'end_date', 'trial_end_date', 'auto_renew', 'is_trial'
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        is_trial = attrs.get('is_trial', False)

        # One-time trial enforcement. We key this off trial_end_date markers.
        if is_trial and user and UserSubscription.objects.filter(user=user, trial_end_date__isnull=False).exists():
            raise serializers.ValidationError({'is_trial': 'Free trial has already been used.'})
        return attrs

    def create(self, validated_data):
        # Prevent client price tampering by snapshotting from the selected plan.
        validated_data.pop('is_trial', None)
        subscription_plan = validated_data['subscription']
        validated_data.setdefault('price', subscription_plan.price)
        validated_data.setdefault('currency', subscription_plan.currency or 'UGX')
        validated_data.setdefault('status', UserSubscription.Status.ACTIVE)
        return super().create(validated_data)
    

class PesapalInitiateSerializer(serializers.Serializer):
    """
    Request body for POST /api/v1/payments/pesapal/initiate/
    Validates and resolves the course + amount before hitting Pesapal.
    """
 
    course_id = serializers.UUIDField(required=False)
    currency = serializers.ChoiceField(
        choices=Payment.CURRENCIES, default="UGX", required=False
    )
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    description = serializers.CharField(required=False, allow_blank=True)
 
    def validate(self, data):
        from apps.catalogue.models import Course
 
        course_id = data.get("course_id")
        if course_id:
            try:
                course = Course.objects.get(id=course_id)
                data["course"] = course
                if not data.get("amount"):
                    data["amount"] = course.price
            except Course.DoesNotExist:
                raise serializers.ValidationError({"course_id": "Course not found."})
 
        if not data.get("amount"):
            raise serializers.ValidationError({"amount": "Amount is required."})
 
        return data
 
 
class PesapalRecurringInitiateSerializer(serializers.Serializer):
    """
    Request body for POST /api/v1/payments/pesapal/recurring/initiate/
    Links a Payment to a UserSubscription and submits a recurring order.
    """
 
    subscription_id = serializers.IntegerField()
    currency = serializers.ChoiceField(
        choices=Payment.CURRENCIES, default="UGX", required=False
    )
 
    def validate_subscription_id(self, value):
        from .models import Subscription
 
        try:
            return Subscription.objects.get(id=value, status="active")
        except Subscription.DoesNotExist:
            raise serializers.ValidationError("Subscription plan not found or inactive.")


class PesapalSubscriptionOneTimeInitiateSerializer(serializers.Serializer):
    """
    Request body for POST /api/v1/payments/pesapal/initiate-subscription-onetime/
    Client sends catalog plan id only; standard Pesapal SubmitOrderRequest (not recurring).
    """

    subscription_id = serializers.IntegerField()
    currency = serializers.ChoiceField(
        choices=Payment.CURRENCIES, default="UGX", required=False
    )

    def validate_subscription_id(self, value):
        from .models import Subscription

        try:
            return Subscription.objects.get(id=value, status="active")
        except Subscription.DoesNotExist:
            raise serializers.ValidationError("Subscription plan not found or inactive.")
 
 
class PesapalWebhookQuerySerializer(serializers.Serializer):
    """
    Validates the GET query params Pesapal sends to the IPN endpoint.
    Pesapal IPN is a GET request — params are in the query string.
    """
 
    orderTrackingId = serializers.CharField()
    orderMerchantReference = serializers.CharField(required=False, allow_blank=True)
    orderNotificationType = serializers.CharField(required=False, allow_blank=True)
 

# PESAPAL IPN 
class PesapalIPNSerializer(serializers.ModelSerializer):
    """Read-only serializer for listing registered IPN URLs."""
 
    class Meta:
        model = PesapalIPN
        fields = [
            "id",
            "ipn_id",
            "url",
            "notification_type",
            "is_active",
            "environment",
            "registered_at",
            "notes",
        ]
        read_only_fields = fields
 
 
class PesapalOrderStatusSerializer(serializers.Serializer):
    """Response shape for transaction status checks."""
 
    order_tracking_id = serializers.CharField()
    status = serializers.CharField()
    payment_method = serializers.CharField(allow_blank=True)
    amount = serializers.FloatField(allow_null=True)
    currency = serializers.CharField(allow_blank=True)
    confirmation_code = serializers.CharField(allow_blank=True)
    message = serializers.CharField(allow_blank=True)


class FinanceDashboardKpisSerializer(serializers.Serializer):
    total_collected_revenue = serializers.CharField()
    collected_revenue_this_month = serializers.CharField()
    pending_invoices_count = serializers.IntegerField()
    pending_invoices_amount = serializers.CharField()
    active_subscribers = serializers.IntegerField()


class FinanceDashboardRevenueTrendPointSerializer(serializers.Serializer):
    month = serializers.CharField()
    collected_revenue = serializers.CharField()


class FinanceDashboardRecentPaymentEventSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    payment_method = serializers.CharField()
    provider_order_id = serializers.CharField(allow_null=True, allow_blank=True)
    provider_payment_id = serializers.CharField(allow_null=True, allow_blank=True)
    user_email = serializers.EmailField(allow_null=True)
    description = serializers.CharField(allow_blank=True)


class FinanceDashboardOverviewSerializer(serializers.Serializer):
    currency = serializers.CharField()
    kpis = FinanceDashboardKpisSerializer()
    revenue_trend = FinanceDashboardRevenueTrendPointSerializer(many=True)
    recent_payment_events = FinanceDashboardRecentPaymentEventSerializer(many=True)


class FinanceAnalyticsWindowSerializer(serializers.Serializer):
    months = serializers.IntegerField()
    from_month = serializers.CharField()
    to_month = serializers.CharField()


class FinanceAnalyticsPaymentKpisSerializer(serializers.Serializer):
    total_collected_revenue = serializers.CharField()
    collected_revenue_this_month = serializers.CharField()
    payment_completion_rate_pct = serializers.FloatField()
    failed_payments_count = serializers.IntegerField()


class FinanceAnalyticsRevenueTrendPointSerializer(serializers.Serializer):
    month = serializers.CharField()
    collected_revenue = serializers.CharField()
    growth_percent = serializers.FloatField(allow_null=True, required=False)


class FinanceAnalyticsPaymentOutcomesSerializer(serializers.Serializer):
    completed = serializers.IntegerField()
    pending = serializers.IntegerField()
    failed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    refunded = serializers.IntegerField()
    total = serializers.IntegerField()


class FinanceAnalyticsInvoiceInsightsSerializer(serializers.Serializer):
    pending_invoices_count = serializers.IntegerField()
    pending_invoices_amount = serializers.CharField()
    overdue_invoices_count = serializers.IntegerField()


class FinanceAnalyticsSubscriptionInsightsSerializer(serializers.Serializer):
    active = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    expired = serializers.IntegerField()


class FinanceAnalyticsOverviewSerializer(serializers.Serializer):
    as_of = serializers.DateTimeField()
    currency = serializers.CharField()
    window = FinanceAnalyticsWindowSerializer()
    payment_kpis = FinanceAnalyticsPaymentKpisSerializer()
    revenue_trend = FinanceAnalyticsRevenueTrendPointSerializer(many=True)
    payment_outcomes = FinanceAnalyticsPaymentOutcomesSerializer()
    invoice_insights = FinanceAnalyticsInvoiceInsightsSerializer()
    subscription_insights = FinanceAnalyticsSubscriptionInsightsSerializer()


class FinanceAlertActionSerializer(serializers.Serializer):
    label = serializers.CharField()
    route = serializers.CharField()


class FinanceAlertItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    severity = serializers.ChoiceField(choices=['critical', 'warning', 'info', 'success'])
    category = serializers.ChoiceField(choices=['payment', 'invoice', 'subscription'])
    code = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    metric_value = serializers.IntegerField()
    metric_unit = serializers.CharField()
    amount = serializers.CharField(allow_null=True, required=False)
    currency = serializers.CharField(allow_blank=True, required=False)
    action = FinanceAlertActionSerializer(required=False)
    created_at = serializers.DateTimeField()


class FinanceAlertsSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    critical = serializers.IntegerField()
    warning = serializers.IntegerField()
    info = serializers.IntegerField()
    success = serializers.IntegerField()


class FinanceAlertsResponseSerializer(serializers.Serializer):
    as_of = serializers.DateTimeField()
    summary = FinanceAlertsSummarySerializer()
    alerts = FinanceAlertItemSerializer(many=True)