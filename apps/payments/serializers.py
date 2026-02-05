from rest_framework import serializers
from .models import Payment

class PaymentSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'user_email', 'course', 'course_title',
            'amount', 'currency', 'payment_method', 'status',
            'created_at', 'completed_at', 'metadata',
        ]
        read_only_fields = ['id', 'created_at', 'completed_at', 'metadata', 'user']

class CreatePaymentSerializer(serializers.Serializer):
    course_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHODS)
    currency = serializers.ChoiceField(
        choices=Payment.CURRENCIES, 
        default='USD',
        required=False
    )
    
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, 
        min_value=0.01,
        required=False
    )
    def validate(self, data):
        # Additional validation can be added here
        return data

class PaymentConfirmationSerializer(serializers.Serializer):
    payment_intent_id = serializers.CharField(required=False)
    order_id = serializers.CharField(required=False)
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHODS)

class PaymentWebhookSerializer(serializers.Serializer):
    provider = serializers.CharField()
    event_type = serializers.CharField()
    event_id = serializers.CharField()
    payload = serializers.JSONField()
    signature = serializers.CharField(required=False)

class PaymentStatusSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    details = serializers.JSONField(required=False) 
from django.utils import timezone
from .models import (
    Invoice, InvoiceItem, Transaction, PaymentMethod,
    Subscription, UserSubscription
)


class InvoiceItemSerializer(serializers.ModelSerializer):
    """Serializer for InvoiceItem model."""
    
    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'invoice', 'item_type', 'item_id',
            'description', 'quantity',
            'unit_price', 'tax_rate',
            'subtotal', 'tax_amount', 'total',
            'enrollment'
        ]
        read_only_fields = ['id', 'subtotal', 'tax_amount', 'total']


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model."""
    items = InvoiceItemSerializer(many=True, read_only=True)
    user_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    remaining_amount = serializers.ReadOnlyField()
    is_paid = serializers.ReadOnlyField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    invoice_type_display = serializers.CharField(source='get_invoice_type_display', read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'invoice_type', 'invoice_type_display',
            'user', 'user_name', 'organization', 'organization_name',
            'customer_name', 'customer_email', 'customer_address',
            'customer_city', 'customer_country',
            'issue_date', 'due_date', 'status', 'status_display',
            'subtotal', 'tax_amount', 'total_amount', 'paid_amount',
            'remaining_amount', 'is_paid',
            'currency', 'notes', 'internal_notes', 'invoice_pdf_url',
            'created_at', 'updated_at', 'paid_at', 'items'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at', 'paid_at']
    
    def get_user_name(self, obj):
        return obj.customer_name
    
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None


class InvoiceCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating invoices."""
    items = InvoiceItemSerializer(many=True)
    
    class Meta:
        model = Invoice
        fields = [
            'user', 'organization', 'invoice_type',
            'customer_name', 'customer_email', 'customer_address',
            'customer_city', 'customer_country',
            'issue_date', 'due_date',
            'subtotal', 'tax_amount', 'total_amount',
            'currency', 'notes', 'internal_notes', 'items'
        ]
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        invoice = Invoice.objects.create(**validated_data)
        
        # Create invoice items
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        
        return invoice


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model."""
    user_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'invoice', 'invoice_number',
            'user', 'user_name', 'organization', 'organization_name',
            'transaction_id', 'amount', 'currency',
            'status', 'status_display',
            'payment_method', 'payment_method_display', 'payment_provider',
            'gateway_transaction_id', 'gateway_response',
            'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = ['id', 'transaction_id', 'created_at', 'updated_at', 'completed_at']
    
    def get_user_name(self, obj):
        return obj.user.email if obj.user else obj.organization.name if obj.organization else None
    
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    def get_invoice_number(self, obj):
        return obj.invoice.invoice_number if obj.invoice else None


class TransactionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating transactions."""
    
    class Meta:
        model = Transaction
        fields = [
            'invoice', 'user', 'organization', 'amount', 'currency',
            'payment_method', 'payment_provider',
            'gateway_transaction_id', 'gateway_response'
        ]


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for PaymentMethod model."""
    user_email = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'user', 'user_email', 'organization', 'organization_name',
            'method_type', 'is_default', 'is_active',
            'display_name', 'is_expired',
            'card_last_four', 'card_brand', 'card_expiry_month', 'card_expiry_year',
            'paypal_email', 'bank_name', 'bank_account_last_four',
            'payment_provider',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_email(self, obj):
        return obj.user.email if obj.user else None
    
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    def get_display_name(self, obj):
        return str(obj)


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
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    billing_cycle_display = serializers.CharField(source='get_billing_cycle_display', read_only=True)
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'name', 'description',
            'price', 'currency', 'billing_cycle', 'billing_cycle_display',
            'features', 'max_courses', 'max_users', 'trial_days',
            'status', 'status_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SubscriptionCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating subscriptions."""
    
    class Meta:
        model = Subscription
        fields = [
            'name', 'description',
            'price', 'currency', 'billing_cycle',
            'features', 'max_courses', 'max_users', 'trial_days',
            'status'
        ]


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for UserSubscription model."""
    user_email = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    subscription_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_trial = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    
    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'user_email', 'organization', 'organization_name',
            'subscription', 'subscription_name',
            'status', 'status_display',
            'start_date', 'end_date', 'trial_end_date',
            'auto_renew', 'cancelled_at',
            'price', 'currency',
            'is_trial', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_email(self, obj):
        return obj.user.email if obj.user else None
    
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    def get_subscription_name(self, obj):
        return obj.subscription.name


class UserSubscriptionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating user subscriptions."""
    
    class Meta:
        model = UserSubscription
        fields = [
            'organization', 'subscription',
            'end_date', 'trial_end_date', 'auto_renew'
        ]
