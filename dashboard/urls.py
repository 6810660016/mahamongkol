from django.urls import path

from . import views

urlpatterns = [
    path("", views.welcome_view, name="welcome"),
    path("home/", views.home_view, name="home"),
    path("owner/", views.owner_dashboard_view, name="owner_dashboard"),
]
