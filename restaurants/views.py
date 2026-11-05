from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from account.decorators import customer_ui_required

from .models import Restaurant


@customer_ui_required
def restaurants_view(request):
    query = request.GET.get("q", "").strip()
    restaurants = Restaurant.objects.published()      # เปลี่ยนจาก .all()
    if query:
        restaurants = restaurants.filter(
            Q(name__icontains=query)
            | Q(type__icontains=query)
            | Q(address__icontains=query)
        )
    return render(
        request,
        "restaurants/restaurants.html",
        {"restaurants": restaurants, "query": query},
    )


@customer_ui_required
def restaurant_detail_view(request, slug):
    restaurant = get_object_or_404(Restaurant.objects.published(), slug=slug)   # เปลี่ยนจาก Restaurant
    return render(
        request, "restaurants/restaurant_detail.html", {"restaurant": restaurant}
    )