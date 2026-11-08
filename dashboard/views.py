from datetime import date

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from account.decorators import customer_ui_required, owner_ui_required
from account.ui import get_landing_url_name
from bookings import services as booking_services
from bookings.models import Booking
from dashboard import owner_bookings, stats, store_details, store_management
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

    return render(
        request,
        "dashboard/home.html",
        {
            "categories": categories,
            "favourites": favourites,
        },
    )


def welcome_view(request):
    if request.user.is_authenticated:
        return redirect(get_landing_url_name(request))

    return render(request, "dashboard/welcome.html")


@owner_ui_required
def owner_dashboard_view(request):
    stores_data = [
        {
            "id": store.slug,
            "slug": store.slug,
            "name": store.name,
            "category": store.category,
            "price": store.price,
            "address": store.address,
            "hours": store.hours,
            "noShowGraceMinutes": store.no_show_grace_minutes,
            "image": store.image,
            "description": store.description,
            "status": store.status,
            "isOpen": store.is_open,
            "serviceMode": store.service_mode,
            "extras": store.extra_details,
            "urls": {
                # 1 บัญชี = 1 ร้าน หน้า Store Details จึงไม่ต้องใช้ slug
                "details": reverse("owner_store_details"),
                "status": reverse(
                    "owner_store_status",
                    args=[store.slug],
                ),
                "delete": reverse(
                    "owner_store_delete",
                    args=[store.slug],
                ),
            },
        }
        for store in Restaurant.objects.filter(owner=request.user)
    ]

    return render(
        request,
        "dashboard/owner_dashboard.html",
        {"stores_data": stores_data},
    )


@owner_ui_required
def owner_overview_view(request):
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    days = stats.parse_range(request.GET.get("range"))
    context = {
        "restaurant": restaurant,
        "stats": stats.owner_overview_stats(restaurant, days),
    }
    return render(request, "dashboard/owner_overview.html", context)


@owner_ui_required
def owner_store_details_view(request):
    restaurant = Restaurant.objects.filter(owner=request.user).first()

    if request.method == "POST":
        return store_details.save_store_details(request, restaurant)

    return store_details.render_store_details(request, restaurant)


@owner_ui_required
def owner_bookings_view(request):
    """Real bookings of the owner's store for one day (?date=YYYY-MM-DD)."""
    restaurant = Restaurant.objects.filter(owner=request.user).first()

    try:
        day = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        day = timezone.localdate()

    bookings_data = []
    if restaurant is not None:
        # ไม่มี background worker: อัปเดต No Show ของร้านนี้ทุกครั้งที่เปิดหน้า
        booking_services.mark_no_shows(restaurant=restaurant)
        now = timezone.now()
        for booking in booking_services.bookings_for_day(restaurant, day):
            bookings_data.append(
                {
                    "id": owner_bookings.booking_code(booking),
                    "time": f"{booking.time:%H:%M}",
                    "name": booking.user.get_full_name() or booking.user.username,
                    "party": booking.guests,
                    "table": booking.table.name,
                    "status": booking.status,
                    "canCancel": booking.status == Booking.Status.CONFIRMED,
                    "canComplete": booking_services.can_complete(booking, now),
                    "cancelUrl": reverse("owner_booking_cancel", args=[booking.id]),
                    "completeUrl": reverse("owner_booking_complete", args=[booking.id]),
                }
            )

    return render(
        request,
        "dashboard/owner_bookings.html",
        {
            "restaurant": restaurant,
            "selected_date": day.isoformat(),
            "bookings_data": bookings_data,
        },
    )


@owner_ui_required
@require_POST
def owner_booking_cancel_view(request, booking_id):
    # การจองของร้านอื่น (หรือเจ้าของที่ไม่มีร้าน) จะได้ 404
    booking = get_object_or_404(
        Booking.objects.select_related("table__restaurant", "user"),
        pk=booking_id,
        table__restaurant__owner=request.user,
    )

    try:
        booking_services.cancel_booking(booking, request.user)
    except booking_services.BookingError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"ยกเลิกการจอง {owner_bookings.booking_code(booking)} แล้ว")

    return redirect(owner_bookings.bookings_url(booking.date))


@owner_ui_required
@require_POST
def owner_booking_complete_view(request, booking_id):
    # การจองของร้านอื่น (หรือเจ้าของที่ไม่มีร้าน) จะได้ 404
    booking = get_object_or_404(
        Booking.objects.select_related("table__restaurant", "user"),
        pk=booking_id,
        table__restaurant__owner=request.user,
    )

    # อัปเดต No Show ก่อน เพื่อให้ตรวจสถานะจากข้อมูลล่าสุด
    booking_services.mark_no_shows(restaurant=booking.table.restaurant)
    booking.refresh_from_db()

    try:
        booking_services.complete_booking(booking, request.user)
    except booking_services.BookingError as exc:
        messages.error(request, owner_bookings.COMPLETE_ERRORS.get(str(exc), str(exc)))
    else:
        messages.success(request, f"บันทึกการจอง {owner_bookings.booking_code(booking)} เป็นเสร็จสิ้นแล้ว")

    return redirect(owner_bookings.bookings_url(booking.date))


@owner_ui_required
def owner_queue_view(request):
    """Queue management page; the live data comes from the queues JSON endpoints."""
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    return render(request, "dashboard/owner_queue.html", {"restaurant": restaurant})


@owner_ui_required
def owner_slots_view(request):
    """JSON: รอบเวลาของวันที่เลือกจากปฏิทินบนหน้า Store Details (?date=YYYY-MM-DD)"""
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    if restaurant is None:
        return JsonResponse({"error": "no store"}, status=404)
    day = store_details.parse_slots_day(request.GET.get("date", ""))
    if day is None:
        return JsonResponse({"error": "วันที่อยู่นอกช่วงที่ลูกค้าจองได้"}, status=400)
    rows, source = store_details.day_slot_rows(restaurant, day)
    return JsonResponse({"date": day.isoformat(), "source": source, "rows": rows})


@owner_ui_required
@require_POST
def store_create(request):
    form = RestaurantForm(request.POST)

    if not form.is_valid():
        messages.error(request, store_management.form_error_message(form))
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
        messages.success(
            request,
            f"สร้างร้าน {restaurant.name} เป็นฉบับร่างแล้ว",
        )

    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_update(request, slug):
    restaurant = store_management.get_store(request, slug)
    form = RestaurantForm(request.POST)

    if not form.is_valid():
        messages.error(request, store_management.form_error_message(form))
        return redirect("owner_dashboard")

    cd = form.cleaned_data

    try:
        services.update_restaurant(
            restaurant,
            request.user,
            cd,
            extra_details=cd["extras"],
        )
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"บันทึกร้าน {restaurant.name} แล้ว")

    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_status(request, slug):
    restaurant = store_management.get_store(request, slug)
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
        messages.success(
            request,
            f"อัปเดตสถานะร้าน {restaurant.name} แล้ว",
        )

    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_delete(request, slug):
    restaurant = store_management.get_store(request, slug)

    try:
        services.delete_restaurant(restaurant, request.user)
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "ลบร้านแล้ว")

    return redirect("owner_dashboard")