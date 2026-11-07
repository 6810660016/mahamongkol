from django.urls import path

from . import views

urlpatterns = [
    path("", views.welcome_view, name="welcome"),
    path("home/", views.home_view, name="home"),
    path("owner/", views.owner_dashboard_view, name="owner_dashboard"),

    # Owner pages
    path("owner/overview/", views.owner_overview_view, name="owner_overview"),
    path(
        "owner/store-details/",
        views.owner_store_details_view,
        name="owner_store_details",
    ),
    path("owner/bookings/", views.owner_bookings_view, name="owner_bookings"),
    path(
        "owner/bookings/<int:booking_id>/cancel/",
        views.owner_booking_cancel_view,
        name="owner_booking_cancel",
    ),
    path(
        "owner/bookings/<int:booking_id>/complete/",
        views.owner_booking_complete_view,
        name="owner_booking_complete",
    ),
    path("owner/queue/", views.owner_queue_view, name="owner_queue"),

    # Store management
    path("owner/stores/new/", views.store_create, name="owner_store_create"),
    path(
        "owner/stores/<slug:slug>/edit/",
        views.store_update,
        name="owner_store_update",
    ),
    path(
        "owner/stores/<slug:slug>/delete/",
        views.store_delete,
        name="owner_store_delete",
    ),
    path(
        "owner/stores/<slug:slug>/status/",
        views.store_status,
        name="owner_store_status",
    ),
]