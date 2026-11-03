from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from account.ui import OWNER_UI, set_active_ui


def manager_required(view):
    """Booking management is for approved restaurant owners and admins only."""
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if user.is_superuser or user.is_admin_role:
            return view(request, *args, **kwargs)
        if user.role == user.Role.OWNER and not user.is_owner_role:
            return redirect("owner_application_status")
        if not user.is_owner_role:
            return HttpResponseForbidden("Owner or administrator access is required.")
        set_active_ui(request, OWNER_UI)
        return view(request, *args, **kwargs)

    return wrapped
