from django.http import Http404
from django.shortcuts import render
from account.decorators import customer_ui_required

from .data import RESTAURANTS, get_restaurant


@customer_ui_required
def restaurants_view(request):
    query = request.GET.get("q", "").strip()
    restaurants = RESTAURANTS
    if query:
        restaurants = [
            place
            for place in RESTAURANTS
            if query.casefold()
            in f"{place['name']} {place['type']} {place['address']}".casefold()
        ]
    return render(
        request,
        "restaurants/restaurants.html",
        {"restaurants": restaurants, "query": query},
    )


@customer_ui_required
def restaurant_detail_view(request, slug):
    restaurant = get_restaurant(slug)
    if restaurant is None:
        raise Http404("Restaurant not found")
    return render(
        request, "restaurants/restaurant_detail.html", {"restaurant": restaurant}
    )
