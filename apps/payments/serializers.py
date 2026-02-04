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
