"""Wave 1 regression tests for Pesapal/backend subscription truth wiring."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.payments.models import Payment, Subscription, UserSubscription

User = get_user_model()


class PaymentsRouteReachabilityTest(APITestCase):
    def test_subscription_me_route_resolves(self):
        match = resolve("/api/v1/payments/subscription/me/")
        self.assertEqual(match.url_name, "subscription-me")

    def test_core_pesapal_routes_resolve(self):
        self.assertEqual(
            resolve("/api/v1/payments/pesapal/webhook/ipn/").url_name,
            "pesapal-webhook-ipn",
        )
        self.assertEqual(
            resolve("/api/v1/payments/pesapal/callback/").url_name,
            "pesapal-callback",
        )
        # Router actions should coexist with subscription/me and callback/IPN routes.
        self.assertIn("pesapal/initiate", reverse("pesapal-payment-initiate"))
        self.assertIn("pesapal/recurring/initiate", reverse("pesapal-recurring-initiate"))


class PesapalFlowWave1Test(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pesapaluser",
            email="pesapal@example.com",
            password="pass1234",
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.client.force_authenticate(self.user)
        self.plan = Subscription.objects.create(
            name="Wave 1 Plan",
            description="Plan for tests",
            price=Decimal("49.00"),
            currency="UGX",
            billing_cycle="monthly",
            status=Subscription.Status.ACTIVE,
        )

    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    def test_pesapal_initiate_returns_expected_payload(self, mock_initialize_payment):
        mock_initialize_payment.return_value = {
            "success": True,
            "order_tracking_id": "TRACK-123",
            "redirect_url": "https://sandbox.pesapal.com/checkout/abc",
        }

        response = self.client.post(
            "/api/v1/payments/pesapal/initiate/",
            {"amount": "49.00", "currency": "UGX", "description": "Test payment"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("payment_id", response.data)
        self.assertEqual(response.data["order_tracking_id"], "TRACK-123")
        self.assertEqual(
            response.data["redirect_url"],
            "https://sandbox.pesapal.com/checkout/abc",
        )

    @patch("apps.payments.views_pesapal.PesapalService.initialize_recurring_payment")
    def test_recurring_initiate_persists_valid_pre_activation_status(self, mock_initialize):
        mock_initialize.return_value = {
            "success": True,
            "order_tracking_id": "TRACK-REC-1",
            "redirect_url": "https://sandbox.pesapal.com/checkout/rec",
        }

        response = self.client.post(
            "/api/v1/payments/pesapal/recurring/initiate/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user_subscription = UserSubscription.objects.get(id=response.data["subscription_id"])
        self.assertEqual(user_subscription.status, UserSubscription.Status.PAUSED)

    @patch("apps.payments.views_pesapal.PesapalService.handle_webhook")
    def test_successful_webhook_completion_activates_linked_subscription(self, mock_handle_webhook):
        user_subscription = UserSubscription.objects.create(
            user=self.user,
            subscription=self.plan,
            status=UserSubscription.Status.PAUSED,
            price=self.plan.price,
            currency=self.plan.currency,
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=self.plan.price,
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            provider_order_id="TRACK-WEBHOOK-1",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring plan charge",
        )

        mock_handle_webhook.return_value = {
            "success": True,
            "merchant_reference": str(payment.id),
            "order_tracking_id": "TRACK-WEBHOOK-1",
            "status": "COMPLETED",
            "confirmation_code": "CONF-1",
        }

        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/api/v1/payments/pesapal/webhook/ipn/",
            {
                "orderTrackingId": "TRACK-WEBHOOK-1",
                "orderMerchantReference": str(payment.id),
                "orderNotificationType": "IPNCHANGE",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertEqual(user_subscription.status, UserSubscription.Status.ACTIVE)
