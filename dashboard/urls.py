from django.urls import path

from . import views

urlpatterns = [
    path("", views.welcome_view, name="welcome"),
    path("home/", views.home_view, name="home"),
    path("owner/", views.owner_dashboard_view, name="owner_dashboard"),
    path("owner/overview/", views.owner_overview_view, name="owner_overview"),
    path("owner/store-details/", views.owner_store_details_view, name="owner_store_details"),
    path("owner/bookings/", views.owner_bookings_view, name="owner_bookings"),
    path("owner/queue/", views.owner_queue_view, name="owner_queue"),
]
