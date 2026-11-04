from django.contrib import messages
from django.shortcuts import get_object_or_404,redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from account.decorators import customer_ui_required, owner_ui_required
from account.ui import get_landing_url_name

from restaurants import services
from restaurants.forms import RestaurantForm
from restaurants.models import Restaurant

@customer_ui_required
def home_view(request):
    categories = [
        ("restaurant", "Restaurants", "Discover handpicked menus"),
        ("coffee", "Cafés", "Slow down and enjoy the moment"),
        ("spa", "Wellness", "Relax and recharge with ease"),
        ("service", "More services", "Book everything in one place"),
    ]
    favourites = [
        {
            "slug": r.slug,
            "name": r.name,
            "type": f"{r.category} · {r.type}" if r.type else r.category,
            "image": r.image,
            "rating": r.rating,
            "reviews": r.reviews,
        }
        for r in Restaurant.objects.published().order_by("-rating", "id")[:3]
    ]
    return render(request, "dashboard/home.html", {"categories": categories, "favourites": favourites})

def welcome_view(request):
    if request.user.is_authenticated:
        return redirect(get_landing_url_name(request))
    return render(request, 'dashboard/welcome.html')


@owner_ui_required
def owner_dashboard_view(request):
    stores_data = [
        {
            "id": s.slug,  # JS เดิมใช้ store.id อยู่ จึงใส่ slug ลงช่องนี้
            "slug": s.slug,
            "name": s.name,
            "category": s.category,
            "price": s.price,
            "address": s.address,
            "hours": s.hours,
            "image": s.image,
            "description": s.description,
            "status": s.status,
            "isOpen": s.is_open,
            "extras": s.extra_details,
            "urls": {
                "edit": reverse("owner_store_update", args=[s.slug]),
                "status": reverse("owner_store_status", args=[s.slug]),
                "delete": reverse("owner_store_delete", args=[s.slug]),
            },
        }
        for s in request.user.restaurants.all()
    ]
    return render(request, "dashboard/owner_dashboard.html", {"stores_data": stores_data})

def _form_error_message(form):
    """รวมข้อความ error ของ form เป็นบรรทัดเดียวสำหรับ messages"""
    parts = []
    for field, errors in form.errors.items():
        label = "ข้อมูล" if field == "__all__" else form.fields[field].label or field
        parts.append(f"{label}: {' '.join(errors)}")
    return "กรอกข้อมูลไม่ถูกต้อง · " + " · ".join(parts)


def _get_store(request, slug):
    return get_object_or_404(services.managed_restaurants(request.user), slug=slug)


@owner_ui_required
@require_POST
def store_create(request):
    form = RestaurantForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_error_message(form))
        return redirect("owner_dashboard")

    cd = form.cleaned_data
    try:
        restaurant = services.create_restaurant(
            request.user,
            cd,
            extra_details=cd["extras"],
            table_count=cd["table_count"],
            seats=cd["seats_per_table"],
        )
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"สร้างร้าน {restaurant.name} เป็นฉบับร่างแล้ว")
    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_update(request, slug):
    restaurant = _get_store(request, slug)
    form = RestaurantForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_error_message(form))
        return redirect("owner_dashboard")

    cd = form.cleaned_data
    try:
        services.update_restaurant(
            restaurant, request.user, cd, extra_details=cd["extras"]
        )
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"บันทึกร้าน {restaurant.name} แล้ว")
    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_status(request, slug):
    restaurant = _get_store(request, slug)
    is_open = request.POST.get("is_open")
    try:
        services.set_status(
            restaurant,
            request.user,
            status=request.POST.get("status") or None,
            is_open=None if is_open is None else is_open == "1",
        )
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"อัปเดตสถานะร้าน {restaurant.name} แล้ว")
    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_delete(request, slug):
    restaurant = _get_store(request, slug)
    try:
        services.delete_restaurant(restaurant, request.user)
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "ลบร้านแล้ว")
    return redirect("owner_dashboard")