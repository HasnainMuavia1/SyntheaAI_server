from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import RegisterView, api_health_check, ProfileView

urlpatterns = [
    path('', api_health_check, name='api_health'),
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('register', RegisterView.as_view(), name='auth_register_no_slash'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token', TokenObtainPairView.as_view(), name='token_obtain_pair_no_slash'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/refresh', TokenRefreshView.as_view(), name='token_refresh_no_slash'),
    path('profile/', ProfileView.as_view(), name='user_profile'),
    path('profile', ProfileView.as_view(), name='user_profile_no_slash'),
]
