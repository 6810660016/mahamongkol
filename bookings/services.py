import calendar
from datetime import time

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from restaurants.models import Restaurant

from .models import Booking

SLOTS = ("11:30", "13:00", "17:30", "19:00", "20:30")
MAX_GUESTS = 12
INVALID_INPUT_MESSAGE = "Please choose a valid date, time and party size."
# Customers may book from today up to this many months ahead. Override it with
# BOOKING_MAX_ADVANCE_MONTHS in settings.py.
DEFAULT_ADVANCE_MONTHS = 1


class BookingError(Exception):
    """A booking could not be made or changed; the message is safe to show."""


def advance_months():
    """How many months ahead a customer may book."""
    return getattr(settings, "BOOKING_MAX_ADVANCE_MONTHS", DEFAULT_ADVANCE_MONTHS)


def add_months(day, months):
    """Same day number `months` later, or the month's last day if it is shorter."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def booking_window(today=None):
    """The first and last dates a customer can book, both inclusive."""
    today = today or timezone.localdate()
    return today, add_months(today, advance_months())


def parse_slot(value):
    """Return a time for one of the allowed slots, otherwise None."""
    if value not in SLOTS:
        return None
    return time.fromisoformat(value)


def can_manage(user, restaurant):
    """Admins manage every restaurant; owners manage only their own."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_admin_role:
        return True
    return user.is_owner_role and restaurant.owner_id == user.id


def booked_table_ids(restaurant, day, slot):
    """Ids of this restaurant's tables that are already booked at that time."""
    return set(
        Booking.objects.filter(
            table__restaurant=restaurant,
            date=day,
            time=slot,
            status=Booking.Status.CONFIRMED,
        ).values_list("table_id", flat=True)
    )


def create_booking(user, restaurant, day, slot_value, guests):
    """Reserve the smallest free table that fits the party."""
    if restaurant.status != Restaurant.Status.PUBLISHED or not restaurant.is_open:
        raise BookingError("ร้านนี้ปิดรับจองชั่วคราว")
    
    slot = parse_slot(slot_value)
    earliest, latest = booking_window()
    if slot is None or day < earliest or not 1 <= guests <= MAX_GUESTS:
        raise BookingError(INVALID_INPUT_MESSAGE)
    if day > latest:
        months = advance_months()
        raise BookingError(
            f"Bookings are open up to {latest:%Y-%m-%d} "
            f"({months} month{'s' if months != 1 else ''} ahead). "
            "Please choose an earlier date."
        )

    for _ in range(3):
        table = (
            restaurant.tables.exclude(id__in=booked_table_ids(restaurant, day, slot))
            .filter(capacity__gte=guests)
            .order_by("capacity", "name")
            .first()
        )
        if table is None:
            raise BookingError("Sorry, no table is free at that time. Please try another time.")
        try:
            with transaction.atomic():
                return Booking.objects.create(
                    user=user, table=table, date=day, time=slot, guests=guests
                )
        except IntegrityError:
            continue
    raise BookingError("That table was just taken. Please try again.")


def cancel_booking(booking, by_user):
    """Cancel a booking. Its owner, the restaurant's owner or an admin may do it."""
    if booking.user_id != by_user.id and not can_manage(by_user, booking.restaurant):
        raise BookingError("You are not allowed to cancel this booking.")
    if booking.status != Booking.Status.CANCELLED:
        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=["status", "cancelled_at"])
    return booking
