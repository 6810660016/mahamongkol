from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from account.decorators import customer_ui_required

from .models import Restaurant, Review


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


@customer_ui_required
@require_POST
def restaurant_review_view(request, slug):
    """Create or update the signed-in customer's review of a restaurant."""
    restaurant = get_object_or_404(Restaurant.objects.published(), slug=slug)
    try:
        rating = int(request.POST.get("rating", ""))
    except ValueError:
        rating = 0
    if not 1 <= rating <= 5:
        return JsonResponse({"error": "Please choose a rating from 1 to 5."}, status=400)
    message = request.POST.get("message", "").strip()[: Review.MAX_MESSAGE_LENGTH]
    review, created = Review.objects.update_or_create(
        restaurant=restaurant,
        user=request.user,
        defaults={"rating": rating, "message": message},
    )
    return JsonResponse(
        {"rating": review.rating, "message": review.message, "created": created}
    )
