import secrets
import time

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.hashers import constant_time_compare
from django.core.mail import send_mail
from django.core.signing import salted_hmac
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from account.decorators import customer_ui_required
from .forms import NewPasswordForm, PasswordResetEmailForm, PasswordResetOTPForm, SignupForm

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
    if request.user.is_authenticated:
        return redirect("owner_dashboard" if request.user.is_owner_role else "home")

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
            destination = "owner_dashboard" if authenticated_user.is_owner_role else "home"
            return redirect(destination)
        error = "Email or password is incorrect. Please try again."

    password_changed = request.session.pop("password_reset_complete", False)
    return render(request, "account/login.html", {"error": error, "password_changed": password_changed})


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
    """Create a customer or owner account; staff accounts remain admin-managed."""
    if request.user.is_authenticated:
        return redirect("owner_dashboard" if request.user.is_owner_role else "home")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("owner_dashboard" if user.is_owner_role else "home")
    else:
        form = SignupForm()

    return render(request, "account/signup.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("welcome")


@customer_ui_required
def settings_view(request):
    if request.user.is_authenticated and request.user.is_owner_role:
        return redirect("owner_dashboard")
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

