from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def customer_ui_required(view):
    """Keep authenticated owner accounts inside their separate owner UI."""
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.is_owner_role:
            return redirect("owner_dashboard")
        return view(request, *args, **kwargs)

    return wrapped


def owner_ui_required(view):
    """Require a signed-in owner account for the owner workspace."""
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_owner_role:
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapped
