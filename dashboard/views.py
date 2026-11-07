from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from account.decorators import customer_ui_required, owner_ui_required
from account.ui import get_landing_url_name

from bookings import services as booking_services
from bookings.models import Booking
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
                "edit": reverse(
                    "owner_store_update",
                    args=[store.slug],
                ),
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
    return render(request, "dashboard/owner_overview.html")


@owner_ui_required
def owner_store_details_view(request):
    return render(request, "dashboard/owner_store_details.html")


_COMPLETE_ERRORS = {
    "This booking is already completed.": "การจองนี้เสร็จสิ้นไปแล้ว",
    "A cancelled booking cannot be completed.": "การจองที่ยกเลิกแล้วไม่สามารถเปลี่ยนเป็นเสร็จสิ้นได้",
    "This booking is not due yet.": "ยังไม่ถึงวันที่จอง จึงยังเปลี่ยนเป็นเสร็จสิ้นไม่ได้",
    "This no-show can no longer be changed to completed.": "เลยวันที่จองแล้ว ไม่สามารถเปลี่ยน No Show เป็นเสร็จสิ้นได้",
    "This booking can no longer be completed.": "ไม่สามารถเปลี่ยนสถานะการจองนี้ได้",
    "You are not allowed to complete this booking.": "คุณไม่มีสิทธิ์จัดการการจองนี้",
}


def _booking_code(booking):
    return booking.code


def _bookings_url(day):
    return f"{reverse('owner_bookings')}?{urlencode({'date': day.isoformat()})}"


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
                    "id": _booking_code(booking),
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
        messages.success(request, f"ยกเลิกการจอง {_booking_code(booking)} แล้ว")

    return redirect(_bookings_url(booking.date))


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
        messages.error(request, _COMPLETE_ERRORS.get(str(exc), str(exc)))
    else:
        messages.success(request, f"บันทึกการจอง {_booking_code(booking)} เป็นเสร็จสิ้นแล้ว")

    return redirect(_bookings_url(booking.date))


@owner_ui_required
def owner_queue_view(request):
    """Queue management page; the live data comes from the queues JSON endpoints."""
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    return render(request, "dashboard/owner_queue.html", {"restaurant": restaurant})


def _form_error_message(form):
    """รวมข้อความ error ของ form เป็นบรรทัดเดียวสำหรับ messages"""
    parts = []

    for field, errors in form.errors.items():
        if field == "__all__":
            label = "ข้อมูล"
        else:
            label = form.fields[field].label or field

        parts.append(f"{label}: {' '.join(errors)}")

    return "กรอกข้อมูลไม่ถูกต้อง · " + " · ".join(parts)


def _get_store(request, slug):
    return get_object_or_404(
        services.managed_restaurants(request.user),
        slug=slug,
    )


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
        messages.success(
            request,
            f"สร้างร้าน {restaurant.name} เป็นฉบับร่างแล้ว",
        )

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
        messages.success(
            request,
            f"อัปเดตสถานะร้าน {restaurant.name} แล้ว",
        )

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