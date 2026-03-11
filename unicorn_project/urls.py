from django.contrib import admin
from django.urls import path, include
from unicorn_project.training.views_auth import ForcePasswordChangeView, forgot_password, custom_login, two_factor_auth, two_factor_setup, two_factor_verify, two_factor_disable

urlpatterns = [
    path('admin/', admin.site.urls),

    # Override auth views for 2FA support
    path('accounts/login/', custom_login, name='login'),
    path('accounts/two-factor/', two_factor_auth, name='two_factor_auth'),
    path('accounts/two-factor/setup/', two_factor_setup, name='two_factor_setup'),
    path('accounts/two-factor/verify/', two_factor_verify, name='two_factor_verify'),
    path('accounts/two-factor/disable/', two_factor_disable, name='two_factor_disable'),

    # Override only this one route so our view can clear the flag:
    path('accounts/password_change/', ForcePasswordChangeView.as_view(), name='password_change'),
    # Simple "forgot password" (emails a new temporary password)
    path('accounts/forgot-password/', forgot_password, name='forgot_password'),
    # All other auth views (login/logout/etc.)
    path('accounts/', include('django.contrib.auth.urls')),

    # Your app
    path('', include('unicorn_project.training.urls')),
]