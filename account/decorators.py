from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .ui import CUSTOMER_UI, OWNER_UI, set_active_ui


def customer_ui_required(view):
    """Every signed-in account can use the customer interface."""
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        set_active_ui(request, CUSTOMER_UI)
        return view(request, *args, **kwargs)

    return wrapped


def owner_ui_required(view):
    """Require a signed-in owner account for the owner workspace."""
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_owner_role:
            return redirect("owner_application_status")
        set_active_ui(request, OWNER_UI)
        return view(request, *args, **kwargs)

    return wrapped


def admin_ui_required(view):
    """Platform admins and superusers can review owner applications."""
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_admin_role or request.user.is_superuser):
            return HttpResponseForbidden("Administrator access is required.")
        return view(request, *args, **kwargs)

    return wrapped
