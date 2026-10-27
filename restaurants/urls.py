from django.urls import path

from . import views

urlpatterns = [
    path("restaurants/", views.restaurants_view, name="restaurants"),
    path(
        "restaurants/<slug:slug>/",
        views.restaurant_detail_view,
        name="restaurant_detail",
    ),
]
