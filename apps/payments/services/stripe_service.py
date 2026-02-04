import stripe
from django.conf import settings
from django.utils import timezone
from ..models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeService:
    def __init__(self):
        self.client = stripe
    
    def create_payment_intent(self, payment):
        """Create a Stripe PaymentIntent"""
        try:
            intent = self.client.PaymentIntent.create(
                amount=int(payment.amount * 100),  # Convert to cents
                currency=payment.currency.lower(),
                metadata={
                    'payment_id': str(payment.id),
                    'user_id': str(payment.user.id),
                    'course_id': str(payment.course.id),
                },
                description=f"Payment for {payment.course.title}",
                automatic_payment_methods={
                    'enabled': True,
                    'allow_redirects': 'never'
                },
            )
            
            payment.provider_payment_id = intent.id
            payment.metadata['client_secret'] = intent.client_secret
            payment.save()
            
            return {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id,
                'status': intent.status,
            }
            
        except stripe.error.StripeError as e:
            raise Exception(f"Stripe error: {str(e)}")
    
    def confirm_payment(self, payment_intent_id):
        """Confirm a Stripe payment"""
        try:
            intent = self.client.PaymentIntent.retrieve(payment_intent_id)
            
            if intent.status == 'succeeded':
                return {
                    'success': True,
                    'payment_intent': intent,
                    'charge_id': intent.charges.data[0].id if intent.charges.data else None,
                }
            return {'success': False, 'status': intent.status}
            
        except stripe.error.StripeError as e:
            raise Exception(f"Stripe error: {str(e)}")
    
    
    def handle_webhook(self, payload, sig_header):
        """Handle Stripe webhook events"""
        try:
            event = self.client.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            
            # Handle different event types
            if event['type'] == 'payment_intent.succeeded':
                payment_intent = event['data']['object']
                self._handle_successful_payment(payment_intent)
                
            elif event['type'] == 'payment_intent.payment_failed':
                payment_intent = event['data']['object']
                self._handle_failed_payment(payment_intent)
            
            return {'success': True, 'event': event['type']}
            
        except Exception as e:
            raise Exception(f"Webhook error: {str(e)}")
    
    def _handle_successful_payment(self, payment_intent):
        """Handle successful payment from webhook"""
        try:
            payment_id = payment_intent['metadata'].get('payment_id')
            payment = Payment.objects.get(id=payment_id)
            
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.webhook_received = True
            payment.save()
            
            # Enroll user in course
            payment.course.enrolled_users.add(payment.user)
            
        except Payment.DoesNotExist:
            pass