"""Wave 1 regression tests for Pesapal/backend subscription truth wiring."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalogue.models import Course
from apps.payments.models import Payment, Subscription, UserSubscription
from apps.learning.models import Enrollment
from apps.payments.services.pesapal_services import PesapalService

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
            duration_days=180,
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
        before = timezone.now()
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
        self.assertIsNotNone(user_subscription.end_date)
        expected_seconds = self.plan.duration_days * 24 * 60 * 60
        actual_seconds = (user_subscription.end_date - before).total_seconds()
        self.assertLess(abs(actual_seconds - expected_seconds), 120)  # 2 minute tolerance

    def test_subscription_payment_completion_does_not_enroll_into_course(self):
        course = Course.objects.create(
            title="Test Course",
            slug="test-course-1",
            description="desc",
            price=Decimal("99.99"),
        )
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
            provider_order_id="TRACK-WEBHOOK-2",
            course=course,
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring plan charge",
        )

        with patch("apps.payments.views_pesapal.PesapalService.handle_webhook") as mock_handle_webhook:
            mock_handle_webhook.return_value = {
                "success": True,
                "merchant_reference": str(payment.id),
                "order_tracking_id": "TRACK-WEBHOOK-2",
                "status": "COMPLETED",
                "confirmation_code": "CONF-1",
            }

            self.client.force_authenticate(user=None)
            response = self.client.get(
                "/api/v1/payments/pesapal/webhook/ipn/",
                {
                    "orderTrackingId": "TRACK-WEBHOOK-2",
                    "orderMerchantReference": str(payment.id),
                    "orderNotificationType": "IPNCHANGE",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        enrollment_exists = Enrollment.objects.filter(user=self.user, course=course, status="active").exists()
        self.assertFalse(enrollment_exists)

    def test_recurring_initiate_rejects_when_user_has_active_subscription(self):
        UserSubscription.objects.create(
            user=self.user,
            subscription=self.plan,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            price=self.plan.price,
            currency=self.plan.currency,
        )

        response = self.client.post(
            "/api/v1/payments/pesapal/recurring/initiate/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('active subscription', response.json().get('error', '').lower())

    def test_recurring_payload_uses_ddmmyyyy_dates_and_valid_frequency(self):
        """
        Regression: Pesapal recurring requires dd-MM-yyyy dates and frequency in:
        DAILY|WEEKLY|MONTHLY|YEARLY.
        """
        payment = Payment.objects.create(
            user=self.user,
            amount=self.plan.price,
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            description="Test recurring payload",
        )

        captured = {}

        def fake_post(self, path: str, payload: dict) -> dict:
            captured["path"] = path
            captured["payload"] = payload
            return {"order_tracking_id": "TRACK-1", "redirect_url": "https://sandbox.pesapal.com/checkout/rec"}

        with patch.object(PesapalService, "_post", new=fake_post):
            service = PesapalService()
            result = service.initialize_recurring_payment(payment, self.plan)

        self.assertTrue(result["success"])
        self.assertEqual(captured["path"], "/api/Transactions/SubmitOrderRequest")
        sub = captured["payload"]["subscription_details"]
        self.assertRegex(sub["start_date"], r"^\d{2}-\d{2}-\d{4}$")
        self.assertRegex(sub["end_date"], r"^\d{2}-\d{2}-\d{4}$")
        self.assertIn(sub["frequency"], {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"})

    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_recurring_payment_status_invalid_releases_paused_subscription(self, mock_verify):
        user_subscription = UserSubscription.objects.create(
            user=self.user,
            subscription=self.plan,
            status=UserSubscription.Status.PAUSED,
            price=self.plan.price,
            currency=self.plan.currency,
            end_date=timezone.now() + timedelta(days=180),
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=self.plan.price,
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            provider_order_id="TRACK-INV-STATUS",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring",
        )
        mock_verify.return_value = {
            "success": True,
            "status": "INVALID",
            "payment_method": "",
            "amount": None,
            "currency": "",
            "confirmation_code": "",
            "message": "",
            "raw": {},
        }

        response = self.client.get(f"/api/v1/payments/pesapal/{payment.id}/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "cancelled")
        self.assertEqual(user_subscription.status, UserSubscription.Status.CANCELLED)
        self.assertIsNotNone(user_subscription.cancelled_at)
        self.assertFalse(user_subscription.auto_renew)

    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_recurring_payment_status_failed_releases_paused_subscription(self, mock_verify):
        user_subscription = UserSubscription.objects.create(
            user=self.user,
            subscription=self.plan,
            status=UserSubscription.Status.PAUSED,
            price=self.plan.price,
            currency=self.plan.currency,
            end_date=timezone.now() + timedelta(days=180),
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=self.plan.price,
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            provider_order_id="TRACK-FAIL-STATUS",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring",
        )
        mock_verify.return_value = {
            "success": True,
            "status": "FAILED",
            "payment_method": "",
            "amount": None,
            "currency": "",
            "confirmation_code": "",
            "message": "",
            "raw": {},
        }

        response = self.client.get(f"/api/v1/payments/pesapal/{payment.id}/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "failed")
        self.assertEqual(user_subscription.status, UserSubscription.Status.CANCELLED)

    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_recurring_payment_status_completed_still_activates_subscription(self, mock_verify):
        before = timezone.now()
        user_subscription = UserSubscription.objects.create(
            user=self.user,
            subscription=self.plan,
            status=UserSubscription.Status.PAUSED,
            price=self.plan.price,
            currency=self.plan.currency,
            end_date=timezone.now() + timedelta(days=180),
        )
        payment = Payment.objects.create(
            user=self.user,
            amount=self.plan.price,
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            provider_order_id="TRACK-OK-STATUS",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring",
        )
        mock_verify.return_value = {
            "success": True,
            "status": "COMPLETED",
            "payment_method": "MOBILE",
            "amount": float(self.plan.price),
            "currency": "UGX",
            "confirmation_code": "CONF-STATUS-1",
            "message": "OK",
            "raw": {},
        }

        response = self.client.get(f"/api/v1/payments/pesapal/{payment.id}/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertEqual(payment.provider_payment_id, "CONF-STATUS-1")
        self.assertEqual(user_subscription.status, UserSubscription.Status.ACTIVE)
        self.assertIsNotNone(user_subscription.end_date)
        expected_seconds = self.plan.duration_days * 24 * 60 * 60
        actual_seconds = (user_subscription.end_date - before).total_seconds()
        self.assertLess(abs(actual_seconds - expected_seconds), 120)
