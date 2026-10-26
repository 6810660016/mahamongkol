from django.urls import path

from . import views

urlpatterns = [
    path("", views.welcome_view, name="welcome"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("welcome/", views.welcome_view, name="welcome"),
]
