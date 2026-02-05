from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import Payment, Course

class PaymentTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            price=99.99
        )
        self.client.force_authenticate(user=self.user)
    
    def test_create_payment(self):
        response = self.client.post('/api/payments/', {
            'course_id': str(self.course.id),
            'payment_method': 'stripe',
            'currency': 'USD'
        })
        
        self.assertEqual(response.status_code, 201)
        self.assertIn('payment_id', response.data)