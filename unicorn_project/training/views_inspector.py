from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def inspector_dashboard(request):
    """
    Temporary Inspector dashboard.
    Replace with real widgets later.
    """
    return render(request, "inspector/dashboard.html", {
        "user": request.user,
    })
