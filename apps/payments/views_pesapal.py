"""
apps/payments/views_pesapal.py
===============================
Add these views to your payments app alongside the existing views.py.
Register them in urls.py (see urls_pesapal.py).

Architecture recap:
  React → POST /api/v1/payments/pesapal/initiate/
        ← { redirect_url }        (React redirects user here)
  User pays on Pesapal hosted page
  Pesapal → GET  /api/v1/payments/pesapal/webhook/ipn/  (IPN — server-to-server)
  Pesapal → GET  /api/v1/payments/pesapal/callback/     (browser hits API first; view redirects to SPA)
  React   → GET  /api/v1/payments/pesapal/{id}/status/  (poll or verify)
"""

import logging

from datetime import timedelta
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from apps.audit.services import log_event  # your existing audit service

from .models import Invoice, InvoiceItem, Payment, PesapalIPN, UserSubscription
from .serializers import PaymentSerializer, UserSubscriptionSerializer
from .serializers import (
    PesapalInitiateSerializer,
    PesapalIPNSerializer,
    PesapalOrderStatusSerializer,
    PesapalRecurringInitiateSerializer,
    PesapalSubscriptionOneTimeInitiateSerializer,
)
from .services.pesapal_services import PesapalService, pesapal_get_request_query

logger = logging.getLogger(__name__)


def _pesapal_frontend_redirect_base():
    """SPA origin for post-checkout redirects (canonical: settings.FRONTEND_BASE_URL)."""
    from django.conf import settings as django_settings

    base = getattr(django_settings, "FRONTEND_BASE_URL", None) or getattr(
        django_settings, "FRONTEND_URL", None
    )
    if not base:
        return "http://localhost:5173"
    return str(base).rstrip("/")


def _user_has_blocking_active_or_paused_subscription(user):
    """True if user already has an ACTIVE or PAUSED sub with no end or end in the future."""
    now = timezone.now()
    return UserSubscription.objects.filter(
        user=user,
        status__in=[UserSubscription.Status.ACTIVE, UserSubscription.Status.PAUSED],
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=now)).exists()


def _subscription_end_date_from_plan(subscription_plan):
    duration_days = getattr(subscription_plan, "duration_days", 180)
    return timezone.now() + timedelta(days=duration_days)


def _release_paused_subscription_for_failed_recurring(payment):
    """
    Recurring checkout leaves UserSubscription PAUSED until payment completes.
    On terminal non-success (failed/cancelled payment row), cancel a still-PAUSED
    linked sub so PesapalRecurringViewSet.initiate can retry.
    Same local fields as PesapalRecurringViewSet.cancel (without the Pesapal API call).
    """
    if payment.payment_method != "pesapal":
        return
    meta = payment.metadata or {}
    sub_id = meta.get("user_subscription_id")
    if not sub_id:
        return
    try:
        us = UserSubscription.objects.get(id=sub_id)
    except UserSubscription.DoesNotExist:
        return
    if us.status != UserSubscription.Status.PAUSED:
        return
    us.status = UserSubscription.Status.CANCELLED
    us.cancelled_at = timezone.now()
    us.auto_renew = False
    us.save(update_fields=["status", "cancelled_at", "auto_renew"])


