"""
Payment validators for the LMS payment system.
Handles validation of payment data, signatures, and webhook authenticity.
"""
import hmac
import hashlib
import json
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone, re
from ..models import Payment


class PaymentValidator:
    """Validator for payment data and transactions."""
    
    @staticmethod
    def validate_amount(amount, min_amount=0.01, max_amount=None):
        """
        Validate payment amount.
        
        Args:
            amount: Amount to validate
            min_amount: Minimum allowed amount
            max_amount: Maximum allowed amount (optional)
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If amount is invalid
        """
        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid amount format")
        
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero")
        
        if amount < Decimal(str(min_amount)):
            raise ValidationError(f"Amount must be at least {min_amount}")
        
        if max_amount and amount > Decimal(str(max_amount)):
            raise ValidationError(f"Amount cannot exceed {max_amount}")
        
        return True
    
    @staticmethod
    def validate_currency(currency, supported_currencies=None):
        """
        Validate currency code.
        
        Args:
            currency: Currency code to validate
            supported_currencies: List of supported currencies
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If currency is invalid
        """
        if not currency or len(currency) != 3:
            raise ValidationError("Currency must be a 3-letter code")
        
        if not currency.isalpha():
            raise ValidationError("Currency must contain only letters")
        
        if supported_currencies and currency.upper() not in supported_currencies:
            raise ValidationError(f"Currency {currency} is not supported")
        
        return True
    
    @staticmethod
    def validate_email(email):
        """
        Validate email address.
        
        Args:
            email: Email to validate
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If email is invalid
        """
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, str(email)):
            raise ValidationError("Invalid email format")
        return True
    
    @staticmethod
    def validate_phone(phone, country_code=None):
        """
        Validate phone number.
        
        Args:
            phone: Phone number to validate
            country_code: Country code for format validation
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If phone is invalid
        """
        if not phone:
            return True  # Phone is optional
        
        # Remove common separators
        cleaned = re.sub(r'[\s\-\(\)\+]', '', str(phone))
        
        # Basic validation - at least 10 digits
        if not cleaned.isdigit() or len(cleaned) < 10:
            raise ValidationError("Invalid phone number format")
        
        return True
    
    @staticmethod
    def validate_payment_method(method, supported_methods=None):
        """
        Validate payment method.
        
        Args:
            method: Payment method to validate
            supported_methods: List of supported methods
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If method is invalid
        """
        valid_methods = supported_methods or ['flutterwave', 'paypal', 'stripe', 'pesapal']
        
        if method not in valid_methods:
            raise ValidationError(f"Payment method {method} is not supported")
        
        return True
    
    @staticmethod
    def validate_course_access(user, course):
        """
        Validate if user can access/purchase a course.
        
        Args:
            user: User attempting to purchase
            course: Course being purchased
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If user cannot purchase
        """
        from learning.models import Enrollment
        
        # Check if already enrolled
        if Enrollment.objects.filter(user=user, course=course, status='active').exists():
            raise ValidationError("User is already enrolled in this course")
        
        # Check if course is available
        if course.status != 'published':
            raise ValidationError("Course is not available for purchase")
        
        return True


