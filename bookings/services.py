from datetime import date as date_cls
from datetime import time

from django.db import IntegrityError, transaction
from django.utils import timezone

from restaurants.models import Restaurant

from .models import Booking

SLOTS = ("11:30", "13:00", "17:30", "19:00", "20:30")
MAX_GUESTS = 12
INVALID_INPUT_MESSAGE = "Please choose a valid date, time and party size."


class BookingError(Exception):
    """A booking could not be made or changed; the message is safe to show."""


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
    if slot is None or day < date_cls.today() or not 1 <= guests <= MAX_GUESTS:
        raise BookingError(INVALID_INPUT_MESSAGE)

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
