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
from apps.payments.models import Invoice, InvoiceItem, Payment, Subscription, UserSubscription
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
        self.assertIn(
            "pesapal/initiate-subscription-onetime",
            reverse("pesapal-payment-initiate-subscription-onetime"),
        )
        self.assertIn("pesapal/recurring/initiate", reverse("pesapal-recurring-initiate"))
        self.assertIn(
            "pesapal/ipn-admin/register",
            reverse("pesapal-ipn-register"),
        )
        self.assertEqual(
            resolve("/api/v1/payments/pesapal/ipn/register/").url_name,
            "pesapal-ipn-register-legacy",
        )


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

    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    def test_onetime_subscription_initiate_creates_payment_paused_sub_and_metadata(
        self, mock_initialize_payment
    ):
        mock_initialize_payment.return_value = {
            "success": True,
            "order_tracking_id": "TRACK-OT-SUB-1",
            "redirect_url": "https://sandbox.pesapal.com/checkout/ot-sub",
        }

        response = self.client.post(
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["order_tracking_id"], "TRACK-OT-SUB-1")
        self.assertIn("user_subscription_id", response.data)

        payment = Payment.objects.get(id=response.data["payment_id"])
        self.assertIsNone(payment.course)
        self.assertEqual(payment.status, "pending")
        self.assertEqual(
            payment.metadata.get("user_subscription_id"),
            response.data["user_subscription_id"],
        )

        user_subscription = UserSubscription.objects.get(
            id=response.data["user_subscription_id"]
        )
        self.assertEqual(user_subscription.status, UserSubscription.Status.PAUSED)
        self.assertEqual(user_subscription.subscription_id, self.plan.id)
        self.assertIsNotNone(user_subscription.end_date)
        mock_initialize_payment.assert_called_once()

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
        for key in ("orderNotificationType", "orderTrackingId", "orderMerchantReference", "status"):
            self.assertIn(key, response.data)
        self.assertEqual(response.data["status"], "ACCEPTED")

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

    @patch.object(PesapalService, "verify_payment")
    def test_ipn_accepts_documented_pascal_case_query_params(self, mock_verify):
        payment = Payment.objects.create(
            user=self.user,
            amount=self.plan.price,
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            provider_order_id="TRACK-PASCAL",
            description="IPN param test",
        )
        mock_verify.return_value = {
            "success": True,
            "status": "PENDING",
            "payment_method": "",
            "amount": None,
            "currency": "",
            "confirmation_code": "",
            "message": "",
            "raw": {},
        }
        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/api/v1/payments/pesapal/webhook/ipn/",
            {
                "OrderTrackingId": "TRACK-PASCAL",
                "OrderMerchantReference": str(payment.id),
                "OrderNotificationType": "IPNCHANGE",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_verify.assert_called_once_with("TRACK-PASCAL")
        for key in ("orderNotificationType", "orderTrackingId", "orderMerchantReference", "status"):
            self.assertIn(key, response.data)
        self.assertEqual(response.data["orderTrackingId"], "TRACK-PASCAL")
        self.assertEqual(response.data["orderNotificationType"], "IPNCHANGE")

    @patch.object(PesapalService, "verify_payment")
    def test_ipn_reversed_releases_linked_paused_subscription(self, mock_verify):
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
            provider_order_id="TRACK-IPN-REV",
            metadata={"user_subscription_id": user_subscription.id},
            description="IPN reversed",
        )
        mock_verify.return_value = {
            "success": True,
            "status": "REVERSED",
            "payment_method": "",
            "amount": None,
            "currency": "",
            "confirmation_code": "",
            "message": "",
            "raw": {},
        }
        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/api/v1/payments/pesapal/webhook/ipn/",
            {
                "orderTrackingId": "TRACK-IPN-REV",
                "orderMerchantReference": str(payment.id),
                "orderNotificationType": "IPNCHANGE",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ACCEPTED")
        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "cancelled")
        self.assertEqual(user_subscription.status, UserSubscription.Status.CANCELLED)

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

    def test_onetime_subscription_initiate_rejects_when_user_has_active_subscription(self):
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
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("active subscription", response.json().get("error", "").lower())

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
    def test_recurring_payment_status_reversed_releases_paused_subscription(self, mock_verify):
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
            provider_order_id="TRACK-REV-STATUS",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring",
        )
        mock_verify.return_value = {
            "success": True,
            "status": "REVERSED",
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
        invoice = Invoice.objects.get(payment=payment)
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.invoice_type, Invoice.InvoiceType.SUBSCRIPTION)
        self.assertEqual(invoice.total_amount, payment.amount)
        self.assertEqual(invoice.paid_amount, payment.amount)
        self.assertEqual(invoice.currency, payment.currency)
        self.assertEqual(invoice.items.count(), 1)
        invoice_item = invoice.items.first()
        self.assertEqual(invoice_item.item_type, "subscription")
        self.assertEqual(invoice_item.item_id, self.plan.id)
        self.assertEqual(invoice_item.quantity, 1)
        self.assertEqual(invoice_item.unit_price, payment.amount)

    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    def test_onetime_subscription_initiate_completion_via_status_activates_sub(
        self, mock_initialize_payment, mock_verify
    ):
        mock_initialize_payment.return_value = {
            "success": True,
            "order_tracking_id": "TRACK-OT-STATUS-1",
            "redirect_url": "https://sandbox.pesapal.com/checkout/ot",
        }
        before = timezone.now()
        init = self.client.post(
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(init.status_code, status.HTTP_201_CREATED)
        payment_id = init.data["payment_id"]
        user_sub_id = init.data["user_subscription_id"]

        mock_verify.return_value = {
            "success": True,
            "status": "COMPLETED",
            "payment_method": "MOBILE",
            "amount": float(self.plan.price),
            "currency": "UGX",
            "confirmation_code": "CONF-OT-1",
            "message": "OK",
            "raw": {},
        }

        response = self.client.get(f"/api/v1/payments/pesapal/{payment_id}/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payment = Payment.objects.get(id=payment_id)
        user_subscription = UserSubscription.objects.get(id=user_sub_id)
        self.assertEqual(payment.status, "completed")
        self.assertEqual(payment.provider_payment_id, "CONF-OT-1")
        self.assertEqual(user_subscription.status, UserSubscription.Status.ACTIVE)
        self.assertIsNotNone(user_subscription.end_date)
        expected_seconds = self.plan.duration_days * 24 * 60 * 60
        actual_seconds = (user_subscription.end_date - before).total_seconds()
        self.assertLess(abs(actual_seconds - expected_seconds), 120)

    @patch("apps.notifications.services.send_subscription_payment_success_email")
    @patch("apps.payments.views_pesapal.PesapalService.handle_webhook")
    def test_ipn_completion_sends_subscription_success_email_once(
        self, mock_handle_webhook, mock_send_email
    ):
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
            provider_order_id="TRACK-IPN-EMAIL-1",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring plan charge",
        )
        mock_send_email.return_value = True
        mock_handle_webhook.return_value = {
            "success": True,
            "merchant_reference": str(payment.id),
            "order_tracking_id": "TRACK-IPN-EMAIL-1",
            "status": "COMPLETED",
            "confirmation_code": "CONF-IPN-EMAIL-1",
        }

        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/api/v1/payments/pesapal/webhook/ipn/",
            {
                "orderTrackingId": "TRACK-IPN-EMAIL-1",
                "orderMerchantReference": str(payment.id),
                "orderNotificationType": "IPNCHANGE",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertTrue(payment.success_email_sent)
        mock_send_email.assert_called_once_with(payment)

    @patch("apps.notifications.services.send_subscription_payment_success_email")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_status_completion_sends_subscription_success_email_once(
        self, mock_verify, mock_send_email
    ):
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
            provider_order_id="TRACK-STATUS-EMAIL-1",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring",
        )
        mock_send_email.return_value = True
        mock_verify.return_value = {
            "success": True,
            "status": "COMPLETED",
            "payment_method": "MOBILE",
            "amount": float(self.plan.price),
            "currency": "UGX",
            "confirmation_code": "CONF-STATUS-EMAIL-1",
            "message": "OK",
            "raw": {},
        }

        response = self.client.get(f"/api/v1/payments/pesapal/{payment.id}/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertTrue(payment.success_email_sent)
        mock_send_email.assert_called_once_with(payment)

    @patch("apps.notifications.services.send_subscription_payment_success_email")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_repeated_status_after_completion_does_not_resend_email(
        self, mock_verify, mock_send_email
    ):
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
            provider_order_id="TRACK-STATUS-EMAIL-2",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring",
        )
        mock_send_email.return_value = True
        mock_verify.return_value = {
            "success": True,
            "status": "COMPLETED",
            "payment_method": "MOBILE",
            "amount": float(self.plan.price),
            "currency": "UGX",
            "confirmation_code": "CONF-STATUS-EMAIL-2",
            "message": "OK",
            "raw": {},
        }

        first = self.client.get(f"/api/v1/payments/pesapal/{payment.id}/status/")
        second = self.client.get(f"/api/v1/payments/pesapal/{payment.id}/status/")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertEqual(mock_send_email.call_count, 1)
        self.assertEqual(Invoice.objects.filter(payment=payment).count(), 1)
        self.assertEqual(InvoiceItem.objects.filter(invoice__payment=payment).count(), 1)

    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_status_completion_preserves_existing_linked_invoice(self, mock_verify):
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
            provider_order_id="TRACK-STATUS-INVOICE-EXISTING",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring",
        )
        invoice = Invoice.objects.create(
            user=self.user,
            payment=payment,
            invoice_type=Invoice.InvoiceType.SUBSCRIPTION,
            customer_name="Existing Customer",
            customer_email=self.user.email,
            subtotal=payment.amount,
            total_amount=payment.amount,
            paid_amount=payment.amount,
            currency=payment.currency,
            status=Invoice.Status.PAID,
            paid_at=timezone.now(),
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            item_type="subscription",
            item_id=self.plan.id,
            description="Existing subscription line item",
            quantity=1,
            unit_price=payment.amount,
        )

        mock_verify.return_value = {
            "success": True,
            "status": "COMPLETED",
            "payment_method": "MOBILE",
            "amount": float(self.plan.price),
            "currency": "UGX",
            "confirmation_code": "CONF-STATUS-EXISTING",
            "message": "OK",
            "raw": {},
        }

        response = self.client.get(f"/api/v1/payments/pesapal/{payment.id}/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(Invoice.objects.filter(payment=payment).count(), 1)
        self.assertEqual(InvoiceItem.objects.filter(invoice=invoice).count(), 1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_name, "Existing Customer")

    @patch("apps.notifications.services.send_subscription_payment_success_email")
    @patch("apps.payments.views_pesapal.PesapalService.handle_webhook")
    def test_repeated_ipn_after_completion_does_not_resend_email(
        self, mock_handle_webhook, mock_send_email
    ):
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
            provider_order_id="TRACK-IPN-EMAIL-2",
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring plan charge",
        )
        mock_send_email.return_value = True
        mock_handle_webhook.return_value = {
            "success": True,
            "merchant_reference": str(payment.id),
            "order_tracking_id": "TRACK-IPN-EMAIL-2",
            "status": "COMPLETED",
            "confirmation_code": "CONF-IPN-EMAIL-2",
        }

        self.client.force_authenticate(user=None)
        first = self.client.get(
            "/api/v1/payments/pesapal/webhook/ipn/",
            {
                "orderTrackingId": "TRACK-IPN-EMAIL-2",
                "orderMerchantReference": str(payment.id),
                "orderNotificationType": "IPNCHANGE",
            },
        )
        second = self.client.get(
            "/api/v1/payments/pesapal/webhook/ipn/",
            {
                "orderTrackingId": "TRACK-IPN-EMAIL-2",
                "orderMerchantReference": str(payment.id),
                "orderNotificationType": "IPNCHANGE",
            },
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertEqual(mock_send_email.call_count, 1)
        self.assertEqual(Invoice.objects.filter(payment=payment).count(), 1)
        self.assertEqual(InvoiceItem.objects.filter(invoice__payment=payment).count(), 1)

    @patch("apps.notifications.services.send_subscription_payment_success_email")
    def test_non_subscription_payment_does_not_send_subscription_success_email(
        self, mock_send_email
    ):
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal("10.00"),
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            description="One-time course payment",
        )

        payment.mark_completed()
        payment.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        mock_send_email.assert_not_called()

    @patch("apps.notifications.services.send_subscription_payment_success_email")
    def test_missing_user_email_does_not_break_completion_flow(self, mock_send_email):
        self.user.email = ""
        self.user.save(update_fields=["email"])
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
            metadata={"user_subscription_id": user_subscription.id},
            description="Recurring plan charge",
        )

        payment.mark_completed()
        payment.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertFalse(payment.success_email_sent)
        mock_send_email.assert_not_called()

    def _stuck_subscription_checkout(self):
        """Paused sub + pending linked Pesapal payment (simulates abandoned hosted checkout)."""
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
            provider_order_id="TRACK-STUCK-1",
            metadata={"user_subscription_id": user_subscription.id},
            description="Stuck checkout",
        )
        return user_subscription, payment

    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_onetime_initiate_reconciles_failed_provider_and_allows_retry(
        self, mock_verify, mock_initialize_payment
    ):
        user_subscription, payment = self._stuck_subscription_checkout()
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
        mock_initialize_payment.return_value = {
            "success": True,
            "order_tracking_id": "TRACK-RETRY-1",
            "redirect_url": "https://sandbox.pesapal.com/checkout/retry",
        }

        response = self.client.post(
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "failed")
        self.assertEqual(user_subscription.status, UserSubscription.Status.CANCELLED)
        mock_verify.assert_called_once_with("TRACK-STUCK-1")
        mock_initialize_payment.assert_called_once()

    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_onetime_initiate_reconciles_invalid_provider_and_allows_retry(
        self, mock_verify, mock_initialize_payment
    ):
        user_subscription, payment = self._stuck_subscription_checkout()
        payment.provider_order_id = "TRACK-STUCK-INV"
        payment.save(update_fields=["provider_order_id"])
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
        mock_initialize_payment.return_value = {
            "success": True,
            "order_tracking_id": "TRACK-RETRY-2",
            "redirect_url": "https://sandbox.pesapal.com/checkout/retry2",
        }

        response = self.client.post(
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "cancelled")
        self.assertEqual(user_subscription.status, UserSubscription.Status.CANCELLED)

    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_onetime_initiate_reconciles_completed_and_still_blocks(
        self, mock_verify, mock_initialize_payment
    ):
        user_subscription, payment = self._stuck_subscription_checkout()
        mock_verify.return_value = {
            "success": True,
            "status": "COMPLETED",
            "payment_method": "MOBILE",
            "amount": float(self.plan.price),
            "currency": "UGX",
            "confirmation_code": "CONF-STUCK",
            "message": "OK",
            "raw": {},
        }

        response = self.client.post(
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_initialize_payment.assert_not_called()
        payment.refresh_from_db()
        user_subscription.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertEqual(user_subscription.status, UserSubscription.Status.ACTIVE)

    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_onetime_initiate_verify_failure_does_not_unblock(
        self, mock_verify, mock_initialize_payment
    ):
        self._stuck_subscription_checkout()
        mock_verify.return_value = {"success": False, "message": "network error"}

        response = self.client.post(
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_initialize_payment.assert_not_called()

    @patch("apps.payments.views_pesapal.PesapalService.initialize_payment")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_onetime_initiate_pending_provider_does_not_unblock(
        self, mock_verify, mock_initialize_payment
    ):
        self._stuck_subscription_checkout()
        mock_verify.return_value = {
            "success": True,
            "status": "PENDING",
            "payment_method": "",
            "amount": None,
            "currency": "",
            "confirmation_code": "",
            "message": "",
            "raw": {},
        }

        response = self.client.post(
            "/api/v1/payments/pesapal/initiate-subscription-onetime/",
            {"subscription_id": self.plan.id, "currency": "UGX"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_initialize_payment.assert_not_called()

    @patch.object(PesapalService, "_post")
    def test_initialize_payment_billing_phone_is_string_never_null(self, mock_post):
        mock_post.return_value = {
            "order_tracking_id": "T1",
            "redirect_url": "https://sandbox.pesapal.com/x",
        }
        self.user.phone_number = None
        self.user.save(update_fields=["phone_number"])
        payment = Payment.objects.create(
            user=self.user,
            amount=self.plan.price,
            currency="UGX",
            payment_method="pesapal",
            status="pending",
            description="billing hygiene",
        )
        result = PesapalService().initialize_payment(payment)
        self.assertTrue(result["success"])
        payload = mock_post.call_args[0][1]
        self.assertIsInstance(payload["billing_address"]["phone_number"], str)
        self.assertEqual(payload["billing_address"]["phone_number"], "")
