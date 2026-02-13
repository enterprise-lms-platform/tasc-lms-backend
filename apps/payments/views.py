from django.shortcuts import render
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
import uuid

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
    PaymentSerializer, CreatePaymentSerializer, PaymentConfirmationSerializer,
    PaymentWebhookSerializer, PaymentStatusSerializer
)


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
        
        # If this is the first payment method, make it default
        if PaymentMethod.objects.filter(user=request.user).count() == 1:
            payment_method = PaymentMethod.objects.get(id=serializer.data['id'])
            payment_method.is_default = True
            payment_method.save()
        
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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set the user
        serializer.save(user=request.user)
        
        # Create invoice for subscription
        subscription = serializer.instance
        subscription_plan = subscription.subscription
        
        # Calculate end date based on billing cycle
        if subscription_plan.billing_cycle == 'monthly':
            end_date = timezone.now() + timezone.timedelta(days=30)
        elif subscription_plan.billing_cycle == 'quarterly':
            end_date = timezone.now() + timezone.timedelta(days=90)
        else:  # yearly
            end_date = timezone.now() + timezone.timedelta(days=365)
        
        subscription.end_date = end_date
        subscription.save()
        
        # Create invoice
        invoice = Invoice.objects.create(
            user=request.user,
            invoice_type='subscription',
            customer_name=request.user.get_full_name() or request.user.email,
            customer_email=request.user.email,
            subtotal=subscription_plan.price,
            total_amount=subscription_plan.price,
            currency=subscription_plan.currency,
            status='pending',
            due_date=timezone.now() + timezone.timedelta(days=7)
        )
        
        # Create invoice item
        InvoiceItem.objects.create(
            invoice=invoice,
            item_type='subscription',
            item_id=subscription_plan.id,
            description=f"{subscription_plan.name} - {subscription_plan.billing_cycle} subscription",
            quantity=1,
            unit_price=subscription_plan.price
        )
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
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
        
        # Extend end date
        subscription_plan = subscription.subscription
        if subscription_plan.billing_cycle == 'monthly':
            subscription.end_date = timezone.now() + timezone.timedelta(days=30)
        elif subscription_plan.billing_cycle == 'quarterly':
            subscription.end_date = timezone.now() + timezone.timedelta(days=90)
        else:  # yearly
            subscription.end_date = timezone.now() + timezone.timedelta(days=365)
        
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
        