import secrets
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import constant_time_compare
from django.core.mail import send_mail
from django.core.signing import salted_hmac
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_http_methods

from .forms import (
    NewPasswordForm,
    OwnerApplicationForm,
    OwnerSignupForm,
    PasswordResetEmailForm,
    PasswordResetOTPForm,
    SignupForm,
)

from .models import OwnerApplication, User
from .ui import CUSTOMER_UI, OWNER_UI, get_landing_url_name, set_active_ui
from .decorators import admin_ui_required, customer_ui_required


OTP_LIFETIME_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_DELAY_SECONDS = 60


def _otp_hash(email, otp):
    return salted_hmac(
        "account.password_reset_otp", f"{email}:{otp}", secret=settings.SECRET_KEY
    ).hexdigest()


def _send_reset_otp(email, otp):
    send_mail(
        "รหัส OTP สำหรับรีเซ็ตรหัสผ่าน Mahamongkol",
        f"รหัส OTP ของคุณคือ {otp}\nรหัสนี้ใช้ได้ 10 นาที หากคุณไม่ได้ร้องขอให้ละเว้นอีเมลนี้",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )


def _create_and_send_otp(request, email):
    otp = f"{secrets.randbelow(1_000_000):06d}"
    request.session["password_reset_email"] = email
    request.session["password_reset_otp_hash"] = _otp_hash(email, otp)
    request.session["password_reset_otp_expires"] = int(time.time()) + OTP_LIFETIME_SECONDS
    request.session["password_reset_otp_sent"] = int(time.time())
    request.session["password_reset_otp_attempts"] = 0
    request.session.pop("password_reset_verified_until", None)
    _send_reset_otp(email, otp)


def _clear_password_reset_session(request):
    for key in (
        "password_reset_email",
        "password_reset_otp_hash",
        "password_reset_otp_expires",
        "password_reset_otp_sent",
        "password_reset_otp_attempts",
        "password_reset_verified_until",
    ):
        request.session.pop(key, None)


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
    password_changed = request.session.pop("password_reset_complete", False)
    return render(request, "account/login.html", {"error": error, "password_changed": password_changed, "next_url": next_url})


def password_reset_view(request):
    if request.user.is_authenticated:
        return redirect("owner_dashboard" if request.user.is_owner_role else "home")
    form = PasswordResetEmailForm(request.POST or None)
    error = ""
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        if user:
            try:
                _create_and_send_otp(request, user.email)
            except Exception:
                _clear_password_reset_session(request)
                error = "ส่งอีเมลไม่สำเร็จ กรุณาตรวจสอบการตั้งค่าอีเมลแล้วลองอีกครั้ง"
                return render(request, "account/password_reset_form.html", {"form": form, "error": error})
        else:
            # Keep the response the same for known and unknown email addresses.
            request.session["password_reset_email"] = email
            request.session["password_reset_otp_hash"] = ""
            request.session["password_reset_otp_expires"] = int(time.time()) + OTP_LIFETIME_SECONDS
            request.session["password_reset_otp_sent"] = int(time.time())
            request.session["password_reset_otp_attempts"] = 0
        return redirect("password_reset_verify")
    return render(request, "account/password_reset_form.html", {"form": form, "error": error})


def password_reset_verify_view(request):
    email = request.session.get("password_reset_email")
    if not email:
        return redirect("password_reset")

    error = ""
    form = PasswordResetOTPForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("action") == "resend":
            sent_at = request.session.get("password_reset_otp_sent", 0)
            if time.time() - sent_at < OTP_RESEND_DELAY_SECONDS:
                error = "กรุณารอสักครู่ก่อนขอรหัสใหม่"
            else:
                user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
                if user:
                    try:
                        _create_and_send_otp(request, user.email)
                    except Exception:
                        error = "ส่งอีเมลไม่สำเร็จ กรุณาลองอีกครั้ง"
                else:
                    request.session["password_reset_otp_sent"] = int(time.time())
                    request.session["password_reset_otp_expires"] = int(time.time()) + OTP_LIFETIME_SECONDS
                if not error:
                    error = "ส่งรหัส OTP ใหม่แล้ว โปรดตรวจสอบอีเมลของคุณ"
        elif form.is_valid():
            if time.time() > request.session.get("password_reset_otp_expires", 0):
                error = "รหัส OTP หมดอายุแล้ว กรุณาขอรหัสใหม่"
            elif request.session.get("password_reset_otp_attempts", 0) >= OTP_MAX_ATTEMPTS:
                error = "ลองรหัสผิดหลายครั้งแล้ว กรุณาขอรหัสใหม่"
            elif not request.session.get("password_reset_otp_hash"):
                error = "ไม่สามารถยืนยันรหัส OTP ได้ กรุณาตรวจสอบข้อมูลหรือขอรหัสใหม่"
            elif constant_time_compare(
                _otp_hash(email, form.cleaned_data["otp"]),
                request.session["password_reset_otp_hash"],
            ):
                request.session["password_reset_verified_until"] = int(time.time()) + OTP_LIFETIME_SECONDS
                request.session["password_reset_otp_hash"] = ""
                return redirect("password_reset_new")
            else:
                request.session["password_reset_otp_attempts"] = request.session.get("password_reset_otp_attempts", 0) + 1
                error = "รหัส OTP ไม่ถูกต้อง กรุณาลองอีกครั้ง"

    return render(request, "account/password_reset_verify.html", {"form": form, "email": email, "error": error})


def password_reset_new_view(request):
    email = request.session.get("password_reset_email")
    verified_until = request.session.get("password_reset_verified_until", 0)
    if not email or time.time() > verified_until:
        _clear_password_reset_session(request)
        return redirect("password_reset")

    user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    if not user:
        _clear_password_reset_session(request)
        return redirect("password_reset")

    form = NewPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        _clear_password_reset_session(request)
        request.session["password_reset_complete"] = True
        return redirect("login")
    return render(request, "account/password_reset_new.html", {"form": form})


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

