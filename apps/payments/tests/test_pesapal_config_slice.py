"""Surgical tests: Pesapal callback redirect base + IPN register URL alignment."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import resolve, reverse


class PesapalCallbackRedirectSliceTests(TestCase):
    @override_settings(FRONTEND_BASE_URL="https://app.example.com")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_callback_redirect_success_uses_frontend_base(self, mock_verify):
        mock_verify.return_value = {"success": True, "status": "COMPLETED"}
        response = self.client.get(
            "/api/v1/payments/pesapal/callback/",
            {"OrderTrackingId": "T1", "OrderMerchantReference": "abc"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://app.example.com/payments/success?tracking_id=T1&ref=abc",
        )

    @override_settings(FRONTEND_BASE_URL="https://app.example.com")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_callback_redirect_failed(self, mock_verify):
        mock_verify.return_value = {"success": True, "status": "FAILED"}
        response = self.client.get(
            "/api/v1/payments/pesapal/callback/",
            {"OrderTrackingId": "T2", "OrderMerchantReference": "x"},
        )
        self.assertEqual(response.status_code, 302)
        loc = response["Location"]
        self.assertIn("/payments/failed", loc)
        self.assertIn("tracking_id=T2", loc)

    @override_settings(FRONTEND_BASE_URL="https://app.example.com")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_callback_redirect_pending_unknown_status(self, mock_verify):
        mock_verify.return_value = {"success": True, "status": "PENDING"}
        response = self.client.get(
            "/api/v1/payments/pesapal/callback/",
            {"OrderTrackingId": "T3", "OrderMerchantReference": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/payments/pending", response["Location"])

    @override_settings(FRONTEND_BASE_URL="https://app.example.com")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_callback_verify_failure_maps_to_failed_route(self, mock_verify):
        mock_verify.return_value = {"success": False, "message": "network"}
        response = self.client.get(
            "/api/v1/payments/pesapal/callback/",
            {"OrderTrackingId": "T4", "OrderMerchantReference": "r"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/payments/failed", response["Location"])

    @override_settings(FRONTEND_BASE_URL="https://fe.example/")
    @patch("apps.payments.views_pesapal.PesapalService.verify_payment")
    def test_callback_strips_trailing_slash_on_frontend_base(self, mock_verify):
        mock_verify.return_value = {"success": True, "status": "COMPLETED"}
        response = self.client.get(
            "/api/v1/payments/pesapal/callback/",
            {"OrderTrackingId": "T5", "OrderMerchantReference": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse("//payments/" in response["Location"])
        self.assertTrue(response["Location"].startswith("https://fe.example/payments/"))


class PesapalIpnRegisterRouteSliceTests(TestCase):
    def test_ipn_register_reverse_matches_frontend_service_path(self):
        url = reverse("pesapal-ipn-register")
        self.assertIn("pesapal/ipn-admin/register", url)

    def test_legacy_ipn_register_alias_resolves(self):
        match = resolve("/api/v1/payments/pesapal/ipn/register/")
        self.assertEqual(match.url_name, "pesapal-ipn-register-legacy")


class PesapalSettingsFrontendAliasTests(TestCase):
    def test_frontend_url_alias_matches_base(self):
        from django.conf import settings

        self.assertEqual(settings.FRONTEND_URL, settings.FRONTEND_BASE_URL)
