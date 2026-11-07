from django.urls import path

from . import views

urlpatterns = [
    path("restaurants/", views.restaurants_view, name="restaurants"),
    path(
        "restaurants/<slug:slug>/",
        views.restaurant_detail_view,
        name="restaurant_detail",
    ),
    path(
        "restaurants/<slug:slug>/review/",
        views.restaurant_review_view,
        name="restaurant_review",
    ),
]
