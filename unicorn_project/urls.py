from django.contrib import admin
from django.urls import path, include
from unicorn_project.training.views_auth import ForcePasswordChangeView, forgot_password

urlpatterns = [
    path('admin/', admin.site.urls),

    # Override only this one route so our view can clear the flag:
    path('accounts/password_change/', ForcePasswordChangeView.as_view(), name='password_change'),
    # Simple "forgot password" (emails a new temporary password)
    path('accounts/forgot-password/', forgot_password, name='forgot_password'),
    # All other auth views (login/logout/etc.)
    path('accounts/', include('django.contrib.auth.urls')),

    # Your app
    path('', include('unicorn_project.training.urls')),
]