# unicorn_project/urls.py  (or wherever your root urls.py is)
from django.contrib import admin
from django.urls import path, include
from unicorn_project.training import urls as training_urls

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(training_urls)),
    path('accounts/', include('django.contrib.auth.urls')),  # <-- add this
]
