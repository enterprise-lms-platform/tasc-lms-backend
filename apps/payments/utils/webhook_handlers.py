"""
Webhook handlers for processing payment notifications from various providers.
Handles successful payments, failures, refunds, and other events.
"""
import json
import logging
from decimal import Decimal
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction

from ..models import (
    Payment, Transaction, Invoice, InvoiceItem, 
    PaymentWebhook, UserSubscription
)
from .payment_validators import FlutterwaveValidator, PaymentValidator

logger = logging.getLogger(__name__)


class BaseWebhookHandler:
    """Base class for all webhook handlers."""
    
    def __init__(self):
        self.validator = None
    
    def log_webhook(self, provider, event_type, event_id, payload, processed=False):
        """Store webhook in database for debugging."""
        webhook = PaymentWebhook.objects.create(
            provider=provider,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            processed=processed
        )
        return webhook
    
    def send_payment_confirmation(self, payment):
        """Send payment confirmation email to user."""
        try:
            subject = f"Payment Confirmed: {payment.description}"
            message = f"""
            Dear {payment.user.get_full_name() or payment.user.email},
            
            Your payment of {payment.currency} {payment.amount} has been confirmed.
            
            Transaction ID: {payment.transaction_id if hasattr(payment, 'transaction_id') else 'N/A'}
            Date: {payment.completed_at or timezone.now()}
            
            Thank you for your purchase!
            
            Best regards,
            {settings.SITE_NAME or 'LMS Team'}
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [payment.user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send payment confirmation email: {e}")
    
    def handle_error(self, error, webhook=None):
        """Handle and log webhook processing errors."""
        logger.error(f"Webhook processing error: {error}")
        if webhook:
            webhook.processed = False
            webhook.save()


class FlutterwaveWebhookHandler(BaseWebhookHandler):
    """Handler for Flutterwave webhook events."""
    
    def __init__(self):
        super().__init__()
        self.validator = FlutterwaveValidator()
        self.provider = 'flutterwave'
    
    @transaction.atomic
    def handle_webhook(self, request):
        """
        Main entry point for Flutterwave webhooks.
        
        Args:
            request: Django request object
        
        Returns:
            dict: Processing result
        """
        # 1. Verify signature
        if not self.validator.verify_webhook_signature(request):
            logger.warning("Invalid webhook signature")
            return {
                'success': False,
                'message': 'Invalid signature'
            }
        
        try:
            # 2. Parse payload
            payload = json.loads(request.body)
            
            # 3. Validate payload structure
            self.validator.validate_webhook_payload(payload)
            
            event_type = payload.get('event')
            event_data = payload.get('data', {})
            event_id = event_data.get('id', 'unknown')
            
            # 4. Log webhook
            webhook = self.log_webhook(
                provider=self.provider,
                event_type=event_type,
                event_id=event_id,
                payload=payload
            )
            
            # 5. Route to appropriate handler
            if event_type == 'charge.completed':
                result = self._handle_successful_payment(event_data, webhook)
            elif event_type == 'charge.failed':
                result = self._handle_failed_payment(event_data, webhook)
            elif event_type == 'charge.refunded':
                result = self._handle_refund(event_data, webhook)
            elif event_type == 'transfer.success':
                result = self._handle_transfer_success(event_data, webhook)
            else:
                # Unknown event type - just acknowledge
                webhook.processed = True
                webhook.processed_at = timezone.now()
                webhook.save()
                result = {
                    'success': True,
                    'message': f'Unhandled event type: {event_type}'
                }
            
            return result
            
        except Exception as e:
            logger.exception("Error processing Flutterwave webhook")
            return {
                'success': False,
                'message': str(e)
            }
    
    def _handle_successful_payment(self, data, webhook):
        """
        Handle successful payment webhook.
        
        Args:
            data: Webhook data
            webhook: PaymentWebhook instance
        
        Returns:
            dict: Processing result
        """
        try:
            # Extract payment reference
            tx_ref = data.get('tx_ref')
            if not tx_ref:
                raise ValueError("Missing transaction reference")
            
            # Find payment
            try:
                payment = Payment.objects.get(id=tx_ref)
            except Payment.DoesNotExist:
                webhook.notes = f"Payment not found: {tx_ref}"
                webhook.save()
                return {
                    'success': False,
                    'message': f'Payment not found: {tx_ref}'
                }
            
            # Validate amounts match
            received_amount = Decimal(str(data.get('amount', 0)))
            self.validator.validate_amount_match(payment.amount, received_amount)
            
            # Validate currency matches
            received_currency = data.get('currency', '')
            self.validator.validate_currency_match(payment.currency, received_currency)
            
            # Extract customer data
            customer_data = self.validator.extract_customer_data(data)
            
            # Update payment
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.webhook_received = True
            payment.metadata['flutterwave_webhook'] = data
            payment.save()
            
            # Create transaction
            transaction = Transaction.objects.create(
                user=payment.user,
                course=payment.course,
                amount=payment.amount,
                currency=payment.currency,
                status='completed',
                payment_method='flutterwave',
                payment_provider='flutterwave',
                gateway_transaction_id=data.get('id'),
                gateway_response=data,
                completed_at=timezone.now(),
                card_last4=customer_data.get('card_last4', ''),
                card_brand=customer_data.get('card_brand', '')
            )
            
            # Create invoice
            invoice = self._create_invoice(payment, transaction, customer_data)
            
            # Enroll user in course (if applicable)
            if payment.course:
                self._enroll_user(payment)
            
            # Send confirmation email
            self.send_payment_confirmation(payment)
            
            # Update webhook
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
            
            return {
                'success': True,
                'message': 'Payment processed successfully',
                'payment_id': str(payment.id),
                'transaction_id': transaction.transaction_id,
                'invoice_number': invoice.invoice_number if invoice else None
            }
            
        except Exception as e:
            self.handle_error(e, webhook)
            raise
    
    def _handle_failed_payment(self, data, webhook):
        """
        Handle failed payment webhook.
        
        Args:
            data: Webhook data
            webhook: PaymentWebhook instance
        
        Returns:
            dict: Processing result
        """
        try:
            tx_ref = data.get('tx_ref')
            if tx_ref:
                try:
                    payment = Payment.objects.get(id=tx_ref)
                    payment.status = 'failed'
                    payment.metadata['flutterwave_failure'] = data
                    payment.save()
                    
                    # Create failed transaction
                    Transaction.objects.create(
                        user=payment.user,
                        course=payment.course,
                        amount=payment.amount,
                        currency=payment.currency,
                        status='failed',
                        payment_method='flutterwave',
                        payment_provider='flutterwave',
                        gateway_transaction_id=data.get('id'),
                        gateway_response=data
                    )
                except Payment.DoesNotExist:
                    pass
            
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
            
            return {
                'success': True,
                'message': 'Failed payment recorded'
            }
            
        except Exception as e:
            self.handle_error(e, webhook)
            raise
    
    def _handle_refund(self, data, webhook):
        """
        Handle refund webhook.
        
        Args:
            data: Webhook data
            webhook: PaymentWebhook instance
        
        Returns:
            dict: Processing result
        """
        try:
            original_tx_id = data.get('transaction_id')
            
            # Find original payment
            try:
                payment = Payment.objects.get(provider_payment_id=original_tx_id)
                payment.status = 'refunded'
                payment.metadata['flutterwave_refund'] = data
                payment.save()
                
                # Remove course access if needed
                if payment.course:
                    from learning.models import Enrollment
                    Enrollment.objects.filter(
                        user=payment.user,
                        course=payment.course,
                        status='active'
                    ).update(status='dropped')
                
            except Payment.DoesNotExist:
                pass
            
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
            
            return {
                'success': True,
                'message': 'Refund recorded'
            }
            
        except Exception as e:
            self.handle_error(e, webhook)
            raise
    
    def _handle_transfer_success(self, data, webhook):
        """
        Handle successful transfer webhook (for payouts).
        
        Args:
            data: Webhook data
            webhook: PaymentWebhook instance
        
        Returns:
            dict: Processing result
        """
        webhook.processed = True
        webhook.processed_at = timezone.now()
        webhook.save()
        
        return {
            'success': True,
            'message': 'Transfer successful'
        }
    
    def _create_invoice(self, payment, transaction, customer_data):
        """
        Create invoice for successful payment.
        
        Args:
            payment: Payment instance
            transaction: Transaction instance
            customer_data: Customer data from webhook
        
        Returns:
            Invoice: Created invoice
        """
        customer_name = customer_data.get('name', payment.user.get_full_name() or payment.user.email)
        customer_email = customer_data.get('email', payment.user.email)
        
        invoice = Invoice.objects.create(
            user=payment.user,
            course=payment.course,
            payment=payment,
            invoice_type='course' if payment.course else 'other',
            customer_name=customer_name,
            customer_email=customer_email,
            subtotal=payment.amount,
            total_amount=payment.amount,
            currency=payment.currency,
            status='paid',
            paid_at=payment.completed_at
        )
        
        # Add invoice item
        description = payment.description or f"Payment for {payment.course.title if payment.course else 'Course'}"
        InvoiceItem.objects.create(
            invoice=invoice,
            item_type='course' if payment.course else 'other',
            course=payment.course,
            description=description,
            quantity=1,
            unit_price=payment.amount
        )
        
        return invoice
    
    def _enroll_user(self, payment):
        """
        Enroll user in course after successful payment.
        
        Args:
            payment: Payment instance
        """
        try:
            from learning.models import Enrollment
            
            enrollment, created = Enrollment.objects.get_or_create(
                user=payment.user,
                course=payment.course,
                defaults={
                    'status': 'active',
                    'organization': payment.user.organization if hasattr(payment.user, 'organization') else None
                }
            )
            
            if not created and enrollment.status != 'active':
                enrollment.status = 'active'
                enrollment.save()
                
            logger.info(f"User {payment.user.id} enrolled in course {payment.course.id}")
            
        except ImportError:
            logger.warning("CourseEnrollment model not found - skipping enrollment")
        except Exception as e:
            logger.error(f"Failed to enroll user: {e}")


class WebhookHandlerFactory:
    """Factory to create appropriate webhook handler."""
    
    @staticmethod
    def get_handler(provider):
        """
        Get webhook handler for provider.
        
        Args:
            provider: Payment provider name
        
        Returns:
            BaseWebhookHandler: Handler instance
        
        Raises:
            ValueError: If provider is not supported
        """
        handlers = {
            'flutterwave': FlutterwaveWebhookHandler,
            # Add other providers here if needed
        }
        
        handler_class = handlers.get(provider.lower())
        if not handler_class:
            raise ValueError(f"Unsupported webhook provider: {provider}")
        
        return handler_class()