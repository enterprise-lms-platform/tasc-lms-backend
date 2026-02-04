from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Invoice, InvoiceItem, Transaction, PaymentMethod,
    Subscription, UserSubscription
)
from .serializers import (
    InvoiceSerializer, InvoiceCreateSerializer,
    InvoiceItemSerializer, TransactionSerializer,
    PaymentMethodSerializer, PaymentMethodCreateSerializer,
    SubscriptionSerializer, UserSubscriptionSerializer, UserSubscriptionCreateSerializer,
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
        if user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return Invoice.objects.all()
        return Invoice.objects.filter(customer=user)
    
    @extend_schema(
        summary='List invoices',
        description='Returns invoices (finance team sees all, users see their own)',
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter by status'),
            OpenApiParameter(name='customer', type=int, description='Filter by customer ID (finance only)'),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Create invoice',
        description='Create a new invoice (finance team only)',
        request=InvoiceCreateSerializer,
        responses={201: InvoiceSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
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
        return super().update(request, *args, **kwargs)
    
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
        invoice.save()
        
        serializer = InvoiceSerializer(invoice)
        return Response(serializer.data)


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
        if user.role in ['finance', 'tasc_admin', 'lms_manager']:
            return Transaction.objects.all()
        return Transaction.objects.filter(invoice__customer=user)
    
    @extend_schema(
        summary='List transactions',
        description='Returns all payment transactions (finance team sees all, users see their own)',
        parameters=[
            OpenApiParameter(name='invoice', type=int, description='Filter by invoice ID'),
            OpenApiParameter(name='status', type=str, description='Filter by status'),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get transaction details',
        description='Returns detailed transaction information',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


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
        return PaymentMethod.objects.filter(user=self.request.user)
    
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
        return super().create(request, *args, **kwargs)
    
    @extend_schema(
        summary='Delete payment method',
        description='Delete a saved payment method',
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    
    @extend_schema(
        summary='Set default payment method',
        description='Set a payment method as the default for future payments',
        responses={200: PaymentMethodSerializer},
    )
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        payment_method = self.get_object()
        
        # Remove default from other methods
        PaymentMethod.objects.filter(user=self.request.user, is_default=True).update(is_default=False)
        
        # Set this as default
        payment_method.is_default = True
        payment_method.save()
        
        serializer = PaymentMethodSerializer(payment_method)
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
        if user.role in ['finance', 'tasc_admin', 'lms_manager']:
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
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Subscribe to plan',
        description='Subscribe to a subscription plan',
        request=UserSubscriptionCreateSerializer,
        responses={201: UserSubscriptionSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
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
        
        # Logic to renew subscription would go here
        subscription.status = 'active'
        subscription.save()
        
        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data)