from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import SignupForm


def login_view(request):
    """Render the login screen; authentication can be connected later."""
    return render(request, "account/login.html")


def signup_view(request):
    """Customer sign up; staff (admin role) accounts are created in Django admin."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = SignupForm()

    return render(request, "account/signup.html", {"form": form})

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

