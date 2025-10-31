from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .serializers import RegisterSerializer, ProfileSerializer
from .utils import make_verification_token, verify_verification_token, success_response, error_response

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Unable to register or account created earlier',
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = serializer.save()
            # send verification email (console backend in dev)
            token = make_verification_token(user)
            verify_url = self.request.build_absolute_uri(f"/api/v1/auth/email/verify/?token={token}")
            subject = 'Verify your email'
            message = f'Hi {user.get_full_name() or user.username},\n\nPlease verify your email by visiting: {verify_url}\n\nIf you did not register, ignore this email.'
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])

            data = {"username": user.username, "email": user.email, "blood_group": user.blood_group}
            return success_response(
                'Register successful',
                data=data,
                status_code=status.HTTP_201_CREATED
            )
        except Exception as exc:
            return error_response(
                'Unable to register or account created earlier',
                errors={'detail': str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST
            )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        # Prevent login if email not verified
        user = self.user
        if not getattr(user, 'email_verified', False):
            raise serializers.ValidationError('Email address not verified.')
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as exc:
            return error_response(
                'Unable to login',
                errors=exc.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        tokens = serializer.validated_data
        return success_response(
            'Login successful',
            data=tokens,
            status_code=status.HTTP_200_OK
        )


class VerifyEmailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            payload = error_response('token required')
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        data = verify_verification_token(token)
        if not data:
            payload = error_response('invalid or expired token')
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        user_id = data.get('user_id')
        user = get_object_or_404(User, id=user_id)
        user.email_verified = True
        user.save()
        payload = success_response('Email verified', {"username": user.username, "email": user.email})
        return Response(payload, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        # Stateless logout - client should discard tokens
        payload = success_response('Logout successful')
        return Response(payload, status=status.HTTP_200_OK)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(user)
        payload = success_response('Profile retrieved', serializer.data)
        return Response(payload, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        user = self.get_object()
        serializer = self.get_serializer(user, data=request.data, partial=partial)
        if not serializer.is_valid():
            payload = error_response('Unable to update profile', serializer.errors)
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        payload = success_response('Profile updated', serializer.data)
        return Response(payload, status=status.HTTP_200_OK)
