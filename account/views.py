from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import SignupForm


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

    return render(request, "account/login.html", {"error": error})


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

