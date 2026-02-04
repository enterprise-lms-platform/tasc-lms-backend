import requests
import json
from django.conf import settings
from django.utils import timezone
from ..models import Payment

class PesaPalService:
    def __init__(self):
        self.base_url = settings.PESAPAL_BASE_URL
        self.consumer_key = settings.PESAPAL_CONSUMER_KEY
        self.consumer_secret = settings.PESAPAL_CONSUMER_SECRET
        self.token = None
    
    def _authenticate(self):
        """Get authentication token"""
        try:
            auth_url = f"{self.base_url}/api/Auth/RequestToken"
            
            data = {
                "consumer_key": self.consumer_key,
                "consumer_secret": self.consumer_secret
            }
            
            response = requests.post(auth_url, json=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.token = token_data['token']
            
        except Exception as e:
            raise Exception(f"PesaPal authentication error: {str(e)}")
    
    def submit_order(self, payment):
        """Submit order to PesaPal"""
        try:
            if not self.token:
                self._authenticate()
            
            order_url = f"{self.base_url}/api/Transactions/SubmitOrderRequest"
            
            order_data = {
                "id": str(payment.id),
                "currency": payment.currency,
                "amount": float(payment.amount),
                "description": f"Payment for {payment.course.title}",
                "callback_url": f"{settings.BACKEND_URL}/api/payments/pesapal/callback/",
                "notification_id": settings.PESAPAL_NOTIFICATION_ID,
                "billing_address": {
                    "email_address": payment.user.email,
                    "phone_number": payment.user.phone or "",
                    "first_name": payment.user.first_name,
                    "last_name": payment.user.last_name,
                }
            }
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(order_url, json=order_data, headers=headers)
            response.raise_for_status()
            
            order_response = response.json()
            
            payment.provider_order_id = order_response['order_tracking_id']
            payment.save()
            
            return {
                'order_tracking_id': order_response['order_tracking_id'],
                'redirect_url': order_response['redirect_url'],
                'status': 'pending',
            }
            
        except Exception as e:
            raise Exception(f"PesaPal error: {str(e)}")
    
    def check_transaction_status(self, order_tracking_id):
        """Check transaction status"""
        try:
            if not self.token:
                self._authenticate()
            
            status_url = f"{self.base_url}/api/Transactions/GetTransactionStatus"
            
            params = {
                "orderTrackingId": order_tracking_id
            }
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(status_url, params=params, headers=headers)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            raise Exception(f"PesaPal error: {str(e)}")