def _sync_payment_from_pesapal_verify(payment, result, request=None):
    """
    Apply Pesapal verify_payment() result to a Payment. Only mutates when result["success"]
    and status is a known terminal or completed state. PENDING or unknown/empty: no change.

    Returns True if local payment/subscription state may have been updated, else False.
    """
    if not result.get("success"):
        return False
    if payment.status != "pending":
        return False
    pesapal_status = (result.get("status") or "").upper()
    if not pesapal_status:
        return False

    if pesapal_status == "COMPLETED":
        payment.mark_completed()
        payment.provider_payment_id = result.get("confirmation_code", "") or ""
        payment.save(update_fields=["provider_payment_id"])
        subscription_id = (payment.metadata or {}).get("user_subscription_id")
        if subscription_id:
            try:
                us = UserSubscription.objects.get(id=subscription_id)
                if us.status != UserSubscription.Status.ACTIVE:
                    now = timezone.now()
                    duration_days = getattr(us.subscription, "duration_days", 180)
                    us.status = UserSubscription.Status.ACTIVE
                    if (not us.end_date) or us.end_date <= now:
                        us.end_date = now + timedelta(days=duration_days)
                        us.save(update_fields=["status", "end_date"])
                    else:
                        us.save(update_fields=["status"])
            except UserSubscription.DoesNotExist:
                pass
        log_event(
            action="updated",
            resource="payment",
            resource_id=str(payment.id),
            actor=getattr(request, "user", None) if request else None,
            request=request,
            details=f"Pesapal payment completed: {payment.amount} {payment.currency}",
        )
        return True

    if pesapal_status == "FAILED":
        payment.status = "failed"
        payment.save(update_fields=["status"])
        _release_paused_subscription_for_failed_recurring(payment)
        return True

    if pesapal_status == "INVALID":
        payment.status = "cancelled"
        payment.save(update_fields=["status"])
        _release_paused_subscription_for_failed_recurring(payment)
        return True

    if pesapal_status == "REVERSED":
        payment.status = "cancelled"
        payment.save(update_fields=["status"])
        _release_paused_subscription_for_failed_recurring(payment)
        return True

    return False


def _reconcile_stale_subscription_checkouts_for_user(user):
    """
    Before blocking a new subscription checkout, refresh provider truth for any
    PAUSED subscription still tied to a pending Pesapal payment.
    """
    now = timezone.now()
    paused_subs = UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.Status.PAUSED,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=now))

    service = PesapalService()
    for us in paused_subs:
        payment = (
            Payment.objects.filter(
                user=user,
                status="pending",
                payment_method="pesapal",
                metadata__user_subscription_id=us.id,
            )
            .order_by("-created_at")
            .first()
        )
        if not payment or not payment.provider_order_id:
            continue
        result = service.verify_payment(payment.provider_order_id)
        _sync_payment_from_pesapal_verify(payment, result, request=None)


# ─────────────────────────────────────────────────────────────────────────────
# One-time payments
# ─────────────────────────────────────────────────────────────────────────────


