from django.conf import settings
from .flutterwave_service import FlutterwaveService

class PaymentFactory:
    """Factory pattern to create payment service instances"""
    
    @staticmethod
    def get_service(provider):
        services = {
            'paypal': FlutterwaveService,
        }
        
        if provider not in services:
            raise ValueError(f"Unsupported payment provider: {provider}")
        
        return services[provider]()