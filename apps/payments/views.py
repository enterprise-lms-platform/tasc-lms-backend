from django.shortcuts import render
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from datetime import timedelta
from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.http import HttpResponse
import uuid
import csv
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncMonth

from .services.flutterwave_service import FlutterwaveService

from .models import (
    Invoice, InvoiceItem, Transaction, PaymentMethod,
    Subscription, UserSubscription, Payment, PaymentWebhook
)
from .serializers import (
    InvoiceSerializer, InvoiceCreateSerializer,
    InvoiceItemSerializer, TransactionSerializer,
    PaymentMethodSerializer, PaymentMethodCreateSerializer,
    SubscriptionSerializer, SubscriptionCreateUpdateSerializer,
    UserSubscriptionSerializer, UserSubscriptionCreateSerializer,
    SubscriptionStatusSerializer,
    PaymentSerializer, CreatePaymentSerializer, PaymentConfirmationSerializer,
    PaymentWebhookSerializer, PaymentStatusSerializer,
    FinanceDashboardOverviewSerializer,
    FinanceAnalyticsOverviewSerializer,
    FinanceAlertsResponseSerializer,
)
from .permissions import user_has_active_subscription, get_best_active_subscription, get_subscription_status, GRACE_PERIOD_DAYS
from apps.accounts.permissions import IsFinanceDashboardUser


def _is_finance_dashboard_user(user):
    return bool(
        user
        and user.is_authenticated
        and (
            getattr(user, 'is_superuser', False)
            or getattr(user, 'is_staff', False)
            or getattr(user, 'role', None) in ['finance', 'tasc_admin', 'lms_manager']
        )
    )