@extend_schema(tags=["Payments - Pesapal"])
class PesapalPaymentViewSet(viewsets.GenericViewSet):
    """
    Handles one-time Pesapal payments.
    Mirrors the structure of PaymentViewSet (Flutterwave).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "role") and user.role in ["finance", "tasc_admin", "lms_manager"]:
            return Payment.objects.filter(payment_method="pesapal")
        return Payment.objects.filter(user=user, payment_method="pesapal")

    # ------------------------------------------------------------------
    @extend_schema(
        summary="Initiate Pesapal payment",
        description=(
            "Creates a Payment record and submits an order to Pesapal. "
            "Returns a redirect_url — send the user there to complete payment."
        ),
        request=PesapalInitiateSerializer,
        responses={
            201: OpenApiResponse(description="{ payment_id, redirect_url, order_tracking_id }"),
            400: OpenApiResponse(description="Validation or Pesapal error"),
        },
    )
    @action(detail=False, methods=["post"], url_path="initiate")
    def initiate(self, request):
        serializer = PesapalInitiateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = Payment.objects.create(
            user=request.user,
            course=data.get("course"),
            amount=data["amount"],
            currency=data.get("currency", "UGX"),
            payment_method="pesapal",
            description=data.get("description", "Course payment"),
        )

        service = PesapalService()
        result = service.initialize_payment(payment)

        if result["success"]:
            # Store the Pesapal tracking ID so we can look it up on IPN/callback
            payment.provider_order_id = result["order_tracking_id"]
            payment.save(update_fields=["provider_order_id"])

            log_event(
                action="created",
                resource="payment",
                resource_id=str(payment.id),
                actor=request.user,
                request=request,
                details=(
                    f"Pesapal payment initiated: amount={payment.amount} "
                    f"{payment.currency} | course={payment.course_id}"
                ),
            )

            return Response(
                {
                    "payment_id": str(payment.id),
                    "redirect_url": result["redirect_url"],
                    "order_tracking_id": result["order_tracking_id"],
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            payment.status = "failed"
            payment.save(update_fields=["status"])
            return Response(
                {"error": result.get("message", "Pesapal order submission failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # ------------------------------------------------------------------
    @extend_schema(
        summary="Initiate one-time Pesapal checkout for a subscription plan",
        description=(
            "Creates Payment + paused UserSubscription, links metadata.user_subscription_id, "
            "and calls standard Pesapal SubmitOrderRequest (not recurring). "
            "Completion is handled by the same IPN and payment_status flow as recurring checkout."
        ),
        request=PesapalSubscriptionOneTimeInitiateSerializer,
        responses={
            201: OpenApiResponse(
                description=(
                    "{ payment_id, redirect_url, order_tracking_id, user_subscription_id }"
                )
            ),
            400: OpenApiResponse(description="Validation, blocking subscription, or Pesapal error"),
        },
    )
    @action(detail=False, methods=["post"], url_path="initiate-subscription-onetime")
    def initiate_subscription_onetime(self, request):
        serializer = PesapalSubscriptionOneTimeInitiateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        _reconcile_stale_subscription_checkouts_for_user(request.user)
        if _user_has_blocking_active_or_paused_subscription(request.user):
            return Response(
                {"error": "An active subscription already exists for this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subscription_plan = serializer.validated_data["subscription_id"]
        currency = serializer.validated_data.get("currency", "UGX")

        payment = Payment.objects.create(
            user=request.user,
            course=None,
            amount=subscription_plan.price,
            currency=currency,
            payment_method="pesapal",
            description=f"{subscription_plan.name} subscription (one-time checkout)",
        )

        user_subscription = UserSubscription.objects.create(
            user=request.user,
            subscription=subscription_plan,
            status=UserSubscription.Status.PAUSED,
            price=subscription_plan.price,
            currency=currency,
            end_date=_subscription_end_date_from_plan(subscription_plan),
        )

        service = PesapalService()
        result = service.initialize_payment(payment)

        if result["success"]:
            payment.provider_order_id = result["order_tracking_id"]
            payment.metadata = {"user_subscription_id": user_subscription.id}
            payment.save(update_fields=["provider_order_id", "metadata"])

            log_event(
                action="created",
                resource="payment",
                resource_id=str(payment.id),
                actor=request.user,
                request=request,
                details=(
                    f"Pesapal one-time subscription checkout initiated: "
                    f"{payment.amount} {payment.currency} | plan={subscription_plan.name}"
                ),
            )

            return Response(
                {
                    "payment_id": str(payment.id),
                    "redirect_url": result["redirect_url"],
                    "order_tracking_id": result["order_tracking_id"],
                    "user_subscription_id": user_subscription.id,
                },
                status=status.HTTP_201_CREATED,
            )

        payment.status = "failed"
        payment.save(update_fields=["status"])
        user_subscription.delete()
        return Response(
            {"error": result.get("message", "Pesapal order submission failed")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------------------------------------------------------
    @extend_schema(
        summary="Check Pesapal payment status",
        description="Polls Pesapal for the latest transaction status and updates the local Payment record.",
        responses={200: PesapalOrderStatusSerializer},
    )
    @action(detail=True, methods=["get"], url_path="status")
    def payment_status(self, request, pk=None):
        payment = self.get_queryset().filter(id=pk).first()
        if not payment:
            return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

        if payment.status in ["completed", "failed", "cancelled"]:
            return Response(
                {
                    "order_tracking_id": payment.provider_order_id,
                    "status": payment.status.upper(),
                    "payment_method": "pesapal",
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "confirmation_code": payment.provider_payment_id or "",
                    "message": f"Payment already {payment.status}",
                }
            )

        service = PesapalService()
        result = service.verify_payment(payment.provider_order_id)
        _sync_payment_from_pesapal_verify(payment, result, request=request)
        payment.refresh_from_db()

        return Response(
            {
                "order_tracking_id": payment.provider_order_id,
                "status": result.get("status", payment.status.upper()),
                "payment_method": result.get("payment_method", ""),
                "amount": result.get("amount") or float(payment.amount),
                "currency": result.get("currency") or payment.currency,
                "confirmation_code": result.get("confirmation_code", ""),
                "message": result.get("message", ""),
            }
        )

    # ------------------------------------------------------------------
    @extend_schema(
        summary="Cancel a Pesapal order",
        description="Cancels a pending Pesapal order. Cannot cancel completed transactions.",
        responses={200: OpenApiResponse(description="{ success, message }")},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        payment = self.get_queryset().filter(id=pk).first()
        if not payment:
            return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == "completed":
            return Response(
                {"error": "Completed payments cannot be cancelled. Use refund instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = PesapalService()
        result = service.cancel_order(payment.provider_order_id)

        if result["success"]:
            payment.status = "cancelled"
            payment.save(update_fields=["status"])
            _release_paused_subscription_for_failed_recurring(payment)
            log_event(
                action="updated",
                resource="payment",
                resource_id=str(payment.id),
                actor=request.user,
                request=request,
                details=f"Pesapal payment cancelled: {payment.provider_order_id}",
            )

        return Response(result, status=status.HTTP_200_OK if result["success"] else status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    @extend_schema(
        summary="Refund a Pesapal payment",
        description="Requests a refund for a completed Pesapal transaction.",
        responses={200: OpenApiResponse(description="{ success, message }")},
    )
    @action(detail=True, methods=["post"], url_path="refund")
    def refund(self, request, pk=None):
        payment = self.get_queryset().filter(id=pk).first()
        if not payment:
            return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

        if payment.status != "completed":
            return Response(
                {"error": "Only completed payments can be refunded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        remarks = request.data.get("remarks", "")
        service = PesapalService()
        result = service.refund_payment(
            payment.provider_order_id, float(payment.amount), remarks
        )

        if result["success"]:
            payment.status = "cancelled"  # treat refunded as cancelled locally
            payment.save(update_fields=["status"])
            log_event(
                action="updated",
                resource="payment",
                resource_id=str(payment.id),
                actor=request.user,
                request=request,
                details=f"Pesapal refund requested: {payment.amount} {payment.currency}",
            )

        return Response(result, status=status.HTTP_200_OK if result["success"] else status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# Recurring payments (subscriptions)
# ─────────────────────────────────────────────────────────────────────────────


@extend_schema(tags=["Payments - Pesapal"])
class PesapalRecurringViewSet(viewsets.GenericViewSet):
    """
    Handles Pesapal recurring payments tied to UserSubscriptions.
    The first payment requires the user to go through the redirect_url.
    Subsequent charges are handled by Pesapal automatically via IPN.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PesapalRecurringInitiateSerializer

    @extend_schema(
        summary="Initiate recurring Pesapal payment",
        description=(
            "Creates a Payment + UserSubscription and submits a recurring order to Pesapal. "
            "The user must complete the first payment at the redirect_url to authorise "
            "all future recurring charges."
        ),
        request=PesapalRecurringInitiateSerializer,
        responses={
            201: OpenApiResponse(
                description="{ payment_id, redirect_url, order_tracking_id, subscription_id }"
            ),
        },
    )
    @action(detail=False, methods=["post"], url_path="initiate")
    def initiate(self, request):
        serializer = PesapalRecurringInitiateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        _reconcile_stale_subscription_checkouts_for_user(request.user)
        if _user_has_blocking_active_or_paused_subscription(request.user):
            return Response(
                {'error': 'An active subscription already exists for this user.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subscription_plan = serializer.validated_data["subscription_id"]  # resolved to Subscription object
        currency = serializer.validated_data.get("currency", "UGX")

        # Create the Payment record
        payment = Payment.objects.create(
            user=request.user,
            amount=subscription_plan.price,
            currency=currency,
            payment_method="pesapal",
            description=f"{subscription_plan.name} subscription",
        )

        # Create a pre-activation UserSubscription; becomes active after verified completion.
        user_subscription = UserSubscription.objects.create(
            user=request.user,
            subscription=subscription_plan,
            status=UserSubscription.Status.PAUSED,
            price=subscription_plan.price,
            currency=currency,
            end_date=_subscription_end_date_from_plan(subscription_plan),
        )

        service = PesapalService()
        result = service.initialize_recurring_payment(payment, subscription_plan)

        if result["success"]:
            payment.provider_order_id = result["order_tracking_id"]
            payment.metadata = {"user_subscription_id": user_subscription.id}
            payment.save(update_fields=["provider_order_id", "metadata"])

            log_event(
                action="created",
                resource="payment",
                resource_id=str(payment.id),
                actor=request.user,
                request=request,
                details=(
                    f"Pesapal recurring payment initiated: "
                    f"{payment.amount} {payment.currency} | plan={subscription_plan.name}"
                ),
            )

            return Response(
                {
                    "payment_id": str(payment.id),
                    "redirect_url": result["redirect_url"],
                    "order_tracking_id": result["order_tracking_id"],
                    "subscription_id": user_subscription.id,
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            payment.status = "failed"
            payment.save(update_fields=["status"])
            user_subscription.delete()
            return Response(
                {"error": result.get("message", "Failed to initiate recurring payment")},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        summary="Cancel a recurring Pesapal subscription",
        description="Cancels the recurring order on Pesapal and marks the local UserSubscription as cancelled.",
        responses={200: OpenApiResponse(description="{ success, message }")},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        try:
            user_subscription = UserSubscription.objects.get(
                id=pk, user=request.user
            )
        except UserSubscription.DoesNotExist:
            return Response({"error": "Subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        # Find the associated payment
        payment = (
            Payment.objects.filter(
                user=request.user,
                payment_method="pesapal",
                metadata__user_subscription_id=user_subscription.id,
            )
            .order_by("-created_at")
            .first()
        )

        pesapal_result = {"success": True, "message": "No active Pesapal order found"}

        if payment and payment.provider_order_id:
            service = PesapalService()
            pesapal_result = service.cancel_order(payment.provider_order_id)

        # Always cancel locally regardless of Pesapal response
        user_subscription.status = "cancelled"
        user_subscription.cancelled_at = timezone.now()
        user_subscription.auto_renew = False
        user_subscription.save()

        log_event(
            action="updated",
            resource="user_subscription",
            resource_id=str(user_subscription.id),
            actor=request.user,
            request=request,
            details=f"Pesapal recurring subscription cancelled: {user_subscription.subscription.name}",
        )

        return Response(pesapal_result)


# ─────────────────────────────────────────────────────────────────────────────
# Webhook (IPN) — no auth required, Pesapal sends GET
# ─────────────────────────────────────────────────────────────────────────────


@extend_schema(tags=["Payments - Pesapal"])
class PesapalWebhookView(APIView):
    """
    Receives Pesapal IPN notifications (server-to-server GET requests).
    No authentication — Pesapal doesn't send auth headers.
    We verify the transaction ourselves by calling GetTransactionStatus.
    """

    permission_classes = [AllowAny]
    
    @staticmethod
    def _activate_user_subscription(user_subscription):
        now = timezone.now()
        user_subscription.status = UserSubscription.Status.ACTIVE

        # Phase 1: plan-derived paid duration.
        duration_days = getattr(user_subscription.subscription, "duration_days", 180)
        if (not user_subscription.end_date) or user_subscription.end_date <= now:
            user_subscription.end_date = now + timedelta(days=duration_days)
            user_subscription.save(update_fields=["status", "end_date"])
            return

        user_subscription.save(update_fields=["status"])

    @extend_schema(
        summary="Pesapal IPN webhook",
        description=(
            "Pesapal calls this endpoint when payment status changes. "
            "This is a GET request with query params: "
            "orderTrackingId, orderMerchantReference, orderNotificationType."
        ),
        parameters=[
            OpenApiParameter("OrderTrackingId", str, OpenApiParameter.QUERY),
            OpenApiParameter("OrderMerchantReference", str, OpenApiParameter.QUERY),
            OpenApiParameter("OrderNotificationType", str, OpenApiParameter.QUERY),
        ],
        responses={
            200: OpenApiResponse(
                description=(
                    "{ orderNotificationType, orderTrackingId, orderMerchantReference, status }"
                )
            ),
        },
    )
    def get(self, request):
        service = PesapalService()
        result = service.handle_webhook(request)

        q_ntype = (
            pesapal_get_request_query(
                request,
                "OrderNotificationType",
                "orderNotificationType",
                "order_notification_type",
            )
            or ""
        )
        q_track = (
            pesapal_get_request_query(
                request,
                "OrderTrackingId",
                "orderTrackingId",
                "order_tracking_id",
            )
            or ""
        )
        q_mref = (
            pesapal_get_request_query(
                request,
                "OrderMerchantReference",
                "orderMerchantReference",
                "order_merchant_reference",
            )
            or ""
        )

        def ipn_ack(http_status, ack_status, extra=None):
            body = {
                "orderNotificationType": result.get("notification_type") or q_ntype or "IPNCHANGE",
                "orderTrackingId": result.get("order_tracking_id") or q_track,
                "orderMerchantReference": result.get("merchant_reference") or q_mref,
                "status": ack_status,
            }
            if extra:
                body.update(extra)
            return Response(body, status=http_status)

        if not result["success"]:
            logger.warning("Pesapal IPN: failed to process — %s", result.get("message"))
            return ipn_ack(
                status.HTTP_200_OK,
                "ERROR",
                {"message": result.get("message", "")},
            )

        merchant_reference = result.get("merchant_reference")  # = payment.id (UUID)
        order_tracking_id = result.get("order_tracking_id")
        pesapal_status = result.get("status", "").upper()

        # Look up the Payment by our payment.id (merchant reference)
        try:
            payment = Payment.objects.get(id=merchant_reference, payment_method="pesapal")
        except (Payment.DoesNotExist, Exception):
            # Fallback: look up by provider_order_id (tracking ID)
            payment = Payment.objects.filter(provider_order_id=order_tracking_id).first()

        if not payment:
            logger.error("Pesapal IPN: no payment found for ref=%s", merchant_reference)
            return ipn_ack(status.HTTP_200_OK, "ACCEPTED")

        if pesapal_status == "COMPLETED" and payment.status != "completed":
            payment.provider_payment_id = result.get("confirmation_code", "") or ""
            payment.mark_completed()  # also handles enrollment

            # If this is a recurring payment, activate the UserSubscription
            subscription_id = payment.metadata.get("user_subscription_id")
            if subscription_id:
                try:
                    us = UserSubscription.objects.get(id=subscription_id)
                    self._activate_user_subscription(us)
                except UserSubscription.DoesNotExist:
                    pass

            log_event(
                action="updated",
                resource="payment",
                resource_id=str(payment.id),
                actor=None,
                request=request,
                details=f"Pesapal IPN: payment completed — {payment.amount} {payment.currency}",
            )

        elif pesapal_status == "FAILED" and payment.status == "pending":
            payment.status = "failed"
            payment.save(update_fields=["status"])
            _release_paused_subscription_for_failed_recurring(payment)

        elif pesapal_status == "INVALID":
            payment.status = "cancelled"
            payment.save(update_fields=["status"])
            _release_paused_subscription_for_failed_recurring(payment)

        elif pesapal_status == "REVERSED" and payment.status == "pending":
            payment.status = "cancelled"
            payment.save(update_fields=["status"])
            _release_paused_subscription_for_failed_recurring(payment)

        return ipn_ack(status.HTTP_200_OK, "ACCEPTED")


# ─────────────────────────────────────────────────────────────────────────────
# Callback (browser redirect back from Pesapal)
# ─────────────────────────────────────────────────────────────────────────────


@extend_schema(tags=["Payments - Pesapal"])
class PesapalCallbackView(APIView):
    """
    Pesapal redirects the user's browser back here after they attempt payment.
    This is NOT the IPN — don't trust it for payment confirmation.
    Just verify the status and send the user to the right React page.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Pesapal payment callback",
        description=(
            "Browser redirect from Pesapal after payment attempt. "
            "Verifies status and redirects user to the appropriate React page."
        ),
        parameters=[
            OpenApiParameter("OrderTrackingId", str, OpenApiParameter.QUERY),
            OpenApiParameter("OrderMerchantReference", str, OpenApiParameter.QUERY),
        ],
        responses={302: OpenApiResponse(description="Redirects to React frontend")},
    )
    def get(self, request):
        from django.shortcuts import redirect

        order_tracking_id = (
            pesapal_get_request_query(
                request,
                "OrderTrackingId",
                "orderTrackingId",
                "order_tracking_id",
            )
            or ""
        )
        merchant_reference = (
            pesapal_get_request_query(
                request,
                "OrderMerchantReference",
                "orderMerchantReference",
                "order_merchant_reference",
            )
            or ""
        )

        frontend_base = _pesapal_frontend_redirect_base()

        service = PesapalService()
        result = service.verify_payment(order_tracking_id)
        pesapal_status = result.get("status", "").upper() if result["success"] else "FAILED"

        if pesapal_status == "COMPLETED":
            return redirect(
                f"{frontend_base}/payments/success"
                f"?tracking_id={order_tracking_id}&ref={merchant_reference}"
            )
        elif pesapal_status in ("FAILED", "REVERSED"):
            return redirect(
                f"{frontend_base}/payments/failed"
                f"?tracking_id={order_tracking_id}&ref={merchant_reference}"
            )
        else:
            return redirect(
                f"{frontend_base}/payments/pending"
                f"?tracking_id={order_tracking_id}&ref={merchant_reference}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# IPN admin actions (staff only)
# ─────────────────────────────────────────────────────────────────────────────


@extend_schema(tags=["Payments - Pesapal Admin"])
class PesapalIPNViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lists registered Pesapal IPN URLs.
    Staff / admin only.
    """

    serializer_class = PesapalIPNSerializer
    queryset = PesapalIPN.objects.all()

    def get_permissions(self):
        from rest_framework.permissions import IsAdminUser
        return [IsAdminUser()]

    @extend_schema(
        summary="Register IPN URL",
        description=(
            "Registers the PESAPAL_IPN_URL from settings with Pesapal and stores the "
            "returned ipn_id. Only needs to be called once per environment."
        ),
        responses={201: PesapalIPNSerializer},
    )
    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        service = PesapalService()
        result = service.register_ipn()

        if not result["success"]:
            return Response(
                {"error": result.get("message")}, status=status.HTTP_400_BAD_REQUEST
            )

        from django.conf import settings as django_settings

        env = getattr(django_settings, "PESAPAL_ENV", "demo")
        ipn_url = getattr(django_settings, "PESAPAL_IPN_URL", "")

        ipn_record, created = PesapalIPN.objects.update_or_create(
            ipn_id=result["ipn_id"],
            defaults={
                "url": ipn_url,
                "environment": env,
                "is_active": True,
            },
        )

        return Response(
            PesapalIPNSerializer(ipn_record).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )