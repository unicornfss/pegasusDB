from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def engineer_dashboard(request):
    """
    Temporary Engineer dashboard.
    Replace with real widgets later.
    """
    return render(request, "engineer/dashboard.html", {
        "user": request.user,
    })
