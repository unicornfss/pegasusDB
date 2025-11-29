from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def inspector_dashboard(request):
    if not request.user.groups.filter(name__iexact="inspector").exists():
        return HttpResponseForbidden("You do not have access to the inspector portal.")
    return render(request, "inspector/dashboard.html")
