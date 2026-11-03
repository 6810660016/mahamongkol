from django.urls import path

from . import views

urlpatterns = [
    path("", views.welcome_view, name="welcome"),
    path("home/", views.home_view, name="home"),
    path("owner/", views.owner_dashboard_view, name="owner_dashboard"),
    path("owner/stores/new/", views.store_create, name="owner_store_create"),
    path("owner/stores/<slug:slug>/edit/", views.store_update, name="owner_store_update"),
    path("owner/stores/<slug:slug>/delete/", views.store_delete, name="owner_store_delete"),
    path("owner/stores/<slug:slug>/status/", views.store_status, name="owner_store_status"),
]
