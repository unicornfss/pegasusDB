from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def engineer_dashboard(request):
    if not request.user.groups.filter(name__iexact="engineer").exists():
        return HttpResponseForbidden("You do not have access to the engineer portal.")
    return render(request, "engineer/dashboard.html")
