import paypalrestsdk
import requests
from django.conf import settings
from django.utils import timezone
from ..models import Payment

class PayPalService:
    def __init__(self):
        paypalrestsdk.configure({
            "mode": settings.PAYPAL_MODE,  # "sandbox" or "live"
            "client_id": settings.PAYPAL_CLIENT_ID,
            "client_secret": settings.PAYPAL_CLIENT_SECRET,
        })
        self.api = paypalrestsdk
    
    def create_order(self, payment):
        """Create a PayPal order"""
        try:
            order = self.api.Order({
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": payment.currency,
                        "value": str(payment.amount)
                    },
                    "description": f"Payment for {payment.course.title}",
                    "custom_id": str(payment.id),
                }],
                "application_context": {
                    "return_url": f"{settings.FRONTEND_URL}/payment/success",
                    "cancel_url": f"{settings.FRONTEND_URL}/payment/cancel",
                    "brand_name": settings.SITE_NAME,
                    "user_action": "PAY_NOW",
                }
            })
            
            if order.create():
                payment.provider_order_id = order.id
                payment.save()
                
                # Find approval link
                approve_link = next(
                    link for link in order.links if link.rel == "approve"
                )
                
                return {
                    'order_id': order.id,
                    'approval_url': approve_link.href,
                    'status': order.status,
                }
            else:
                raise Exception(order.error)
                
        except Exception as e:
            raise Exception(f"PayPal error: {str(e)}")
    
    def capture_order(self, order_id):
        """Capture a PayPal order"""
        try:
            order = self.api.Order.find(order_id)
            
            if order.capture():
                # Get capture details
                capture = order.purchase_units[0].payments.captures[0]
                
                return {
                    'success': True,
                    'order_id': order.id,
                    'capture_id': capture.id,
                    'status': capture.status,
                }
            else:
                raise Exception(order.error)
                
        except Exception as e:
            raise Exception(f"PayPal error: {str(e)}")
    
    def handle_webhook(self, request):
        """Handle PayPal webhook events"""
        transmission_id = request.META.get('HTTP_PAYPAL_TRANSMISSION_ID')
        timestamp = request.META.get('HTTP_PAYPAL_TRANSMISSION_TIME')
        webhook_id = settings.PAYPAL_WEBHOOK_ID
        event_body = request.body.decode('utf-8')
        cert_url = request.META.get('HTTP_PAYPAL_CERT_URL')
        actual_sig = request.META.get('HTTP_PAYPAL_TRANSMISSION_SIG')
        
        try:
            is_valid = self.api.WebhookEvent.verify(
                transmission_id,
                timestamp,
                webhook_id,
                event_body,
                cert_url,
                actual_sig
            )
            
            if not is_valid:
                raise Exception("Invalid PayPal webhook signature")
            
            event = self.api.WebhookEvent.construct_from(
                request.data, self.api.api
            )
            
            return event
            
        except Exception as e:
            raise Exception(f"PayPal webhook error: {str(e)}")