def _can_manage_subscription_plans(user):
    return bool(
        user
        and user.is_authenticated
        and (
            getattr(user, 'is_superuser', False)
            or getattr(user, 'is_staff', False)
            or getattr(user, 'role', None) == 'tasc_admin'
        )
    )


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
        sub_status = get_subscription_status(user)

        if sub_status["has_subscription"]:
            us = sub_status["subscription"]
            now = timezone.now()
            days_remaining = None
            approaching_grace = False
            grace_days_remaining = None
            if us.end_date:
                delta = us.end_date - now
                days_remaining = max(0, delta.days)
                if delta.days < 0:
                    approaching_grace = True
                    grace_days_remaining = GRACE_PERIOD_DAYS + delta.days
                elif delta.days <= GRACE_PERIOD_DAYS:
                    approaching_grace = True
                    grace_days_remaining = GRACE_PERIOD_DAYS

            plan = us.subscription
            data = {
                'has_active_subscription': True,
                'status': us.status,
                'is_trial': us.is_trial,
                'start_date': us.start_date,
                'end_date': us.end_date,
                'days_remaining': days_remaining,
                'in_grace_period': False,
                'grace_days_remaining': grace_days_remaining if approaching_grace else None,
                'approaching_grace_period': approaching_grace,
                'plan': {
                    'id': plan.id,
                    'name': plan.name,
                    'price': str(plan.price),
                    'currency': plan.currency,
                    'billing_cycle': plan.billing_cycle,
                },
            }
        elif sub_status["in_grace_period"]:
            us = sub_status["subscription"]
            plan = us.subscription
            data = {
                'has_active_subscription': False,
                'status': 'grace_period',
                'is_trial': us.is_trial,
                'start_date': us.start_date,
                'end_date': us.end_date,
                'days_remaining': 0,
                'in_grace_period': True,
                'grace_days_remaining': sub_status.get('grace_days_remaining', 0),
                'plan': {
                    'id': plan.id,
                    'name': plan.name,
                    'price': str(plan.price),
                    'currency': plan.currency,
                    'billing_cycle': plan.billing_cycle,
                },
            }
        else:
            data = {
                'has_active_subscription': False,
                'status': 'none',
                'is_trial': False,
                'start_date': None,
                'end_date': None,
                'days_remaining': 0,
                'in_grace_period': False,
                'grace_days_remaining': None,
                'plan': None,
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
        qs = Invoice.objects.select_related('user', 'organization', 'course', 'payment').prefetch_related('items')
        if hasattr(user, 'role') and user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return qs
        return qs.filter(user=user)
    
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
        summary='Retry a failed transaction',
        description='Reset a failed transaction so the user can re-attempt payment',
        responses={200: OpenApiResponse(description='{ message, transaction_id, status }')},
    )
    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        transaction = self.get_object()
        if transaction.user != request.user and not (
            hasattr(request.user, 'role')
            and request.user.role in ['finance', 'tasc_admin', 'lms_manager']
        ):
            raise PermissionDenied("You cannot retry this transaction.")
        if transaction.status not in [Transaction.Status.FAILED, Transaction.Status.CANCELLED]:
            return Response(
                {"error": "Only failed or cancelled transactions can be retried."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if transaction.invoice:
            invoice = transaction.invoice
            if invoice.status == 'paid':
                return Response(
                    {'error': 'Associated invoice is already paid'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            invoice.status = 'pending'
            invoice.save(update_fields=['status'])
        transaction.status = Transaction.Status.PENDING
        transaction.error_message = ''
        transaction.save(update_fields=['status', 'error_message'])
        return Response({
            'message': 'Transaction reset for retry.',
            'transaction_id': transaction.transaction_id,
            'status': transaction.status,
        })

    @extend_schema(
        summary='Download invoice PDF',
        description='Generate and download invoice as PDF',
    )
    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        """GET /api/v1/payments/invoices/{id}/download-pdf/"""
        import weasyprint
        from django.template.loader import render_to_string

        invoice = self.get_object()
        items = invoice.items.all()
        context = {
            'invoice': invoice,
            'invoice_items': items,
        }
        html_string = render_to_string('emails/payments/invoice_pdf.html', context)
        pdf_bytes = weasyprint.HTML(string=html_string).write_pdf()
        filename = f"invoice_{invoice.invoice_number}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @extend_schema(
        summary='Email receipt',
        description='Email invoice receipt to the customer',
    )
    @action(detail=True, methods=['post'], url_path='email-receipt')
    def email_receipt(self, request, pk=None):
        """POST /api/v1/payments/invoices/{id}/email-receipt/"""
        from apps.notifications.services import send_tasc_email
        invoice = self.get_object()

        recipient_email = (
            invoice.user.email if invoice.user else request.data.get('email')
        )
        if not recipient_email:
            return Response({'error': 'No recipient email found.'}, status=status.HTTP_400_BAD_REQUEST)

        context = {
            'invoice_number': invoice.invoice_number,
            'total_amount': str(invoice.total_amount),
            'currency': invoice.currency,
            'status': invoice.status,
            'due_date': invoice.due_date.strftime('%d %b %Y') if invoice.due_date else 'N/A',
            'issued_at': invoice.issued_at.strftime('%d %b %Y') if invoice.issued_at else 'N/A',
            'user_name': invoice.user.get_full_name() if invoice.user else 'Customer',
        }

        send_tasc_email(
            subject=f'Your Invoice #{invoice.invoice_number}',
            to=[recipient_email],
            template='emails/payments/invoice_receipt.html',
            context=context,
        )

        return Response({'status': 'Receipt emailed successfully.'})

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


    @extend_schema(summary='Export invoices as CSV')
    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """GET /api/v1/payments/invoices/export-csv/ — respects status, search filters"""
        import csv as csv_module
        from django.http import HttpResponse
        qs = self.get_queryset()

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = request.query_params.get('search')
        if search:
            from django.db.models import Q as DQ
            qs = qs.filter(DQ(invoice_number__icontains=search) | DQ(user__email__icontains=search))
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="invoices.csv"'
        writer = csv_module.writer(response)
        writer.writerow([
            'ID', 'Invoice Number', 'Customer', 'Amount', 'Currency',
            'Status', 'Due Date', 'Created At',
        ])
        for inv in qs.select_related('user'):
            writer.writerow([
                inv.id,
                inv.invoice_number,
                inv.user.get_full_name() or inv.user.email if inv.user else '',
                inv.total_amount,
                getattr(inv, 'currency', 'USD'),
                inv.status,
                inv.due_date,
                inv.created_at,
            ])
        return response


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
        qs = Transaction.objects.select_related('user', 'organization', 'course', 'invoice')
        if hasattr(user, 'role') and user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return qs
        return qs.filter(user=user)
    
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
        summary='Transaction revenue summary',
        description='Returns total completed revenue — superadmin KPI use',
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        from django.db.models import Sum
        from apps.accounts.rbac import is_tasc_admin, is_admin_like
        if not is_admin_like(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can view revenue summary.")
        total = Transaction.objects.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0
        return Response({'total_revenue': str(total)})

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
        summary='Retry a failed or cancelled transaction',
        description='Reset a failed or cancelled transaction so the user can re-attempt payment',
        responses={200: OpenApiResponse(description='{ message, transaction_id, status }')},
    )
    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        transaction = self.get_object()
        if transaction.user != request.user and not (
            hasattr(request.user, 'role')
            and request.user.role in ['finance', 'tasc_admin', 'lms_manager']
        ):
            raise PermissionDenied("You cannot retry this transaction.")
        if transaction.status not in [Transaction.Status.FAILED, Transaction.Status.CANCELLED]:
            return Response(
                {"error": "Only failed or cancelled transactions can be retried."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if transaction.invoice:
            invoice = transaction.invoice
            if invoice.status == 'paid':
                return Response(
                    {'error': 'Associated invoice is already paid'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            invoice.status = 'pending'
            invoice.save(update_fields=['status'])
        transaction.status = Transaction.Status.PENDING
        transaction.error_message = ''
        transaction.save(update_fields=['status', 'error_message'])
        return Response({
            'message': 'Transaction reset for retry.',
            'transaction_id': transaction.transaction_id,
            'status': transaction.status,
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
    tags=['Payments - Finance'],
    description='Finance payment attempts and outcomes ledger',
)
class FinancePaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsFinanceDashboardUser]

    def get_queryset(self):
        return Payment.objects.select_related('user', 'user__organization').order_by('-created_at')

    @extend_schema(
        summary='List finance payments',
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter by payment status'),
            OpenApiParameter(name='payment_method', type=str, description='Filter by payment method'),
            OpenApiParameter(name='search', type=str, description='Search by email, provider IDs, description, or payment ID'),
            OpenApiParameter(name='ordering', type=str, description='Ordering field, default -created_at'),
        ],
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        method_filter = request.query_params.get('payment_method')
        if method_filter:
            queryset = queryset.filter(payment_method=method_filter)

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(provider_order_id__icontains=search)
                | Q(provider_payment_id__icontains=search)
                | Q(description__icontains=search)
                | Q(id__icontains=search)
            )

        ordering = request.query_params.get('ordering') or '-created_at'
        allowed_ordering = {'created_at', '-created_at', 'completed_at', '-completed_at', 'updated_at', '-updated_at'}
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary='Retry a failed payment',
        description='Reset a failed payment to pending so the user can attempt again',
    )
    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        payment = self.get_object()
        if payment.status != 'failed':
            return Response(
                {'error': 'Only failed payments can be retried.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment.status = 'pending'
        payment.save(update_fields=['status'])
        return Response({'message': 'Payment reset for retry.', 'id': str(payment.id), 'status': payment.status})


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
class SubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing subscription plans."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Subscription.objects.all().order_by('price', 'name')
        if _can_manage_subscription_plans(self.request.user):
            return queryset
        return queryset.filter(status=Subscription.Status.ACTIVE)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return SubscriptionCreateUpdateSerializer
        return SubscriptionSerializer

    def _require_plan_admin(self, request):
        if not _can_manage_subscription_plans(request.user):
            raise PermissionDenied('Only TASC admins can manage subscription plans.')
    
    @extend_schema(
        summary='List subscription plans',
        description='Returns all plans for TASC admins and active plans for other authenticated users',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get subscription plan details',
        description='Returns detailed information about a subscription plan visible to the requester',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary='Create subscription plan',
        description='Create a subscription plan (TASC admin only)',
        request=SubscriptionCreateUpdateSerializer,
        responses={201: SubscriptionSerializer},
    )
    def create(self, request, *args, **kwargs):
        self._require_plan_admin(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(SubscriptionSerializer(instance).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Update subscription plan',
        description='Update a subscription plan (TASC admin only)',
        request=SubscriptionCreateUpdateSerializer,
        responses={200: SubscriptionSerializer},
    )
    def update(self, request, *args, **kwargs):
        self._require_plan_admin(request)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(SubscriptionSerializer(instance).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary='Delete subscription plan',
        description='Deletes a subscription plan only when it has never been assigned to a user subscription.',
    )
    def destroy(self, request, *args, **kwargs):
        self._require_plan_admin(request)
        instance = self.get_object()
        if instance.user_subscriptions.exists():
            raise ValidationError(
                {
                    'detail': (
                        'This subscription plan is already referenced by user subscriptions. '
                        'Set its status to inactive or archived instead.'
                    )
                }
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


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

        # Phase 1: enforce one learner subscription at a time.
        # Block creation when an ACTIVE/PAUSED subscription already exists with an end_date in the future.
        now = timezone.now()
        has_other_active_or_paused = UserSubscription.objects.filter(
            user=request.user,
            status__in=[UserSubscription.Status.ACTIVE, UserSubscription.Status.PAUSED],
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gt=now)
        ).exists()

        if has_other_active_or_paused:
            return Response(
                {'error': 'An active subscription already exists for this user.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save(user=request.user)
        
        # Configure active access window for Phase 1 gating.
        subscription = serializer.instance
        subscription_plan = subscription.subscription

        if is_trial:
            end_date = timezone.now() + timedelta(days=7)
            subscription.trial_end_date = end_date
        else:
            end_date = timezone.now() + timedelta(days=subscription_plan.duration_days)
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
        description='Cancel an active subscription with an optional reason',
        request={'type': 'object', 'properties': {'reason': {'type': 'string', 'description': 'Cancellation reason'}}},
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

        reason = request.data.get('reason', '')
        subscription.status = 'cancelled'
        subscription.auto_renew = False
        subscription.cancelled_at = timezone.now()
        subscription.cancellation_reason = reason
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
        
        # Extend end date using the paid Phase 1 duration (plan-derived; 6 months).
        subscription.end_date = timezone.now() + timedelta(days=subscription.subscription.duration_days)
        
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
    @extend_schema(
        summary='Revenue breakdown by organization',
        description='Returns total revenue grouped by organization for superadmin dashboards',
    )
    @action(detail=False, methods=['get'], url_path='revenue-by-org')
    def revenue_by_org(self, request):
        """Revenue totals grouped by organization."""
        from django.db.models import Sum
        from rest_framework.exceptions import PermissionDenied

        if not hasattr(request.user, 'role') or request.user.role not in ['tasc_admin', 'finance']:
            raise PermissionDenied('Superadmin or finance access required.')

        rows = (
            Transaction.objects.filter(status='completed', organization__isnull=False)
            .values('organization__id', 'organization__name')
            .annotate(revenue=Sum('amount'))
            .order_by('-revenue')
        )

        data = [
            {
                'organization_id': r['organization__id'],
                'organization': r['organization__name'],
                'revenue': str(r['revenue'] or 0),
            }
            for r in rows
        ]

        return Response({'results': data})

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


@extend_schema(
    tags=['Payments - Finance'],
    summary='Finance dashboard overview',
    description='Read-only dashboard summary for finance-facing roles.',
    responses={200: FinanceDashboardOverviewSerializer},
)
class FinanceDashboardOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, IsFinanceDashboardUser]

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        completed_payments = Payment.objects.filter(status='completed')
        total_collected = completed_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        month_collected = completed_payments.filter(
            completed_at__gte=month_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        pending_invoices = Invoice.objects.filter(status='pending')
        pending_invoices_count = pending_invoices.count()
        pending_invoices_amount = pending_invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

        active_subscribers = UserSubscription.objects.filter(status='active').count()

        trend_start = (month_start - timedelta(days=31 * 5)).replace(day=1)
        trend_rows = (
            completed_payments
            .filter(completed_at__isnull=False, completed_at__gte=trend_start)
            .annotate(month=TruncMonth('completed_at'))
            .values('month')
            .annotate(collected_revenue=Sum('amount'))
            .order_by('month')
        )
        trend_map = {
            row['month'].strftime('%Y-%m'): row['collected_revenue'] or Decimal('0.00')
            for row in trend_rows
            if row.get('month')
        }
        def _money_str(value):
            return format(value or Decimal('0.00'), '.2f')

        revenue_trend = []
        for i in range(5, -1, -1):
            month_point = (month_start - timedelta(days=31 * i)).replace(day=1)
            key = month_point.strftime('%Y-%m')
            revenue_trend.append({
                'month': key,
                'collected_revenue': _money_str(trend_map.get(key, Decimal('0.00'))),
            })

        recent_payment_events = []
        recent_payments = (
            Payment.objects.select_related('user')
            .order_by('-created_at')[:8]
        )
        for payment in recent_payments:
            recent_payment_events.append({
                'payment_id': payment.id,
                'created_at': payment.created_at,
                'completed_at': payment.completed_at,
                'status': payment.status,
                'amount': _money_str(payment.amount),
                'currency': payment.currency,
                'payment_method': payment.payment_method,
                'provider_order_id': payment.provider_order_id,
                'provider_payment_id': payment.provider_payment_id,
                'user_email': payment.user.email if payment.user else None,
                'description': payment.description or '',
            })

        default_currency = (
            completed_payments.exclude(currency='')
            .values_list('currency', flat=True)
            .first()
            or 'UGX'
        )
        payload = {
            'currency': default_currency,
            'kpis': {
                'total_collected_revenue': _money_str(total_collected),
                'collected_revenue_this_month': _money_str(month_collected),
                'pending_invoices_count': pending_invoices_count,
                'pending_invoices_amount': _money_str(pending_invoices_amount),
                'active_subscribers': active_subscribers,
            },
            'revenue_trend': revenue_trend,
            'recent_payment_events': recent_payment_events,
        }
        serializer = FinanceDashboardOverviewSerializer(payload)
        return Response(serializer.data)


def _month_start(dt):
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_month(dt, months_delta):
    year = dt.year
    month = dt.month + months_delta
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return dt.replace(year=year, month=month, day=1)


def _money_str(value):
    return format(value or Decimal('0.00'), '.2f')


ALERT_THRESHOLD_INVOICE_OVERDUE_COUNT = 3
ALERT_THRESHOLD_FAILED_24H_COUNT = 5
ALERT_THRESHOLD_FAILED_24H_MIN_VOLUME = 20
ALERT_THRESHOLD_PENDING_OLD_COUNT = 8
ALERT_PENDING_OLD_HOURS = 2
ALERT_SUBSCRIPTION_EXPIRY_DAYS = 14
ALERT_THRESHOLD_SUBSCRIPTION_EXPIRY_COUNT = 10
ALERT_INVOICE_DUE_SOON_DAYS = 7


@extend_schema(
    tags=['Payments - Finance'],
    summary='Finance alerts',
    description='Read-only aggregate finance alerts for dashboard operations.',
    responses={200: FinanceAlertsResponseSerializer},
)
class FinanceAlertsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsFinanceDashboardUser]

    def get(self, request):
        now = timezone.now()
        today = timezone.localdate()
        alerts = []

        # Critical: overdue pending invoice backlog
        overdue_qs = Invoice.objects.filter(status='pending', due_date__lt=today)
        overdue_count = overdue_qs.count()
        if overdue_count >= ALERT_THRESHOLD_INVOICE_OVERDUE_COUNT:
            overdue_amount = overdue_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            alerts.append({
                'id': f'invoice-overdue-{today.isoformat()}',
                'severity': 'critical',
                'category': 'invoice',
                'code': 'INVOICE_OVERDUE_BACKLOG',
                'title': 'Overdue invoices require action',
                'message': f'{overdue_count} overdue invoices totaling UGX {int(overdue_amount)}.',
                'metric_value': overdue_count,
                'metric_unit': 'count',
                'amount': _money_str(overdue_amount),
                'currency': 'UGX',
                'action': {'label': 'Review invoices', 'route': '/finance/invoices'},
                'created_at': now,
            })

        # Critical: payment failure spike in last 24h with minimum volume.
        failures_window_start = now - timedelta(hours=24)
        payments_24h = Payment.objects.filter(created_at__gte=failures_window_start)
        outcomes_24h = payments_24h.values('status').annotate(count=Count('id'))
        outcomes_map = {row['status']: row['count'] for row in outcomes_24h}
        failed_24h = outcomes_map.get('failed', 0)
        total_24h = sum(outcomes_map.values())
        if failed_24h >= ALERT_THRESHOLD_FAILED_24H_COUNT and total_24h >= ALERT_THRESHOLD_FAILED_24H_MIN_VOLUME:
            alerts.append({
                'id': f'payment-failure-spike-{today.isoformat()}',
                'severity': 'critical',
                'category': 'payment',
                'code': 'PAYMENT_FAILURE_SPIKE',
                'title': 'Payment failures spiked in the last 24 hours',
                'message': f'{failed_24h} failed payments out of {total_24h} attempts in the last 24 hours.',
                'metric_value': failed_24h,
                'metric_unit': 'count',
                'amount': None,
                'currency': '',
                'action': {'label': 'Review payments', 'route': '/finance/payments'},
                'created_at': now,
            })

        # Warning: pending payments older than expected processing window.
        pending_before = now - timedelta(hours=ALERT_PENDING_OLD_HOURS)
        pending_old_count = Payment.objects.filter(status='pending', created_at__lt=pending_before).count()
        if pending_old_count >= ALERT_THRESHOLD_PENDING_OLD_COUNT:
            alerts.append({
                'id': f'payment-pending-buildup-{today.isoformat()}',
                'severity': 'warning',
                'category': 'payment',
                'code': 'PAYMENT_PENDING_BUILDUP',
                'title': 'Pending payments are building up',
                'message': (
                    f'{pending_old_count} payments have been pending for more than '
                    f'{ALERT_PENDING_OLD_HOURS} hours.'
                ),
                'metric_value': pending_old_count,
                'metric_unit': 'count',
                'amount': None,
                'currency': '',
                'action': {'label': 'Inspect payments', 'route': '/finance/payments'},
                'created_at': now,
            })

        # Warning: active subscriptions nearing expiry.
        expiry_cutoff = now + timedelta(days=ALERT_SUBSCRIPTION_EXPIRY_DAYS)
        expiring_count = UserSubscription.objects.filter(
            status='active',
            end_date__isnull=False,
            end_date__gte=now,
            end_date__lte=expiry_cutoff,
        ).count()
        if expiring_count >= ALERT_THRESHOLD_SUBSCRIPTION_EXPIRY_COUNT:
            alerts.append({
                'id': f'subscription-expiry-wave-{today.isoformat()}',
                'severity': 'warning',
                'category': 'subscription',
                'code': 'SUBSCRIPTION_EXPIRY_WAVE',
                'title': 'Active subscriptions nearing expiry',
                'message': (
                    f'{expiring_count} active subscriptions are due to expire '
                    f'within {ALERT_SUBSCRIPTION_EXPIRY_DAYS} days.'
                ),
                'metric_value': expiring_count,
                'metric_unit': 'count',
                'amount': None,
                'currency': '',
                'action': {'label': 'Review subscriptions', 'route': '/finance/subscriptions'},
                'created_at': now,
            })

        # Info: pending invoices due soon.
        due_soon_cutoff = today + timedelta(days=ALERT_INVOICE_DUE_SOON_DAYS)
        due_soon_count = Invoice.objects.filter(
            status='pending',
            due_date__gte=today,
            due_date__lte=due_soon_cutoff,
        ).count()
        if due_soon_count > 0:
            alerts.append({
                'id': f'invoice-due-soon-{today.isoformat()}',
                'severity': 'info',
                'category': 'invoice',
                'code': 'INVOICE_DUE_SOON',
                'title': 'Pending invoices due soon',
                'message': f'{due_soon_count} pending invoices are due within {ALERT_INVOICE_DUE_SOON_DAYS} days.',
                'metric_value': due_soon_count,
                'metric_unit': 'count',
                'amount': None,
                'currency': '',
                'action': {'label': 'Open invoices', 'route': '/finance/invoices'},
                'created_at': now,
            })

        # Info: subscription cancellations today.
        cancelled_today_count = UserSubscription.objects.filter(
            status='cancelled',
            cancelled_at__date=today,
        ).count()
        if cancelled_today_count > 0:
            alerts.append({
                'id': f'subscription-cancelled-today-{today.isoformat()}',
                'severity': 'info',
                'category': 'subscription',
                'code': 'SUBSCRIPTION_CANCELLATIONS_TODAY',
                'title': 'Subscription cancellations recorded today',
                'message': f'{cancelled_today_count} subscription cancellations were recorded today.',
                'metric_value': cancelled_today_count,
                'metric_unit': 'count',
                'amount': None,
                'currency': '',
                'action': {'label': 'View subscriptions', 'route': '/finance/subscriptions'},
                'created_at': now,
            })

        severity_order = {'critical': 0, 'warning': 1, 'info': 2, 'success': 3}
        alerts.sort(key=lambda item: (severity_order.get(item['severity'], 99), -item['created_at'].timestamp()))

        summary = {
            'total': len(alerts),
            'critical': sum(1 for a in alerts if a['severity'] == 'critical'),
            'warning': sum(1 for a in alerts if a['severity'] == 'warning'),
            'info': sum(1 for a in alerts if a['severity'] == 'info'),
            'success': 0,
        }
        payload = {
            'as_of': now,
            'summary': summary,
            'alerts': alerts,
        }
        serializer = FinanceAlertsResponseSerializer(payload)
        return Response(serializer.data)


@extend_schema(
    tags=['Payments - Finance'],
    summary='Finance analytics overview',
    description='Aggregated finance analytics summary for analytics page.',
    parameters=[
        OpenApiParameter(
            name='months',
            type=int,
            description='Trend window in months. Allowed values: 6 or 12.',
            required=False,
        ),
    ],
    responses={200: FinanceAnalyticsOverviewSerializer},
)
class FinanceAnalyticsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, IsFinanceDashboardUser]

    def get(self, request):
        try:
            months = int(request.query_params.get('months', 6))
        except (TypeError, ValueError):
            months = 6
        if months not in (6, 12):
            months = 6

        now = timezone.now()
        month_start = _month_start(now)
        window_start = _shift_month(month_start, -(months - 1))
        today = timezone.localdate()

        completed_payments_all_time = Payment.objects.filter(status='completed')
        total_collected = completed_payments_all_time.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        month_collected = completed_payments_all_time.filter(
            completed_at__gte=month_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        window_payments = Payment.objects.filter(created_at__gte=window_start)
        outcomes_rows = window_payments.values('status').annotate(count=Count('id'))
        outcome_map = {row['status']: row['count'] for row in outcomes_rows}
        completed_count = outcome_map.get('completed', 0)
        total_attempts = sum(outcome_map.values())
        completion_rate = round((completed_count / total_attempts) * 100, 1) if total_attempts else 0.0

        trend_rows = (
            Payment.objects.filter(
                status='completed',
                completed_at__isnull=False,
                completed_at__gte=window_start,
            )
            .annotate(month=TruncMonth('completed_at'))
            .values('month')
            .annotate(collected_revenue=Sum('amount'))
            .order_by('month')
        )
        trend_map = {
            row['month'].strftime('%Y-%m'): row['collected_revenue'] or Decimal('0.00')
            for row in trend_rows
            if row.get('month')
        }

        pending_invoices_qs = Invoice.objects.filter(status='pending')
        pending_invoices_count = pending_invoices_qs.count()
        pending_invoices_amount = pending_invoices_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        overdue_invoices_count = pending_invoices_qs.filter(due_date__lt=today).count()

        subscription_rows = (
            UserSubscription.objects.filter(status__in=['active', 'cancelled', 'expired'])
            .values('status')
            .annotate(count=Count('id'))
        )
        subscription_map = {row['status']: row['count'] for row in subscription_rows}

        # New subscriptions trend (monthly count in window)
        new_sub_rows = (
            UserSubscription.objects.filter(created_at__gte=window_start)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        new_sub_map = {
            row['month'].strftime('%Y-%m'): row['count']
            for row in new_sub_rows if row.get('month')
        }

        def _money_str(value):
            return format(value or Decimal('0.00'), '.2f')

        # Revenue by payment method
        revenue_by_method_rows = (
            Payment.objects.filter(status='completed', completed_at__gte=window_start)
            .values('payment_method')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')
        )
        revenue_by_method = [
            {'method': r['payment_method'] or 'unknown', 'total': _money_str(r['total']), 'count': r['count']}
            for r in revenue_by_method_rows
        ]

        # Revenue by plan (aggregate subscription prices per plan)
        revenue_by_plan_rows = (
            UserSubscription.objects.filter(created_at__gte=window_start)
            .values('subscription__name')
            .annotate(total=Sum('price'), count=Count('id'))
            .order_by('-total')
        )
        revenue_by_plan = [
            {'plan': r['subscription__name'] or 'Unknown', 'total': _money_str(r['total']), 'count': r['count']}
            for r in revenue_by_plan_rows
        ]

        revenue_trend = []
        prev_revenue = None
        for i in range(months):
            month_point = _shift_month(window_start, i)
            key = month_point.strftime('%Y-%m')
            revenue = float(trend_map.get(key, Decimal('0.00')))
            growth = None
            if prev_revenue is not None and prev_revenue > 0:
                growth = round(((revenue - prev_revenue) / prev_revenue) * 100, 1)
            revenue_trend.append({
                'month': key,
                'collected_revenue': _money_str(trend_map.get(key, Decimal('0.00'))),
                'growth_percent': growth,
            })
            prev_revenue = revenue

        default_currency = (
            completed_payments_all_time.exclude(currency='')
            .values_list('currency', flat=True)
            .first()
            or 'UGX'
        )

        payload = {
            'as_of': now,
            'currency': default_currency,
            'window': {
                'months': months,
                'from_month': window_start.strftime('%Y-%m'),
                'to_month': month_start.strftime('%Y-%m'),
            },
            'payment_kpis': {
                'total_collected_revenue': _money_str(total_collected),
                'collected_revenue_this_month': _money_str(month_collected),
                'payment_completion_rate_pct': completion_rate,
                'failed_payments_count': outcome_map.get('failed', 0),
            },
            'revenue_trend': revenue_trend,
            'payment_outcomes': {
                'completed': outcome_map.get('completed', 0),
                'pending': outcome_map.get('pending', 0),
                'failed': outcome_map.get('failed', 0),
                'cancelled': outcome_map.get('cancelled', 0),
                'refunded': outcome_map.get('refunded', 0),
                'total': total_attempts,
            },
            'invoice_insights': {
                'pending_invoices_count': pending_invoices_count,
                'pending_invoices_amount': _money_str(pending_invoices_amount),
                'overdue_invoices_count': overdue_invoices_count,
            },
            'subscription_insights': {
                'active': subscription_map.get('active', 0),
                'cancelled': subscription_map.get('cancelled', 0),
                'expired': subscription_map.get('expired', 0),
            },
            'new_subscriptions_trend': [
                {'month': _shift_month(window_start, i).strftime('%Y-%m'),
                 'count': new_sub_map.get(_shift_month(window_start, i).strftime('%Y-%m'), 0)}
                for i in range(months)
            ],
            'revenue_by_method': revenue_by_method,
            'revenue_by_plan': revenue_by_plan,
        }

        serializer = FinanceAnalyticsOverviewSerializer(payload)
        return Response(serializer.data)

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


@extend_schema(
    tags=['Payments - Organization Subscriptions'],
    summary='List all organization subscriptions (LMS Manager)',
    description='Returns subscription status for all organizations. Accessible by LMS Manager and TASC Admin.',
)
class OrganizationSubscriptionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (
            getattr(request.user, 'role', '') in ('lms_manager', 'tasc_admin')
            or request.user.is_superuser
        ):
            raise PermissionDenied("Only LMS Manager or TASC Admin can view this.")

        from apps.accounts.models import Organization, Membership

        orgs = Organization.objects.filter(is_active=True)
        results = []
        for org in orgs:
            sub = (
                UserSubscription.objects.filter(
                    organization=org,
                    status=UserSubscription.Status.ACTIVE,
                )
                .select_related('subscription')
                .order_by('-end_date')
                .first()
            )
            member_count = Membership.objects.filter(
                organization=org, is_active=True
            ).count()
            results.append({
                'organization_id': org.id,
                'organization_name': org.name,
                'max_seats': org.max_seats,
                'used_seats': member_count,
                'subscription_status': sub.status if sub else None,
                'subscription_plan': sub.subscription.name if sub and sub.subscription else None,
                'subscription_end_date': sub.end_date.isoformat() if sub and sub.end_date else None,
                'days_remaining': (sub.end_date - timezone.now()).days if sub and sub.end_date else None,
            })

        return Response(results)


class ChurnReasonsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (
            getattr(request.user, 'role', '') in ('lms_manager', 'tasc_admin', 'finance')
            or request.user.is_superuser
        ):
            raise PermissionDenied("Only finance, LMS Manager or TASC Admin can view this.")

        cancelled = UserSubscription.objects.filter(
            status=UserSubscription.Status.CANCELLED
        ).exclude(cancellation_reason='')

        from collections import Counter
        reason_counts = Counter()
        for sub in cancelled:
            reason = sub.cancellation_reason.strip()
            if reason:
                reason_counts[reason] += 1

        reasons = [
            {'reason': reason, 'count': count}
            for reason, count in reason_counts.most_common()
        ]

        by_plan = (
            cancelled
            .values('subscription__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        churn_by_plan = [
            {'plan': entry['subscription__name'] or 'Unknown', 'count': entry['count']}
            for entry in by_plan
        ]

        churned_orgs = []
        if getattr(request.user, 'role', '') in ('lms_manager', 'tasc_admin') or request.user.is_superuser:
            from apps.accounts.models import Organization
            for org in Organization.objects.filter(is_active=False):
                last_sub = (
                    UserSubscription.objects.filter(organization=org)
                    .order_by('-cancelled_at')
                    .first()
                )
                churned_orgs.append({
                    'organization_id': org.id,
                    'organization_name': org.name,
                    'cancelled_at': last_sub.cancelled_at.isoformat() if last_sub and last_sub.cancelled_at else None,
                    'reason': last_sub.cancellation_reason if last_sub else '',
                    'plan': last_sub.subscription.name if last_sub and last_sub.subscription else '',
                })

        total_cancelled = UserSubscription.objects.filter(status=UserSubscription.Status.CANCELLED).count()
        total_all = UserSubscription.objects.count()
        churn_rate = round((total_cancelled / total_all * 100), 1) if total_all > 0 else 0.0

        return Response({
            'churn_rate': churn_rate,
            'total_cancelled': total_cancelled,
            'reasons': reasons,
            'churn_by_plan': churn_by_plan,
            'churned_organizations': churned_orgs,
        })


class FinancialStatementsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (
            getattr(request.user, 'role', '') in ('lms_manager', 'tasc_admin', 'finance')
            or request.user.is_superuser
        ):
            raise PermissionDenied("Only finance, LMS Manager or TASC Admin can view this.")

        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        tx_qs = Transaction.objects.all()
        inv_qs = Invoice.objects.all()

        if from_date:
            tx_qs = tx_qs.filter(created_at__gte=from_date)
            inv_qs = inv_qs.filter(created_at__gte=from_date)
        if to_date:
            tx_qs = tx_qs.filter(created_at__lte=to_date)
            inv_qs = inv_qs.filter(created_at__lte=to_date)

        total_income = tx_qs.filter(
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        total_refunds = tx_qs.filter(
            status='refunded'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        pending_amount = inv_qs.filter(
            status='pending'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        overdue_amount = inv_qs.filter(
            status='overdue'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        paid_amount = inv_qs.filter(
            status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        net_income = total_income - total_refunds
        collection_rate = round(
            (paid_amount / (paid_amount + pending_amount + overdue_amount) * 100), 1
        ) if (paid_amount + pending_amount + overdue_amount) > 0 else 0.0

        active_subs = UserSubscription.objects.filter(status='active').count()
        cancelled_subs = UserSubscription.objects.filter(status='cancelled').count()
        expired_subs = UserSubscription.objects.filter(status='expired').count()

        income_by_month = (
            tx_qs.filter(status='completed')
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
        monthly_income = [
            {'month': entry['month'].strftime('%Y-%m'), 'amount': str(entry['total'] or 0)}
            for entry in income_by_month
        ]

        return Response({
            'period': {
                'from': from_date or 'all',
                'to': to_date or 'all',
            },
            'income_statement': {
                'total_revenue': str(total_income),
                'total_refunds': str(total_refunds),
                'net_income': str(net_income),
                'pending_invoices': str(pending_amount),
                'overdue_invoices': str(overdue_amount),
                'collected_invoices': str(paid_amount),
                'collection_rate_pct': collection_rate,
            },
            'balance_sheet': {
                'accounts_receivable': str(pending_amount + overdue_amount),
                'active_subscriptions': active_subs,
                'cancelled_subscriptions': cancelled_subs,
                'expired_subscriptions': expired_subs,
            },
            'monthly_income': monthly_income,
        })
