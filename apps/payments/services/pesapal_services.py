"""
Pesapal v3 Service
Mirrors the FlutterwaveService pattern in services/flutterwave_service.py.
All Pesapal API calls are made here — credentials never leave the backend.

Env vars required (add to .env):
    PESAPAL_CONSUMER_KEY=your_key
    PESAPAL_CONSUMER_SECRET=your_secret
    PESAPAL_ENV=demo          # or 'live'
    PESAPAL_IPN_URL=https://yourdomain.com/api/v1/payments/pesapal/webhook/ipn/
    PESAPAL_CALLBACK_URL=https://yourdomain.com/payments/callback/
"""

import logging
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

PESAPAL_DEMO_BASE = "https://cybqa.pesapal.com/pesapalv3"
PESAPAL_LIVE_BASE = "https://pay.pesapal.com/v3"


class PesapalService:
    """
    Handles all communication with the Pesapal v3 API.
    Token is fetched once and cached until expiry.
    """

    TOKEN_CACHE_KEY = "pesapal_access_token"
    TOKEN_CACHE_TTL = 60 * 4  # 4 minutes (Pesapal tokens last 5 min)

    def __init__(self):
        self.consumer_key = settings.PESAPAL_CONSUMER_KEY
        self.consumer_secret = settings.PESAPAL_CONSUMER_SECRET
        env = getattr(settings, "PESAPAL_ENV", "demo")
        self.base_url = PESAPAL_LIVE_BASE if env == "live" else PESAPAL_DEMO_BASE
        self.ipn_url = getattr(settings, "PESAPAL_IPN_URL", "")
        self.callback_url = getattr(settings, "PESAPAL_CALLBACK_URL", "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """
        Returns a valid bearer token, fetching a fresh one if needed.
        Token is cached in Django's cache backend (Redis / memcache / local).
        """
        cached = cache.get(self.TOKEN_CACHE_KEY)
        if cached:
            return cached

        response = requests.post(
            f"{self.base_url}/api/Auth/RequestToken",
            json={
                "consumer_key": self.consumer_key,
                "consumer_secret": self.consumer_secret,
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        token = data.get("token")
        if not token:
            raise ValueError(f"Pesapal token request failed: {data}")

        cache.set(self.TOKEN_CACHE_KEY, token, self.TOKEN_CACHE_TTL)
        logger.info("Pesapal: fetched fresh access token")
        return token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, params: dict = None) -> dict:
        resp = requests.get(
            f"{self.base_url}{path}",
            params=params,
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # IPN management (register once per deployment)
    # ------------------------------------------------------------------

    def register_ipn(self, ipn_url: str = None) -> dict:
        """
        Register an IPN URL with Pesapal.
        Returns { success, ipn_id, message }.
        Only needs to be called once — store the returned ipn_id in your DB
        or settings and reuse it for all orders.
        """
        url = ipn_url or self.ipn_url
        try:
            data = self._post(
                "/api/URLSetup/RegisterIPN",
                {"url": url, "ipn_notification_type": "GET"},
            )
            return {
                "success": True,
                "ipn_id": data.get("ipn_id"),
                "message": data.get("message", "IPN registered"),
            }
        except Exception as exc:
            logger.exception("Pesapal: register_ipn failed")
            return {"success": False, "message": str(exc)}

    def get_registered_ipns(self) -> dict:
        """List all IPN URLs registered under this merchant account."""
        try:
            data = self._get("/api/URLSetup/GetIpnList")
            return {"success": True, "ipns": data}
        except Exception as exc:
            logger.exception("Pesapal: get_registered_ipns failed")
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------
    # One-time order
    # ------------------------------------------------------------------

    def initialize_payment(self, payment) -> dict:
        """
        Submit a one-time order to Pesapal.
        `payment` is an instance of apps.payments.models.Payment.

        Returns:
            {
                success: bool,
                order_tracking_id: str,   # save to payment.provider_order_id
                redirect_url: str,        # send this to React
                message: str,
            }
        """
        user = payment.user
        ipn_id = getattr(settings, "PESAPAL_IPN_ID", "")

        payload = {
            "id": str(payment.id),
            "currency": payment.currency,
            "amount": float(payment.amount),
            "description": payment.description or f"Payment {payment.id}",
            "callback_url": self.callback_url,
            "notification_id": ipn_id,
            "billing_address": {
                "email_address": user.email,
                "phone_number": getattr(user, "phone_number", ""),
                "country_code": "UG",
                "first_name": user.first_name or user.email.split("@")[0],
                "middle_name": "",
                "last_name": user.last_name or "",
                "line_1": "",
                "line_2": "",
                "city": "Kampala",
                "state": "",
                "postal_code": "",
                "zip_code": "",
            },
        }

        try:
            data = self._post("/api/Transactions/SubmitOrderRequest", payload)
            tracking_id = data.get("order_tracking_id")
            redirect_url = data.get("redirect_url")

            if not tracking_id:
                return {"success": False, "message": f"Unexpected response: {data}"}

            return {
                "success": True,
                "order_tracking_id": tracking_id,
                "redirect_url": redirect_url,
                "message": "Order submitted",
            }
        except Exception as exc:
            logger.exception("Pesapal: initialize_payment failed for payment %s", payment.id)
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------
    # Recurring / subscription order
    # ------------------------------------------------------------------

    def initialize_recurring_payment(self, payment, subscription_plan) -> dict:
        """
        Submit a recurring order to Pesapal (linked to a UserSubscription).
        `subscription_plan` is an instance of apps.payments.models.Subscription.

        Pesapal recurring works the same endpoint as a one-time order but with
        the extra `subscription_details` block. The customer authorises on the
        first payment; subsequent charges happen automatically.

        Returns same shape as initialize_payment().
        """
        user = payment.user
        ipn_id = getattr(settings, "PESAPAL_IPN_ID", "")

        billing_cycle_map = {
            "monthly": "MONTHLY",
            "quarterly": "MONTHLY",   # Pesapal has no QUARTERLY; bill monthly x3
            "yearly": "ANNUALLY",
        }
        frequency = billing_cycle_map.get(subscription_plan.billing_cycle, "MONTHLY")

        start_date = timezone.now().date().isoformat()
        end_date = (timezone.now() + timedelta(days=365)).date().isoformat()

        payload = {
            "id": str(payment.id),
            "currency": payment.currency,
            "amount": float(payment.amount),
            "description": f"{subscription_plan.name} subscription",
            "callback_url": self.callback_url,
            "notification_id": ipn_id,
            "account_number": str(user.id),
            "subscription_details": {
                "start_date": start_date,
                "end_date": end_date,
                "frequency": frequency,
            },
            "billing_address": {
                "email_address": user.email,
                "phone_number": getattr(user, "phone_number", ""),
                "country_code": "UG",
                "first_name": user.first_name or user.email.split("@")[0],
                "middle_name": "",
                "last_name": user.last_name or "",
                "line_1": "",
                "line_2": "",
                "city": "Kampala",
                "state": "",
                "postal_code": "",
                "zip_code": "",
            },
        }

        try:
            data = self._post("/api/Transactions/SubmitOrderRequest", payload)
            tracking_id = data.get("order_tracking_id")
            redirect_url = data.get("redirect_url")

            if not tracking_id:
                return {"success": False, "message": f"Unexpected response: {data}"}

            return {
                "success": True,
                "order_tracking_id": tracking_id,
                "redirect_url": redirect_url,
                "message": "Recurring order submitted",
            }
        except Exception as exc:
            logger.exception(
                "Pesapal: initialize_recurring_payment failed for payment %s", payment.id
            )
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------
    # Transaction status
    # ------------------------------------------------------------------

    def verify_payment(self, order_tracking_id: str) -> dict:
        """
        Get the current status of a transaction by order_tracking_id.

        Returns:
            {
                success: bool,
                status: str,           # 'COMPLETED' | 'PENDING' | 'FAILED' | 'INVALID'
                payment_method: str,
                amount: float,
                currency: str,
                message: str,
                raw: dict,
            }
        """
        try:
            data = self._get(
                "/api/Transactions/GetTransactionStatus",
                params={"orderTrackingId": order_tracking_id},
            )
            status_code = data.get("payment_status_description", "").upper()

            return {
                "success": True,
                "status": status_code,
                "payment_method": data.get("payment_method", ""),
                "amount": data.get("amount"),
                "currency": data.get("currency"),
                "confirmation_code": data.get("confirmation_code", ""),
                "message": data.get("message", ""),
                "raw": data,
            }
        except Exception as exc:
            logger.exception("Pesapal: verify_payment failed for %s", order_tracking_id)
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel_order(self, order_tracking_id: str) -> dict:
        """
        Cancel a pending order (one-time or recurring).
        Returns { success, message }.
        """
        try:
            data = self._get(
                "/api/Transactions/CancelOrder",
                params={"orderTrackingId": order_tracking_id},
            )
            return {
                "success": data.get("status") == "200",
                "message": data.get("message", ""),
                "raw": data,
            }
        except Exception as exc:
            logger.exception("Pesapal: cancel_order failed for %s", order_tracking_id)
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------
    # Refund
    # ------------------------------------------------------------------

    def refund_payment(self, order_tracking_id: str, amount: float, remarks: str = "") -> dict:
        """
        Request a refund for a completed transaction.
        Returns { success, message }.
        """
        try:
            data = self._post(
                "/api/Transactions/RefundRequest",
                {
                    "confirmation_code": order_tracking_id,
                    "amount": amount,
                    "username": "system",
                    "remarks": remarks or "Customer requested refund",
                },
            )
            return {
                "success": data.get("status") == "200",
                "message": data.get("message", ""),
                "raw": data,
            }
        except Exception as exc:
            logger.exception("Pesapal: refund_payment failed for %s", order_tracking_id)
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------
    # IPN webhook handler (called from WebhookView)
    # ------------------------------------------------------------------

    def handle_webhook(self, request) -> dict:
        """
        Pesapal sends IPN as a GET request with query params:
            ?orderTrackingId=...&orderMerchantReference=...&orderNotificationType=IPNCHANGE

        This method verifies the transaction and returns a result dict
        that the view uses to update the Payment record.
        """
        order_tracking_id = request.GET.get("orderTrackingId")
        merchant_reference = request.GET.get("orderMerchantReference")  # = payment.id
        notification_type = request.GET.get("orderNotificationType", "")

        if not order_tracking_id:
            return {"success": False, "message": "Missing orderTrackingId"}

        logger.info(
            "Pesapal IPN received: tracking_id=%s ref=%s type=%s",
            order_tracking_id,
            merchant_reference,
            notification_type,
        )

        # Verify the actual status with Pesapal (never trust IPN alone)
        result = self.verify_payment(order_tracking_id)
        result["order_tracking_id"] = order_tracking_id
        result["merchant_reference"] = merchant_reference
        return result