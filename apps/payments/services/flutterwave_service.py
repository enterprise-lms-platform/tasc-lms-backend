import requests
import json
import hmac
import hashlib
from django.conf import settings
from django.utils import timezone
from ..models import Payment

class FlutterwaveService:
    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        self.encryption_key = settings.FLUTTERWAVE_ENCRYPTION_KEY
        self.base_url = settings.FLUTTERWAVE_BASE_URL or 'https://api.flutterwave.com/v3'
        self.secret_hash = settings.FLUTTERWAVE_SECRET_HASH
        
    def _get_headers(self):
        """Get headers for Flutterwave API requests"""
        return {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
    
    def initialize_payment(self, payment, redirect_url=None):
        """
        Initialize a payment with Flutterwave
        
        Args:
            payment: Payment model instance
            redirect_url: URL to redirect after payment
        
        Returns:
            dict: Payment initialization response
        """
        try:
            # Set redirect URL
            if not redirect_url:
                redirect_url = f"{settings.FRONTEND_URL}/payment/callback"
            
            # Prepare payment data
            payment_data = {
                "tx_ref": str(payment.id),
                "amount": str(payment.amount),
                "currency": payment.currency,
                "redirect_url": redirect_url,
                "payment_options": "card,account,ussd,mpesa,barter",  # Available options
                "meta": {
                    "payment_id": str(payment.id),
                    "user_id": str(payment.user.id),
                    "user_email": payment.user.email,
                    "course_id": str(payment.course.id) if payment.course else None,
                    "course_title": payment.course.title if payment.course else None
                },
                "customer": {
                    "email": payment.user.email,
                    "name": f"{payment.user.first_name} {payment.user.last_name}".strip() or payment.user.email,
                    "phonenumber": getattr(payment.user, 'phone', ''),
                },
                "customizations": {
                    "title": settings.SITE_NAME or "LMS Payment",
                    "description": payment.description or f"Payment for {payment.course.title if payment.course else 'Course'}",
                    "logo": settings.LOGO_URL if hasattr(settings, 'LOGO_URL') else None,
                }
            }
            
            # Make API request
            response = requests.post(
                f"{self.base_url}/payments",
                headers=self._get_headers(),
                json=payment_data
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('status') == 'success':
                # Update payment with Flutterwave reference
                payment.provider_payment_id = result['data']['id']
                payment.metadata['flutterwave_response'] = result['data']
                payment.save()
                
                return {
                    'success': True,
                    'payment_link': result['data']['link'],
                    'transaction_id': result['data']['id'],
                    'reference': result['data']['tx_ref'],
                    'data': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Payment initialization failed'),
                    'data': result
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to connect to Flutterwave'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'An unexpected error occurred'
            }
    
    def verify_payment(self, transaction_id):
        """
        Verify a payment with Flutterwave
        
        Args:
            transaction_id: Flutterwave transaction ID
        
        Returns:
            dict: Verification result
        """
        try:
            response = requests.get(
                f"{self.base_url}/transactions/{transaction_id}/verify",
                headers=self._get_headers()
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('status') == 'success':
                data = result['data']
                
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': data['amount'],
                    'currency': data['currency'],
                    'reference': data['tx_ref'],
                    'payment_id': data['id'],
                    'customer': data.get('customer', {}),
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Verification failed'),
                    'data': result
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to verify payment with Flutterwave'
            }
    
    def handle_webhook(self, request):
        """
        Handle Flutterwave webhook
        
        Args:
            request: Django request object
        
        Returns:
            dict: Webhook processing result
        """
        # Verify webhook signature
        signature = request.headers.get('verif-hash')
        
        if not signature or signature != self.secret_hash:
            return {
                'success': False,
                'message': 'Invalid webhook signature'
            }
        
        # Get webhook data
        webhook_data = json.loads(request.body)
        event_type = webhook_data.get('event')
        event_data = webhook_data.get('data', {})
        
        # Store webhook for debugging
        from ..models import PaymentWebhook
        webhook = PaymentWebhook.objects.create(
            provider='flutterwave',
            event_type=event_type,
            event_id=event_data.get('id', ''),
            payload=webhook_data,
            processed=False
        )
        
        # Process based on event type
        if event_type == 'charge.completed':
            return self._process_successful_payment(event_data, webhook)
        elif event_type == 'charge.failed':
            return self._process_failed_payment(event_data, webhook)
        elif event_type == 'charge.refunded':
            return self._process_refund(event_data, webhook)
        
        # Mark webhook as processed
        webhook.processed = True
        webhook.processed_at = timezone.now()
        webhook.save()
        
        return {
            'success': True,
            'message': f'Webhook received: {event_type}'
        }
    
    def _process_successful_payment(self, event_data, webhook):
        """Process successful payment from webhook"""
        try:
            # Find payment by transaction reference
            tx_ref = event_data.get('tx_ref')
            payment = Payment.objects.get(id=tx_ref)
            
            # Verify amount matches
            if float(payment.amount) != float(event_data.get('amount', 0)):
                webhook.notes = "Amount mismatch"
                webhook.save()
                return {
                    'success': False,
                    'message': 'Amount mismatch'
                }
            
            # Mark payment as completed
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.webhook_received = True
            payment.metadata['flutterwave_webhook'] = event_data
            payment.save()
            
            # Create transaction record
            from ..models import Transaction
            Transaction.objects.create(
                user=payment.user,
                course=payment.course,
                amount=payment.amount,
                currency=payment.currency,
                status='completed',
                payment_method='flutterwave',
                payment_provider='flutterwave',
                gateway_transaction_id=event_data.get('id'),
                gateway_response=event_data,
                completed_at=timezone.now()
            )
            
            # Create invoice
            from ..models import Invoice, InvoiceItem
            invoice = Invoice.objects.create(
                user=payment.user,
                course=payment.course,
                payment=payment,
                invoice_type='course',
                customer_name=payment.user.get_full_name() or payment.user.email,
                customer_email=payment.user.email,
                subtotal=payment.amount,
                total_amount=payment.amount,
                status='paid',
                paid_at=timezone.now()
            )
            
            InvoiceItem.objects.create(
                invoice=invoice,
                item_type='course',
                course=payment.course,
                description=f"Course: {payment.course.title}",
                quantity=1,
                unit_price=payment.amount,
                enrollment=payment.course.enrollments.filter(user=payment.user).first()
            )
            
            # Mark webhook as processed
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
            
            return {
                'success': True,
                'message': 'Payment processed successfully',
                'payment_id': str(payment.id)
            }
            
        except Payment.DoesNotExist:
            webhook.notes = f"Payment not found: {tx_ref}"
            webhook.save()
            return {
                'success': False,
                'message': f'Payment not found: {tx_ref}'
            }
        except Exception as e:
            webhook.notes = f"Error: {str(e)}"
            webhook.save()
            return {
                'success': False,
                'message': f'Error processing payment: {str(e)}'
            }
    
    def _process_failed_payment(self, event_data, webhook):
        """Process failed payment from webhook"""
        try:
            tx_ref = event_data.get('tx_ref')
            payment = Payment.objects.get(id=tx_ref)
            
            payment.status = 'failed'
            payment.metadata['flutterwave_failure'] = event_data
            payment.save()
            
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
            
            return {
                'success': True,
                'message': 'Failed payment recorded'
            }
            
        except Payment.DoesNotExist:
            return {
                'success': False,
                'message': f'Payment not found: {tx_ref}'
            }
    
    def _process_refund(self, event_data, webhook):
        """Process refund from webhook"""
        try:
            tx_ref = event_data.get('tx_ref')
            payment = Payment.objects.get(id=tx_ref)
            
            payment.status = 'refunded'
            payment.metadata['flutterwave_refund'] = event_data
            payment.save()
            
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
            
            return {
                'success': True,
                'message': 'Refund recorded'
            }
            
        except Payment.DoesNotExist:
            return {
                'success': False,
                'message': f'Payment not found: {tx_ref}'
            }
    
    def create_refund(self, payment, amount=None):
        """
        Create a refund in Flutterwave
        
        Args:
            payment: Payment model instance
            amount: Amount to refund (None for full refund)
        
        Returns:
            dict: Refund result
        """
        try:
            refund_data = {
                "transaction_id": payment.provider_payment_id,
                "amount": amount if amount else None  # None means full refund
            }
            
            response = requests.post(
                f"{self.base_url}/transactions/{payment.provider_payment_id}/refund",
                headers=self._get_headers(),
                json=refund_data
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'refund_id': result['data']['id'],
                    'amount': result['data']['amount'],
                    'status': result['data']['status'],
                    'data': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Refund failed'),
                    'data': result
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to process refund with Flutterwave'
            }
    
    def get_banks(self, country='UG'):
        """
        Get list of banks for a country
        
        Args:
            country: Country code (NG, GH, KE, etc.)
        
        Returns:
            dict: List of banks
        """
        try:
            response = requests.get(
                f"{self.base_url}/banks/{country}",
                headers=self._get_headers()
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'banks': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Failed to fetch banks'),
                    'data': result
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to fetch banks from Flutterwave'
            }
    
    def get_exchange_rates(self, from_currency='USD', to_currency='UGX', amount=1):
        """
        Get exchange rates
        
        Args:
            from_currency: Source currency
            to_currency: Target currency
            amount: Amount to convert
        
        Returns:
            dict: Exchange rate information
        """
        try:
            response = requests.get(
                f"{self.base_url}/transfers/rates",
                headers=self._get_headers(),
                params={
                    'amount': amount,
                    'source_currency': from_currency,
                    'destination_currency': to_currency
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'rate': result['data']['rate'],
                    'source_amount': result['data']['source']['amount'],
                    'destination_amount': result['data']['destination']['amount'],
                    'data': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Failed to fetch rates'),
                    'data': result
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to fetch exchange rates'
            }