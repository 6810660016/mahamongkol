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


def welcome_view(request):
    return render(request, "account/welcome.html")
