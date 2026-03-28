from django.shortcuts import render
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.http import HttpResponse
import uuid
import csv

from .services.flutterwave_service import FlutterwaveService

from .models import (
    Invoice, InvoiceItem, Transaction, PaymentMethod,
    Subscription, UserSubscription, Payment, PaymentWebhook
)
from .serializers import (
    InvoiceSerializer, InvoiceCreateSerializer,
    InvoiceItemSerializer, TransactionSerializer,
    PaymentMethodSerializer, PaymentMethodCreateSerializer,
    SubscriptionSerializer, UserSubscriptionSerializer, UserSubscriptionCreateSerializer,
    SubscriptionStatusSerializer,
    PaymentSerializer, CreatePaymentSerializer, PaymentConfirmationSerializer,
    PaymentWebhookSerializer, PaymentStatusSerializer
)
from .permissions import user_has_active_subscription, get_best_active_subscription


@extend_schema(
    tags=['Payments - Subscriptions'],
    summary='Get my subscription status',
    description='Returns the current user\'s subscription status for content access.',
    responses={
        200: SubscriptionStatusSerializer,
    },
)
class SubscriptionMeView(APIView):
    """GET /api/v1/payments/subscription/me/ - current user's subscription status."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        has_active = user_has_active_subscription(user)
        us = get_best_active_subscription(user) if has_active else None

        if not us:
            data = {
                'has_active_subscription': False,
                'status': 'none',
                'is_trial': False,
                'start_date': None,
                'end_date': None,
                'days_remaining': 0,
                'plan': None,
            }
        else:
            now = timezone.now()
            days_remaining = None
            if us.end_date:
                delta = us.end_date - now
                days_remaining = max(0, delta.days)

            plan = us.subscription
            data = {
                'has_active_subscription': True,
                'status': us.status,
                'is_trial': us.is_trial,
                'start_date': us.start_date,
                'end_date': us.end_date,
                'days_remaining': days_remaining,
                'plan': {
                    'id': plan.id,
                    'name': plan.name,
                    'price': str(plan.price),
                    'currency': plan.currency,
                    'billing_cycle': plan.billing_cycle,
                },
            }

        return Response(data)


@extend_schema(
    tags=['Payments - Invoices'],
    description='Manage billing invoices and payments',
)
class InvoiceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing invoices."""
    queryset = Invoice.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceCreateSerializer
        return InvoiceSerializer
    
    def get_queryset(self):
        user = self.request.user
        # Check user role - adjust based on your User model
        if hasattr(user, 'role') and user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return Invoice.objects.all()
        return Invoice.objects.filter(user=user)
    
    @extend_schema(
        summary='List invoices',
        description='Returns invoices (finance team sees all, users see their own)',
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter by status'),
            OpenApiParameter(name='user', type=int, description='Filter by user ID (finance only)'),
            OpenApiParameter(name='from_date', type=str, description='Filter from date (YYYY-MM-DD)'),
            OpenApiParameter(name='to_date', type=str, description='Filter to date (YYYY-MM-DD)'),
        ],
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        user_filter = request.query_params.get('user')
        if user_filter and hasattr(request.user, 'role') and request.user.role in ['finance', 'tasc_admin']:
            queryset = queryset.filter(user_id=user_filter)

        from_date = request.query_params.get('from_date')
        if from_date:
            queryset = queryset.filter(created_at__date__gte=from_date)

        to_date = request.query_params.get('to_date')
        if to_date:
            queryset = queryset.filter(created_at__date__lte=to_date)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Create invoice',
        description='Create a new invoice (finance team only)',
        request=InvoiceCreateSerializer,
        responses={201: InvoiceSerializer},
    )
    def create(self, request, *args, **kwargs):
        # Check permissions
        if not hasattr(request.user, 'role') or request.user.role not in ['finance', 'tasc_admin', 'lms_manager']:
            return Response(
                {'error': 'Only finance team members can create invoices'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @extend_schema(
        summary='Get invoice details',
        description='Returns detailed invoice information including line items',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        summary='Update invoice',
        description='Update invoice status or details (finance team only)',
        request=InvoiceSerializer,
    )
    def update(self, request, *args, **kwargs):
        # Check permissions
        if not hasattr(request.user, 'role') or request.user.role not in ['finance', 'tasc_admin']:
            return Response(
                {'error': 'Only finance team members can update invoices'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        
        return Response(serializer.data)
    
    @extend_schema(
        summary='Pay invoice',
        description='Mark invoice as paid and create transaction record',
        responses={
            200: InvoiceSerializer,
            400: OpenApiResponse(description='Invoice already paid or invalid'),
        },
    )
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        invoice = self.get_object()
        
        if invoice.status != 'pending':
            return Response(
                {'error': 'Invoice can only be paid if status is pending'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update invoice status
        invoice.status = 'paid'
        invoice.paid_at = timezone.now()
        invoice.paid_amount = invoice.total_amount
        invoice.save()
        # US-027 audit: record invoice payment event after successful status update
        from apps.audit.services import log_event
        log_event(
            action="updated",
            resource="invoice",
            resource_id=str(invoice.id),
            actor=request.user,
            request=request,
            details=f"Invoice paid: {invoice.invoice_number} | amount={invoice.total_amount}",
        )
        
        # Create transaction record
        transaction = Transaction.objects.create(
            invoice=invoice,
            user=invoice.user,
            organization=invoice.organization,
            amount=invoice.total_amount,
            currency=invoice.currency,
            status='completed',
            payment_method='other',
            completed_at=timezone.now()
        )
        
        serializer = InvoiceSerializer(invoice)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Download invoice PDF',
        description='Get URL to download invoice PDF',
        responses={200: OpenApiResponse(description='PDF download URL')},
    )
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        invoice = self.get_object()
        
        if not invoice.invoice_pdf_url:
            # Generate PDF logic would go here
            invoice.invoice_pdf_url = f"/media/invoices/{invoice.invoice_number}.pdf"
            invoice.save()
        
        return Response({
            'pdf_url': invoice.invoice_pdf_url,
            'invoice_number': invoice.invoice_number
        })

    @extend_schema(
        summary='Download invoice PDF',
        description='Get invoice data for PDF generation',
    )
    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        """GET /api/v1/payments/invoices/{id}/download-pdf/"""
        invoice = self.get_object()
        # Option 1: Return invoice data for frontend CSS-based printing
        # Option 2: Use WeasyPrint (if installed)
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)
        # TODO: For real PDF, add weasyprint to requirements and render template

    @extend_schema(
        summary='Email receipt',
        description='Email invoice receipt to the customer',
    )
    @action(detail=True, methods=['post'], url_path='email-receipt')
    def email_receipt(self, request, pk=None):
        """POST /api/v1/payments/invoices/{id}/email-receipt/"""
        invoice = self.get_object()
        # TODO: Send email via SendGrid with invoice data
        return Response({'status': 'Receipt email queued'})

    @extend_schema(
        summary='Invoice statistics (superadmin)',
        description='Returns aggregate invoice stats for admin dashboards',
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Admin-level invoice statistics."""
        from django.db.models import Sum
        all_invoices = Invoice.objects.all()
        now = timezone.now()

        total = all_invoices.count()
        paid = all_invoices.filter(status='paid').count()
        pending = all_invoices.filter(status='pending').count()
        overdue = all_invoices.filter(status='pending', due_date__lt=now).count()
        total_revenue = all_invoices.filter(
            status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        return Response({
            'total': total,
            'paid': paid,
            'pending': pending,
            'overdue': overdue,
            'total_revenue': str(total_revenue),
        })


@extend_schema(
    tags=['Payments - Transactions'],
    description='Manage payment transactions',
)
class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing transactions."""
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return Transaction.objects.all()
        return Transaction.objects.filter(user=user)
    
    @extend_schema(
        summary='List transactions',
        description='Returns all payment transactions (finance team sees all, users see their own)',
        parameters=[
            OpenApiParameter(name='invoice', type=int, description='Filter by invoice ID'),
            OpenApiParameter(name='status', type=str, description='Filter by status'),
            OpenApiParameter(name='from_date', type=str, description='Filter from date (YYYY-MM-DD)'),
            OpenApiParameter(name='to_date', type=str, description='Filter to date (YYYY-MM-DD)'),
        ],
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Apply filters
        invoice_id = request.query_params.get('invoice')
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        from_date = request.query_params.get('from_date')
        if from_date:
            queryset = queryset.filter(created_at__date__gte=from_date)
        
        to_date = request.query_params.get('to_date')
        if to_date:
            queryset = queryset.filter(created_at__date__lte=to_date)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Get transaction details',
        description='Returns detailed transaction information',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get transaction receipt',
        description='Get receipt details for a transaction',
    )
    @action(detail=True, methods=['get'])
    def receipt(self, request, pk=None):
        transaction = self.get_object()
        
        return Response({
            'transaction_id': transaction.transaction_id,
            'amount': transaction.amount,
            'currency': transaction.currency,
            'status': transaction.status,
            'created_at': transaction.created_at,
            'payment_method': transaction.payment_method,
            'invoice': transaction.invoice.invoice_number if transaction.invoice else None,
            'receipt_url': f"/media/receipts/{transaction.transaction_id}.pdf"
        })

    @extend_schema(
        summary='Export transactions to CSV',
        description='Download all visible transactions as a CSV file',
    )
    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """GET /api/v1/payments/transactions/export-csv/"""
        qs = self.get_queryset()
        
        # Also apply any query parameter filters before returning the CSV
        invoice_id = request.query_params.get('invoice')
        if invoice_id:
            qs = qs.filter(invoice_id=invoice_id)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        
        from_date = request.query_params.get('from_date')
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        
        to_date = request.query_params.get('to_date')
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)
            
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Transaction ID', 'Amount', 'Currency', 'Status',
            'Payment Method', 'Created At', 'Completed At',
        ])
        for t in qs:
            writer.writerow([
                t.id, t.transaction_id, t.amount, t.currency, t.status,
                t.payment_method, t.created_at, t.completed_at,
            ])
        return response


@extend_schema(
    tags=['Payments - Payment Methods'],
    description='Manage saved payment methods',
)
class PaymentMethodViewSet(viewsets.ModelViewSet):
    """ViewSet for managing payment methods."""
    queryset = PaymentMethod.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentMethodCreateSerializer
        return PaymentMethodSerializer
    
    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user, is_active=True)
    
    @extend_schema(
        summary='List payment methods',
        description='Returns all saved payment methods for the authenticated user',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Add payment method',
        description='Add a new payment method',
        request=PaymentMethodCreateSerializer,
        responses={201: PaymentMethodSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set the user
        serializer.save(user=request.user)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary='Delete payment method',
        description='Delete a saved payment method (soft delete by setting inactive)',
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.is_default = False
        instance.save()
        
        # If this was the default, set another as default
        if instance.is_default:
            next_method = PaymentMethod.objects.filter(
                user=request.user, is_active=True
            ).first()
            if next_method:
                next_method.is_default = True
                next_method.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @extend_schema(
        summary='Set default payment method',
        description='Set a payment method as the default for future payments',
        responses={200: PaymentMethodSerializer},
    )
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        payment_method = self.get_object()
        
        # Remove default from other methods
        PaymentMethod.objects.filter(user=request.user, is_default=True).update(is_default=False)
        
        # Set this as default
        payment_method.is_default = True
        payment_method.save()
        
        serializer = self.get_serializer(payment_method)
        return Response(serializer.data)


@extend_schema(
    tags=['Payments - Subscriptions'],
    description='Manage subscription plans',
)
class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing subscription plans."""
    queryset = Subscription.objects.filter(status='active')
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary='List subscription plans',
        description='Returns all active subscription plans',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get subscription plan details',
        description='Returns detailed information about a subscription plan',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


@extend_schema(
    tags=['Payments - User Subscriptions'],
    description='Manage user subscription enrollments',
)
class UserSubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing user subscriptions."""
    queryset = UserSubscription.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserSubscriptionCreateSerializer
        return UserSubscriptionSerializer
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return UserSubscription.objects.all()
        return UserSubscription.objects.filter(user=user)
    
    @extend_schema(
        summary='List user subscriptions',
        description='Returns subscriptions (finance team sees all, users see their own)',
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter by status'),
            OpenApiParameter(name='user', type=int, description='Filter by user ID (finance only)'),
        ],
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        user_filter = request.query_params.get('user')
        if user_filter and hasattr(request.user, 'role') and request.user.role in ['finance', 'tasc_admin']:
            queryset = queryset.filter(user_id=user_filter)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Subscribe to plan',
        description='Subscribe to a subscription plan',
        request=UserSubscriptionCreateSerializer,
        responses={201: UserSubscriptionSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        # Set the user
        is_trial = serializer.validated_data.get('is_trial', False)
        serializer.save(user=request.user)
        
        # Configure active access window for Phase 1 gating.
        subscription = serializer.instance
        subscription_plan = subscription.subscription

        if is_trial:
            end_date = timezone.now() + timedelta(days=7)
            subscription.trial_end_date = end_date
        else:
            end_date = timezone.now() + timedelta(days=180)  # biannual paid access
            subscription.trial_end_date = None

        subscription.status = UserSubscription.Status.ACTIVE
        subscription.end_date = end_date
        subscription.save()

        # Keep invoice workflow for paid subscriptions.
        if not is_trial:
            invoice = Invoice.objects.create(
                user=request.user,
                invoice_type='subscription',
                customer_name=request.user.get_full_name() or request.user.email,
                customer_email=request.user.email,
                subtotal=subscription_plan.price,
                total_amount=subscription_plan.price,
                currency=subscription_plan.currency or 'UGX',
                status='pending',
                due_date=timezone.now() + timedelta(days=7)
            )

            InvoiceItem.objects.create(
                invoice=invoice,
                item_type='subscription',
                item_id=subscription_plan.id,
                description=f"{subscription_plan.name} - biannual subscription",
                quantity=1,
                unit_price=subscription_plan.price
            )

        return Response(UserSubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary='Cancel subscription',
        description='Cancel an active subscription',
        responses={200: UserSubscriptionSerializer},
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        subscription = self.get_object()
        
        if subscription.status != 'active':
            return Response(
                {'error': 'Only active subscriptions can be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        subscription.status = 'cancelled'
        subscription.auto_renew = False
        subscription.cancelled_at = timezone.now()
        subscription.save()
        
        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Renew subscription',
        description='Renew a subscription for another billing period',
        responses={200: UserSubscriptionSerializer},
    )
    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        subscription = self.get_object()
        
        if subscription.status not in ['cancelled', 'expired']:
            return Response(
                {'error': 'Only cancelled or expired subscriptions can be renewed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Reactivate subscription
        subscription.status = 'active'
        subscription.cancelled_at = None
        
        # Extend end date using the paid Phase 1 duration (6 months).
        subscription.end_date = timezone.now() + timedelta(days=180)
        
        subscription.save()
        
        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Pause subscription',
        description='Pause an active subscription temporarily',
        responses={200: UserSubscriptionSerializer},
    )
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        subscription = self.get_object()
        
        if subscription.status != 'active':
            return Response(
                {'error': 'Only active subscriptions can be paused'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        subscription.status = 'paused'
        subscription.save()
        
        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Resume subscription',
        description='Resume a paused subscription',
        responses={200: UserSubscriptionSerializer},
    )
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        subscription = self.get_object()
        
        if subscription.status != 'paused':
            return Response(
                {'error': 'Only paused subscriptions can be resumed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        subscription.status = 'active'
        subscription.save()
        
        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data)


@extend_schema(
    tags=['Payments - Processing'],
    description='Process payments with Flutterwave',
)
class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for processing payments with Flutterwave."""
    queryset = Payment.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return Payment.objects.all()
        return Payment.objects.filter(user=user)
    
    @extend_schema(
        summary='Create payment',
        description='Create a new payment and initialize with Flutterwave',
        request=CreatePaymentSerializer,
        responses={201: OpenApiResponse(description='Payment link generated')},
    )
    def create(self, request):
        """Create a new payment with Flutterwave"""
        serializer = CreatePaymentSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        # Create payment record
        payment = Payment.objects.create(
            user=request.user,
            course=data.get('course'),
            amount=data['amount'],
            currency=data.get('currency', 'USD'),
            payment_method='flutterwave',
            description=data.get('description', f"Payment for course")
        )
        
        # Initialize Flutterwave service
        service = FlutterwaveService()
        result = service.initialize_payment(payment)
        
        if result['success']:
            # US-027 audit: record payment initiation only after provider initialization succeeds
            from apps.audit.services import log_event
            log_event(
                action="created",
                resource="payment",
                resource_id=str(payment.id),
                actor=request.user,
                request=request,
                details=f"Payment initiated: amount={payment.amount} {payment.currency} | course={payment.course_id}",
            )
            return Response({
                'payment_id': str(payment.id),
                'payment_link': result['payment_link'],
                'transaction_id': result['transaction_id'],
                'reference': result['reference']
            }, status=status.HTTP_201_CREATED)
        else:
            payment.status = 'failed'
            payment.save()
            return Response({
                'error': result.get('message', 'Payment initialization failed'),
                'details': result.get('data')
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary='Verify payment',
        description='Verify a Flutterwave payment',
        parameters=[
            OpenApiParameter(name='transaction_id', type=str, description='Flutterwave transaction ID'),
        ],
        responses={200: OpenApiResponse(description='Payment verification result')},
    )
    @action(detail=False, methods=['get'], url_path='verify')
    def verify_payment(self, request):
        """Verify Flutterwave payment"""
        transaction_id = request.query_params.get('transaction_id')
        
        if not transaction_id:
            return Response({
                'error': 'Transaction ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        service = FlutterwaveService()
        result = service.verify_payment(transaction_id)
        
        if result['success']:
            # Find and update payment
            try:
                payment = Payment.objects.get(id=result['reference'])
                
                if result['status'] == 'successful':
                    payment.mark_completed()
                    # US-027 audit: record successful payment completion after local status update
                    from apps.audit.services import log_event
                    log_event(
                        action="updated",
                        resource="payment",
                        resource_id=str(payment.id),
                        actor=request.user if request.user.is_authenticated else None,
                        request=request,
                        details=f"Payment completed: amount={payment.amount} {payment.currency}",
                    )
                    
                    return Response({
                        'success': True,
                        'status': 'completed',
                        'payment': PaymentSerializer(payment).data,
                        'verification': result
                    })
                else:
                    return Response({
                        'success': False,
                        'status': result['status'],
                        'payment_id': result['reference'],
                        'verification': result
                    })
                    
            except Payment.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Payment not found',
                    'verification': result
                })
        else:
            return Response({
                'success': False,
                'error': result.get('message', 'Verification failed'),
                'details': result.get('data')
            }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary='Revenue statistics (superadmin)',
        description='Returns monthly revenue breakdown and growth rate for admin dashboards',
    )
    @action(detail=False, methods=['get'], url_path='revenue-stats')
    def revenue_stats(self, request):
        """Admin-level revenue statistics."""
        from django.db.models import Sum
        from django.db.models.functions import TruncMonth

        months = int(request.query_params.get('months', 12))
        start_date = timezone.now() - timedelta(days=months * 30)

        monthly = (
            Transaction.objects.filter(
                status='completed',
                created_at__gte=start_date,
            )
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(revenue=Sum('amount'))
            .order_by('month')
        )

        monthly_data = []
        prev_revenue = None
        for m in monthly:
            rev = float(m['revenue'] or 0)
            growth = None
            if prev_revenue is not None and prev_revenue > 0:
                growth = round(((rev - prev_revenue) / prev_revenue) * 100, 1)
            monthly_data.append({
                'month': m['month'].strftime('%b %Y') if m['month'] else None,
                'revenue': str(m['revenue'] or 0),
                'growth_percent': growth,
            })
            prev_revenue = rev

        total_revenue = Transaction.objects.filter(
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or 0

        return Response({
            'total_revenue': str(total_revenue),
            'monthly': monthly_data,
        })
    
    @extend_schema(
        summary='Get banks',
        description='Get list of banks for a country (Flutterwave)',
        parameters=[
            OpenApiParameter(name='country', type=str, description='Country code (NG, GH, KE, etc.)'),
        ],
        responses={200: OpenApiResponse(description='List of banks')},
    )
    @action(detail=False, methods=['get'], url_path='banks')
    def get_banks(self, request):
        """Get list of banks for a country"""
        country = request.query_params.get('country', 'NG')
        
        service = FlutterwaveService()
        result = service.get_banks(country)
        
        if result['success']:
            return Response(result['banks'])
        else:
            return Response({
                'error': result.get('message', 'Failed to fetch banks')
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary='Get exchange rates',
        description='Get exchange rates (Flutterwave)',
        parameters=[
            OpenApiParameter(name='from', type=str, description='From currency'),
            OpenApiParameter(name='to', type=str, description='To currency'),
            OpenApiParameter(name='amount', type=float, description='Amount to convert'),
        ],
        responses={200: OpenApiResponse(description='Exchange rate information')},
    )
    @action(detail=False, methods=['get'], url_path='rates')
    def get_rates(self, request):
        """Get exchange rates"""
        from_currency = request.query_params.get('from', 'USD')
        to_currency = request.query_params.get('to', 'NGN')
        amount = request.query_params.get('amount', 1)
        
        service = FlutterwaveService()
        result = service.get_exchange_rates(from_currency, to_currency, amount)
        
        if result['success']:
            return Response(result)
        else:
            return Response({
                'error': result.get('message', 'Failed to fetch rates')
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary='Check payment status',
        description='Check status of a payment',
        responses={200: PaymentStatusSerializer},
    )
    @action(detail=True, methods=['get'], url_path='status')
    def payment_status(self, request, pk=None):
        """Check payment status"""
        payment = self.get_object()
        
        # If payment completed locally, return status
        if payment.status in ['completed', 'failed']:
            return Response({
                'payment_id': str(payment.id),
                'status': payment.status,
                'completed_at': payment.completed_at,
            })
        
        # Check with Flutterwave
        try:
            service = FlutterwaveService()
            result = service.verify_payment(payment.provider_payment_id)
            
            if result['success'] and result['status'] == 'successful':
                payment.mark_completed()
                # US-027 audit: record successful payment completion after local status update
                from apps.audit.services import log_event
                log_event(
                    action="updated",
                    resource="payment",
                    resource_id=str(payment.id),
                    actor=request.user if request.user.is_authenticated else None,
                    request=request,
                    details=f"Payment completed: amount={payment.amount} {payment.currency}",
                )
            
            return Response({
                'payment_id': str(payment.id),
                'status': payment.status,
                'provider_status': result.get('status'),
                'verification': result
            })
                
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )


from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth

@extend_schema(tags=['Payments - Analytics'])
class PaymentAnalyticsViewSet(viewsets.ViewSet):
    """ViewSet for dashboard analytics regarding revenue."""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='revenue')
    def revenue(self, request):
        months = int(request.query_params.get('months', 6))
        start_date = timezone.now() - timedelta(days=months * 30)

        user = request.user
        base_qs = Transaction.objects.filter(
            status='completed',
            created_at__gte=start_date
        )

        # Scope by role
        if user.role == 'lms_manager' and hasattr(user, 'organization') and user.organization:
            base_qs = base_qs.filter(organization=user.organization)

        monthly = base_qs.annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            total=Sum('amount')
        ).order_by('month')

        # Build consistent month list
        labels_map = {}
        for i in range(months - 1, -1, -1):
            d = timezone.now() - timedelta(days=i * 30)
            label = d.strftime('%b %Y')
            labels_map[label] = 0

        for m in monthly:
            if m['month']:
                key = m['month'].strftime('%b %Y')
                if key in labels_map:
                    labels_map[key] = float(m['total'] or 0)

        labels = list(labels_map.keys())
        revenue = list(labels_map.values())
        total_revenue = sum(revenue)

        return Response({
            "labels": labels,
            "revenue": revenue,
            "total_revenue": total_revenue,
        })


@extend_schema(
    tags=['Payments - Webhooks'],
    description='Handle Flutterwave webhooks',
)
class WebhookView(viewsets.GenericViewSet):
    """Handle Flutterwave webhooks"""
    permission_classes = [AllowAny]
    serializer_class = PaymentWebhookSerializer
    
    @extend_schema(
        summary='Flutterwave webhook',
        description='Receive webhooks from Flutterwave',
        request=PaymentWebhookSerializer,
        responses={200: OpenApiResponse(description='Webhook received')},
    )
    @action(detail=False, methods=['post'], url_path='flutterwave')
    def flutterwave_webhook(self, request):
        """Handle Flutterwave webhook"""
        service = FlutterwaveService()
        result = service.handle_webhook(request)
        
        if result['success']:
            return Response({'success': True})
        else:
            return Response(
                {'error': result.get('message', 'Webhook processing failed')},
                status=status.HTTP_400_BAD_REQUEST
            )
