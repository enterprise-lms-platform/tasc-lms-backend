from django.conf import settings
from .paypal_service import PayPalService

class PaymentFactory:
    """Factory pattern to create payment service instances"""
    
    @staticmethod
    def get_service(provider):
        services = {
            'paypal': PayPalService,
        }
        
        if provider not in services:
            raise ValueError(f"Unsupported payment provider: {provider}")
        
        return services[provider]()