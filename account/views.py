from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_http_methods

from .decorators import admin_ui_required, customer_ui_required
from .forms import OwnerApplicationForm, OwnerSignupForm, SignupForm
from .models import OwnerApplication, User
from .ui import CUSTOMER_UI, OWNER_UI, get_landing_url_name, set_active_ui


def login_view(request):
    """Authenticate users and direct them to the UI for their account role."""
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
        next_url = ""
    if request.user.is_authenticated:
        return redirect(next_url or get_landing_url_name(request))

    error = ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=email).first()
        authenticated_user = (
            authenticate(request, username=user.get_username(), password=password)
            if user
            else None
        )
        if authenticated_user is not None:
            login(request, authenticated_user)
            if request.POST.get("remember") != "on":
                request.session.set_expiry(0)
            return redirect(next_url or get_landing_url_name(request))
        error = "Email or password is incorrect. Please try again."

    return render(request, "account/login.html", {"error": error, "next_url": next_url})


def signup_view(request):
    """Register a customer account; owner access is requested separately."""
    if request.user.is_authenticated:
        return redirect(get_landing_url_name(request))

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = SignupForm()

    return render(request, "account/signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def owner_signup_view(request):
    """Apply using an existing account, or create one customer account and apply."""
    if request.user.is_authenticated:
        if request.user.is_admin_role or request.user.is_superuser:
            return redirect("owner_applications_admin")
        if request.user.is_owner_role:
            set_active_ui(request, OWNER_UI)
            return redirect("owner_dashboard")
        if OwnerApplication.objects.filter(user=request.user).exists():
            return redirect("owner_application_status")
        form_class = OwnerApplicationForm
    else:
        form_class = OwnerSignupForm

    form = form_class(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = request.user if request.user.is_authenticated else form.save()
            OwnerApplication.objects.get_or_create(
                user=user,
                defaults={
                    "contact_name": form.cleaned_data["contact_name"],
                    "business_name": form.cleaned_data["business_name"],
                },
            )
        if not request.user.is_authenticated:
            login(request, user)
        set_active_ui(request, CUSTOMER_UI)
        return redirect("owner_application_status")

    return render(request, "account/owner_signup.html", {"form": form})


@login_required(login_url="login")
def owner_application_status_view(request):
    application = OwnerApplication.objects.filter(user=request.user).first()
    if not application and not request.user.is_owner_role:
        return redirect("owner_signup")
    return render(request, "account/owner_application_status.html", {
        "application": application,
        "owner_approved": request.user.is_owner_role,
    })


@admin_ui_required
def owner_applications_admin_view(request):
    status = request.GET.get("status", "pending")
    if status not in ("pending", "approved", "all"):
        status = "pending"
    query = request.GET.get("q", "").strip()[:160]
    applications = OwnerApplication.objects.select_related("user", "reviewed_by")
    if status != "all":
        applications = applications.filter(status=status)
    if query:
        applications = applications.filter(
            Q(contact_name__icontains=query) | Q(business_name__icontains=query)
            | Q(user__email__icontains=query) | Q(user__username__icontains=query)
        )
    return render(request, "account/admin_owner_applications.html", {
        "applications": applications,
        "active_status": status,
        "query": query,
        "pending_count": OwnerApplication.objects.filter(status=OwnerApplication.Status.PENDING).count(),
        "approved_count": OwnerApplication.objects.filter(status=OwnerApplication.Status.APPROVED).count(),
    })


@admin_ui_required
@require_POST
def approve_owner_application_view(request, application_id):
    with transaction.atomic():
        application = get_object_or_404(
            OwnerApplication.objects.select_for_update(), pk=application_id,
        )
        if application.status == OwnerApplication.Status.PENDING:
            User.objects.filter(pk=application.user_id, role=User.Role.USER).update(role=User.Role.OWNER)
            application.status = OwnerApplication.Status.APPROVED
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            messages.success(request, f"{application.business_name} has been approved. Owner access is now available.")
        else:
            messages.info(request, "This application has already been approved.")
    return redirect("owner_applications_admin")


@require_POST
def logout_view(request):
    logout(request)
    return redirect("welcome")


@login_required(login_url="login")
@require_POST
def switch_ui_view(request):
    interface = request.POST.get("interface")
    if interface not in (CUSTOMER_UI, OWNER_UI):
        return HttpResponseBadRequest("Unknown interface.")
    if interface == OWNER_UI and not request.user.is_owner_role:
        return HttpResponseForbidden("Owner access requires administrator approval.")
    set_active_ui(request, interface)
    return redirect(get_landing_url_name(request))


@customer_ui_required
def settings_view(request):
    settings = request.session.get('site_settings', {
        'name': 'Guest Member',
        'email': '',
        'language': 'English',
        'currency': 'THB',
        'time_format': '12-hour',
        'reservation_updates': True,
        'reminders': True,
        'offers': False,
    })
    saved = False
    if request.method == 'POST':
        language = request.POST.get('language', 'English')
        currency = request.POST.get('currency', 'THB')
        time_format = request.POST.get('time_format', '12-hour')
        settings = {
            'name': request.POST.get('name', '').strip()[:80] or 'Guest Member',
            'email': request.POST.get('email', '').strip()[:254],
            'language': language if language in ('English', 'Thai') else 'English',
            'currency': currency if currency in ('THB', 'USD') else 'THB',
            'time_format': time_format if time_format in ('12-hour', '24-hour') else '12-hour',
            'reservation_updates': request.POST.get('reservation_updates') == 'on',
            'reminders': request.POST.get('reminders') == 'on',
            'offers': request.POST.get('offers') == 'on',
        }
        request.session['site_settings'] = settings
        saved = True
    return render(request, 'account/settings.html', {'settings': settings, 'saved': saved})