class FlutterwaveValidator:
    """Validator for Flutterwave-specific data."""
    
    @staticmethod
    def verify_webhook_signature(request):
        """
        Verify that webhook request is genuinely from Flutterwave.
        
        Args:
            request: Django request object
        
        Returns:
            bool: True if signature is valid
        """
        signature = request.headers.get('verif-hash')
        expected_hash = settings.FLUTTERWAVE_SECRET_HASH
        
        if not signature or not expected_hash:
            return False
        
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected_hash)
    
    @staticmethod
    def validate_webhook_payload(payload):
        """
        Validate webhook payload structure.
        
        Args:
            payload: Webhook payload dict
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If payload is invalid
        """
        required_fields = ['event', 'data']
        
        for field in required_fields:
            if field not in payload:
                raise ValidationError(f"Missing required field: {field}")
        
        if not isinstance(payload['data'], dict):
            raise ValidationError("Invalid data format")
        
        return True
    
    @staticmethod
    def validate_transaction_status(status):
        """
        Validate transaction status.
        
        Args:
            status: Transaction status string
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If status is invalid
        """
        valid_statuses = ['successful', 'failed', 'pending', 'cancelled']
        
        if status not in valid_statuses:
            raise ValidationError(f"Invalid transaction status: {status}")
        
        return True
    
    @staticmethod
    def validate_amount_match(expected, received, tolerance=0.01):
        """
        Validate that amounts match within tolerance.
        
        Args:
            expected: Expected amount
            received: Received amount from webhook
            tolerance: Allowed difference (default 0.01)
        
        Returns:
            bool: True if amounts match
        
        Raises:
            ValidationError: If amounts don't match
        """
        expected_dec = Decimal(str(expected))
        received_dec = Decimal(str(received))
        
        difference = abs(expected_dec - received_dec)
        
        if difference > Decimal(str(tolerance)):
            raise ValidationError(
                f"Amount mismatch: expected {expected}, received {received}"
            )
        
        return True
    
    @staticmethod
    def validate_currency_match(expected, received):
        """
        Validate that currencies match.
        
        Args:
            expected: Expected currency
            received: Received currency from webhook
        
        Returns:
            bool: True if currencies match
        
        Raises:
            ValidationError: If currencies don't match
        """
        if expected.upper() != received.upper():
            raise ValidationError(
                f"Currency mismatch: expected {expected}, received {received}"
            )
        
        return True
    
    @staticmethod
    def extract_customer_data(data):
        """
        Extract and validate customer data from webhook payload.
        
        Args:
            data: Webhook data dict
        
        Returns:
            dict: Validated customer data
        
        Raises:
            ValidationError: If customer data is invalid
        """
        customer = data.get('customer', {})
        
        if not customer:
            return {}
        
        validated = {}
        
        # Email is required
        if 'email' in customer:
            PaymentValidator.validate_email(customer['email'])
            validated['email'] = customer['email']
        
        # Optional fields
        if 'name' in customer:
            validated['name'] = str(customer['name'])[:255]
        
        if 'phone' in customer:
            try:
                PaymentValidator.validate_phone(customer['phone'])
                validated['phone'] = str(customer['phone'])
            except ValidationError:
                # Don't fail on invalid phone, just skip it
                pass
        
        return validated


class WebhookValidator:
    """Generic webhook validator for all payment providers."""
    
    @staticmethod
    def verify_ip_address(request, allowed_ips=None):
        """
        Verify that request comes from allowed IP addresses.
        
        Args:
            request: Django request object
            allowed_ips: List of allowed IP addresses
        
        Returns:
            bool: True if IP is allowed
        """
        if not allowed_ips:
            return True  # Skip if no IP restrictions
        
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        return ip in allowed_ips
    
    @staticmethod
    def verify_timestamp(timestamp, max_age_seconds=300):
        """
        Verify that webhook timestamp is not too old (prevents replay attacks).
        
        Args:
            timestamp: Timestamp from webhook
            max_age_seconds: Maximum allowed age in seconds
        
        Returns:
            bool: True if timestamp is recent
        """
        try:
            # Parse timestamp (adjust format based on provider)
            webhook_time = timezone.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if timezone.is_naive(webhook_time):
                webhook_time = timezone.make_aware(webhook_time)
            
            age = (timezone.now() - webhook_time).total_seconds()
            return age <= max_age_seconds
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def verify_event_type(event_type, allowed_events):
        """
        Verify that event type is expected/allowed.
        
        Args:
            event_type: Event type from webhook
            allowed_events: List of allowed event types
        
        Returns:
            bool: True if event is allowed
        
        Raises:
            ValidationError: If event is not allowed
        """
        if event_type not in allowed_events:
            raise ValidationError(f"Unexpected event type: {event_type}")
        
        return True