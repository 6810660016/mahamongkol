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
]
