import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
import requests

logger = logging.getLogger(__name__)

User = get_user_model()


@extend_schema(
    tags=['Accounts'],
    summary='Google OAuth Login',
    description='Authenticate user using Google OAuth ID token. Returns JWT tokens and user information.',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'id_token': {'type': 'string', 'description': 'Google OAuth ID token'},
                'access_token': {'type': 'string', 'description': 'Google OAuth access token (optional)'},
            },
            'required': ['id_token'],
        }
    },
    responses={
        200: OpenApiResponse(
            description='Login successful',
            response={
                'type': 'object',
                'properties': {
                    'refresh': {'type': 'string'},
                    'access': {'type': 'string'},
                    'user': {'type': 'object'},
                    'is_new_user': {'type': 'boolean'},
                }
            }
        ),
        400: OpenApiResponse(description='Invalid request or token'),
        403: OpenApiResponse(description='Account inactive'),
        500: OpenApiResponse(description='Server error'),
    },
    examples=[
        OpenApiExample(
            'Login Success',
            value={
                'refresh': 'jwt-refresh-token',
                'access': 'jwt-access-token',
                'user': {
                    'id': 1,
                    'name': 'John Doe',
                    'email': 'john@example.com',
                    'avatar': 'https://example.com/avatar.jpg',
                    'role': 'learner',
                    'email_verified': True,
                },
                'is_new_user': False,
            },
            response_only=True,
        ),
    ],
)
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def google_oauth_login(request):
    """
    Google OAuth Login Endpoint.
    
    Expects a JSON body with:
    {
        "id_token": "google_id_token",
        "access_token": "google_access_token"  # optional
    }
    
    Returns JWT tokens and user information.
    """
    id_token = request.data.get('id_token')
    
    if not id_token:
        return Response(
            {'error': 'ID token is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Verify the Google ID token
        google_response = requests.get(
            f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}'
        )
        
        if google_response.status_code != 200:
            return Response(
                {'error': 'Invalid Google ID token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        google_data = google_response.json()
        
        # Verify audience (client ID) if configured
        if hasattr(settings, 'GOOGLE_CLIENT_ID') and settings.GOOGLE_CLIENT_ID:
            token_aud = google_data.get('aud')
            if token_aud != settings.GOOGLE_CLIENT_ID:
                return Response(
                    {'error': 'Invalid token audience. Token was not issued for this application.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Extract user information
        google_id = google_data.get('sub')
        email = google_data.get('email')
        name = google_data.get('name')
        given_name = google_data.get('given_name', '')
        family_name = google_data.get('family_name', '')
        picture = google_data.get('picture')
        email_verified = google_data.get('email_verified', False)
        
        if not email:
            return Response(
                {'error': 'Email is required from Google'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not email_verified:
            return Response(
                {'error': 'Email must be verified on Google'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user exists with this Google ID, then link/create atomically.
        user = None
        is_new_user = False
        try:
            with transaction.atomic():
                try:
                    user = User.objects.get(google_id=google_id)
                except User.DoesNotExist:
                    # Check if user exists with this email
                    try:
                        user = User.objects.get(email__iexact=email)
                        # Link Google account to existing user
                        user.google_id = google_id
                        user.google_picture = picture
                        if not user.avatar:
                            user.avatar = picture
                        user.save()
                    except User.DoesNotExist:
                        # Create new user
                        # Generate username from email
                        base_username = email.split('@')[0][:25]
                        username = base_username
                        i = 1
                        while User.objects.filter(username=username).exists():
                            i += 1
                            username = f"{base_username}{i}"

                        user = User.objects.create_user(
                            username=username,
                            email=email.strip().lower(),
                            first_name=given_name,
                            last_name=family_name,
                            google_id=google_id,
                            google_picture=picture,
                            avatar=picture,
                            email_verified=True,
                            is_active=True,
                            role='learner',  # Default role for new users
                        )
                        is_new_user = True
        except IntegrityError:
            return Response(
                {"email": ["A user with this email already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Enforce consistent account state checks across auth methods
        if not user.is_active:
            return Response(
                {'error': 'Account is inactive'},
                status=status.HTTP_403_FORBIDDEN
            )
        if hasattr(user, "email_verified") and not user.email_verified:
            return Response(
                {"error": "Email not verified."},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'name': user.get_full_name(),
                'email': user.email,
                'avatar': user.avatar,
                'role': user.role,
                'email_verified': user.email_verified,
            },
            'is_new_user': is_new_user,
        }, status=status.HTTP_200_OK)
    
    except Exception:
        logger.exception("Google OAuth login failed")
        return Response(
            {'error': 'Authentication failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Accounts'],
    summary='Link Google Account',
    description='Link a Google OAuth account to the authenticated user.',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'id_token': {'type': 'string', 'description': 'Google OAuth ID token'},
            },
            'required': ['id_token'],
        }
    },
    responses={
        200: OpenApiResponse(description='Account linked successfully'),
        400: OpenApiResponse(description='Invalid request or token'),
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def google_oauth_link(request):
    """
    Link Google Account Endpoint.
    
    Expects a JSON body with:
    {
        "id_token": "google_id_token"
    }
    
    Links a Google account to the currently authenticated user.
    """
    id_token = request.data.get('id_token')
    
    if not id_token:
        return Response(
            {'error': 'ID token is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Verify Google ID token (same verification as google_oauth_login)
        google_response = requests.get(
            f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}'
        )
        
        if google_response.status_code != 200:
            return Response(
                {'error': 'Invalid Google ID token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        google_data = google_response.json()
        
        # Verify audience (client ID) if configured
        if hasattr(settings, 'GOOGLE_CLIENT_ID') and settings.GOOGLE_CLIENT_ID:
            token_aud = google_data.get('aud')
            if token_aud != settings.GOOGLE_CLIENT_ID:
                return Response(
                    {'error': 'Invalid token audience.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        google_id = google_data.get('sub')
        picture = google_data.get('picture')
        
        # Check if Google ID is already linked to another account
        user = request.user
        if User.objects.filter(google_id=google_id).exclude(id=user.id).exists():
            return Response(
                {'error': 'Google account is already linked to another account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Link Google account to the authenticated user
        user.google_id = google_id
        user.google_picture = picture
        if not user.avatar:
            user.avatar = picture
        user.save()
        
        return Response({
            'message': 'Google account linked successfully',
            'user': {
                'id': user.id,
                'name': user.get_full_name(),
                'email': user.email,
                'avatar': user.avatar,
            }
        }, status=status.HTTP_200_OK)
    
    except Exception:
        logger.exception("Failed to link Google account for user %s", request.user.id)
        return Response(
            {'error': 'Failed to link Google account. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Accounts'],
    summary='Unlink Google Account',
    description='Unlink Google OAuth account from the current user.',
    responses={
        200: OpenApiResponse(description='Account unlinked successfully'),
        400: OpenApiResponse(description='Cannot unlink account'),
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def google_oauth_unlink(request):
    """
    Unlink Google Account Endpoint.
    
    Unlinks the Google account from the current user.
    User must have a password set for security.
    """
    user = request.user
    
    # Check if user has a password set
    if not user.check_password(request.data.get('password', '')):
        return Response(
            {'error': 'Password is required and must be correct'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Unlink Google account
    user.google_id = None
    user.google_picture = None
    user.save()
    
    return Response({
        'message': 'Google account unlinked successfully'
    }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Accounts'],
    summary='Get Google OAuth Status',
    description='Get the Google OAuth linking status for the current user.',
    responses={
        200: OpenApiResponse(
            description='Status retrieved successfully',
            response={
                'type': 'object',
                'properties': {
                    'is_linked': {'type': 'boolean'},
                    'google_id': {'type': 'string', 'nullable': True},
                    'google_picture': {'type': 'string', 'nullable': True},
                }
            }
        ),
    },
    examples=[
        OpenApiExample(
            'Linked Account',
            value={
                'is_linked': True,
                'google_id': '123456789',
                'google_picture': 'https://example.com/pic.jpg',
            },
            response_only=True,
        ),
        OpenApiExample(
            'Not Linked',
            value={
                'is_linked': False,
                'google_id': None,
                'google_picture': None,
            },
            response_only=True,
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def google_oauth_status(request):
    """
    Get Google OAuth Status Endpoint.
    
    Returns the current user's Google OAuth linking status.
    """
    user = request.user
    
    return Response({
        'is_linked': bool(user.google_id),
        'google_id': user.google_id,
        'google_picture': user.google_picture,
    }, status=status.HTTP_200_OK)


google_oauth_login.cls.throttle_scope = "google_login"
google_oauth_link.cls.throttle_scope = "google_link"
google_oauth_unlink.cls.throttle_scope = "google_unlink"