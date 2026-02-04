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

class RefundSerializer(serializers.ModelSerializer):
    payment_details = PaymentSerializer(source='payment', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'payment_details', 'amount', 'currency',
            'status', 'created_at', 'processed_at',
        ]
        read_only_fields = ['id', 'status', 'created_at', 'processed_at']

class CreateRefundSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=500)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, 
        required=False, allow_null=True
    )
    
    def validate(self, data):
        try:
            payment = Payment.objects.get(id=data['payment_id'])
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Payment not found")
        
        if not payment.is_refundable():
            raise serializers.ValidationError("Payment is not refundable")
        
        # If amount not specified, refund full amount
        if 'amount' not in data or data['amount'] is None:
            data['amount'] = payment.amount
        elif data['amount'] > payment.amount:
            raise serializers.ValidationError("Refund amount exceeds payment amount")
        
        data['payment'] = payment
        return data