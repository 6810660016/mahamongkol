"""Session-level UI selection, separate from account permissions."""

CUSTOMER_UI = "customer"
OWNER_UI = "owner"
ACTIVE_UI_SESSION_KEY = "active_ui"


def get_active_ui(request):
    if (
        request.user.is_authenticated
        and request.user.is_owner_role
        and request.session.get(ACTIVE_UI_SESSION_KEY) == OWNER_UI
    ):
        return OWNER_UI
    return CUSTOMER_UI


def get_landing_url_name(request):
    if request.user.is_authenticated and (request.user.is_admin_role or request.user.is_superuser):
        return "owner_applications_admin"
    return "owner_dashboard" if get_active_ui(request) == OWNER_UI else "home"


def set_active_ui(request, interface):
    request.session[ACTIVE_UI_SESSION_KEY] = interface
