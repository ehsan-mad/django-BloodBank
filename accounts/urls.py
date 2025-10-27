from django.urls import path
from .views import RegisterView, CustomTokenObtainPairView, VerifyEmailView, LogoutView, ProfileView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('email/verify/', VerifyEmailView.as_view(), name='auth-email-verify'),
]

# profile endpoint exposed at /api/v1/profile/ from project urls
