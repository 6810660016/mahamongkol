from datetime import date
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from account.decorators import customer_ui_required
from restaurants.models import Restaurant

from . import services
from .models import Booking
from .permissions import manager_required

#Customer side

@customer_ui_required
def booking_view(request, slug):
    restaurant = get_object_or_404(Restaurant.objects.published(), slug=slug)
    if not restaurant.accepts_bookings:
        return redirect("restaurant_detail", slug=restaurant.slug)
    error = ""
    if request.method == "POST":
        try:
            day = date.fromisoformat(request.POST.get("date", ""))
            guests = int(request.POST.get("guests", "2"))
        except (TypeError, ValueError):
            error = services.INVALID_INPUT_MESSAGE
        else:
            try:
                services.create_booking(
                    request.user, restaurant, day, request.POST.get("time", ""), guests
                )
            except services.BookingError as exc:
                error = str(exc)
            else:
                return redirect("my_queues")
    min_date, max_date = services.booking_window()
    try:
        shown_day = date.fromisoformat(request.POST.get("date", ""))
    except ValueError:
        shown_day = min_date
    return render(
        request,
        "bookings/booking.html",
        {
            "restaurant": restaurant,
            "error": error,
            "shown_day": shown_day,
            "slot_options": services.slot_options(restaurant, shown_day),
            "selected_time": request.POST.get("time", ""),
            "min_date": min_date,
            "max_date": max_date,
        },
    )


@customer_ui_required
def booking_slots_view(request, slug):
    """JSON: the times of one day with how many tables are left (full / past are flagged)."""
    restaurant = get_object_or_404(Restaurant.objects.published(), slug=slug)
    if not restaurant.accepts_bookings:
        return JsonResponse({"error": "This restaurant does not take table bookings."}, status=404)
    try:
        day = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        return JsonResponse({"error": services.INVALID_INPUT_MESSAGE}, status=400)
    earliest, latest = services.booking_window()
    if not earliest <= day <= latest:
        return JsonResponse({"error": services.INVALID_INPUT_MESSAGE}, status=400)
    try:
        guests = int(request.GET.get("guests", "")) or None
    except ValueError:
        guests = None
    return JsonResponse({"slots": services.slot_options(restaurant, day, guests)})


QUEUE_TABS = {
    "upcoming": (Booking.Status.CONFIRMED,),
    "past": (Booking.Status.COMPLETED, Booking.Status.NO_SHOW),
    "cancelled": (Booking.Status.CANCELLED,),
}


@customer_ui_required
def my_queues_view(request):
    # ไม่มี background worker: อัปเดต No Show ของลูกค้าคนนี้ทุกครั้งที่เปิดหน้า
    services.mark_no_shows(user=request.user)

    tab = request.GET.get("tab", "upcoming")
    if tab not in QUEUE_TABS:
        tab = "upcoming"

    mine = Booking.objects.filter(user=request.user).select_related("table__restaurant")
    counts = {name: mine.filter(status__in=statuses).count() for name, statuses in QUEUE_TABS.items()}
    ordering = ("date", "time") if tab == "upcoming" else ("-date", "-time")
    bookings = mine.filter(status__in=QUEUE_TABS[tab]).order_by(*ordering)
    return render(
        request,
        "bookings/my_queues.html",
        {
            "bookings": bookings,
            "active_tab": tab,
            "tabs": [
                {"key": "upcoming", "label": "Upcoming", "count": counts["upcoming"]},
                {"key": "past", "label": "Past", "count": counts["past"]},
                {"key": "cancelled", "label": "Cancelled", "count": counts["cancelled"]},
            ],
        },
    )


@customer_ui_required
def cancel_booking_view(request, booking_id):
    booking = (
        Booking.objects.filter(
            pk=booking_id, user=request.user, status=Booking.Status.CONFIRMED
        )
        .select_related("table__restaurant")
        .first()
    )
    if booking is None:
        return redirect("my_queues")
    if request.method == "POST":
        services.cancel_booking(booking, request.user)
        return redirect("my_queues")
    return render(request, "bookings/cancel_booking.html", {"booking": booking})


#Management side (owners and admins)

def managed_restaurants(user):
    restaurants = Restaurant.objects.all()
    if user.is_superuser or user.is_admin_role:
        return restaurants
    return restaurants.filter(owner=user)


@manager_required
def manage_restaurants_view(request):
    return render(
        request,
        "bookings/manage_restaurants.html",
        {"restaurants": managed_restaurants(request.user)},
    )


@manager_required
def manage_bookings_view(request, slug):
    restaurant = get_object_or_404(managed_restaurants(request.user), slug=slug)

    try:
        day = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        day = timezone.localdate()
    slot_value = request.GET.get("time", "")
    if slot_value not in services.SLOTS:
        slot_value = services.SLOTS[0]
    slot = services.parse_slot(slot_value)

    booked = {
        booking.table_id: booking
        for booking in Booking.objects.filter(
            table__restaurant=restaurant,
            date=day,
            time=slot,
            status=Booking.Status.CONFIRMED,
        ).select_related("user")
    }
    
    rows = []
    for table in restaurant.tables.all():
        booking = booked.get(table.id)
        rows.append(
            {
                "table": table,
                "booking": booking,
                "status": "Booked" if booking else "Available",
            }
        )

    day_bookings = (
        Booking.objects.filter(table__restaurant=restaurant, date=day)
        .select_related("user", "table")
        .order_by("time", "table__name")
    )
    return render(
        request,
        "bookings/manage_bookings.html",
        {
            "restaurant": restaurant,
            "day": day,
            "slot": slot_value,
            "slots": services.SLOTS,
            "rows": rows,
            "booked_count": len(booked),
            "table_count": len(rows),
            "day_bookings": day_bookings,
        },
    )


@manager_required
@require_POST
def manage_cancel_view(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("table__restaurant"), pk=booking_id
    )
    try:
        services.cancel_booking(booking, request.user)
    except services.BookingError:
        raise PermissionDenied
    query = urlencode({"date": booking.date.isoformat(), "time": f"{booking.time:%H:%M}"})
    return redirect(
        f"{reverse('manage_bookings', args=[booking.restaurant.slug])}?{query}"
    )
