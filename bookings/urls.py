from django.urls import path

from . import views

urlpatterns = [
    path("book/<slug:slug>/", views.booking_view, name="booking"),
    path("my-queues/", views.my_queues_view, name="my_queues"),
    path(
        "cancel-booking/<int:booking_id>/",
        views.cancel_booking_view,
        name="cancel_booking",
    ),
    path("manage/", views.manage_restaurants_view, name="manage_restaurants"),
    path(
        "manage/cancel/<int:booking_id>/",
        views.manage_cancel_view,
        name="manage_cancel",
    ),
    path("manage/<slug:slug>/", views.manage_bookings_view, name="manage_bookings"),
]
