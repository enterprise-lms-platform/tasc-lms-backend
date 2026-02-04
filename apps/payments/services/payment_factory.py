from django.conf import settings
from .stripe_service import StripeService
from .paypal_service import PayPalService
from .pesapal_service import PesaPalService

class PaymentFactory:
    """Factory pattern to create payment service instances"""
    
    @staticmethod
    def get_service(provider):
        services = {
            'stripe': StripeService,
            'paypal': PayPalService,
            'pesapal': PesaPalService,
        }
        
        if provider not in services:
            raise ValueError(f"Unsupported payment provider: {provider}")
        
        return services[provider]()