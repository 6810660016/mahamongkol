import calendar
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from restaurants.models import Restaurant

from .models import Booking

SLOTS = ("11:30", "13:00", "17:30", "19:00", "20:30")
MAX_GUESTS = 12
INVALID_INPUT_MESSAGE = "Please choose a valid date, time and party size."
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
    """Cancel a confirmed booking. Its owner, the restaurant's owner or an admin may do it."""
    if booking.user_id != by_user.id and not can_manage(by_user, booking.restaurant):
        raise BookingError("You are not allowed to cancel this booking.")
    if booking.status == Booking.Status.CANCELLED:
        return booking
    if booking.status != Booking.Status.CONFIRMED:
        raise BookingError("Only a confirmed booking can be cancelled.")
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])
    return booking


def booking_starts_at(booking):
    """The booking's date and time as an aware datetime in the project time zone."""
    return timezone.make_aware(datetime.combine(booking.date, booking.time))


def mark_no_shows(restaurant=None, user=None, now=None):
    """Turn confirmed bookings into no-shows once the restaurant's grace period is over.

    There is no background worker: this runs whenever a booking page is opened and
    from `manage.py mark_no_shows`. It is idempotent and only touches confirmed
    bookings. `restaurant` and `user` narrow which bookings are checked.
    Returns how many bookings changed.
    """
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    candidates = Booking.objects.filter(
        status=Booking.Status.CONFIRMED, date__lte=today
    ).select_related("table__restaurant")
    if restaurant is not None:
        candidates = candidates.filter(table__restaurant=restaurant)
    if user is not None:
        candidates = candidates.filter(user=user)

    overdue = [
        booking.pk
        for booking in candidates
        if booking_starts_at(booking)
        + timedelta(minutes=booking.table.restaurant.no_show_grace_minutes)
        < now
    ]
    if not overdue:
        return 0
    return Booking.objects.filter(
        pk__in=overdue, status=Booking.Status.CONFIRMED
    ).update(status=Booking.Status.NO_SHOW)


def can_complete(booking, now=None):
    """Whether the owner may mark this booking as completed right now.

    A confirmed booking can be completed from the start of its booking day
    (so a guest who arrives early is fine), never before. A no-show can be
    turned into completed only until the end of its booking day. Days are in
    the project time zone.
    """
    today = timezone.localtime(now or timezone.now()).date()
    if booking.status == Booking.Status.CONFIRMED:
        return today >= booking.date
    if booking.status == Booking.Status.NO_SHOW:
        return today <= booking.date
    return False


def complete_booking(booking, by_user, now=None):
    """Mark a booking as completed, recording who did it and when."""
    if not can_manage(by_user, booking.restaurant):
        raise BookingError("You are not allowed to complete this booking.")
    now = now or timezone.now()
    if booking.status == Booking.Status.COMPLETED:
        raise BookingError("This booking is already completed.")
    if booking.status == Booking.Status.CANCELLED:
        raise BookingError("A cancelled booking cannot be completed.")
    if booking.status == Booking.Status.CONFIRMED and not can_complete(booking, now):
        raise BookingError("This booking is not due yet.")
    if not can_complete(booking, now):
        raise BookingError("This no-show can no longer be changed to completed.")

    today = timezone.localtime(now).date()
    allowed = Q(status=Booking.Status.CONFIRMED, date__lte=today) | Q(
        status=Booking.Status.NO_SHOW, date__gte=today
    )
    with transaction.atomic():
        # The status filter makes the update win only once, even for simultaneous requests.
        changed = Booking.objects.filter(allowed, pk=booking.pk).update(
            status=Booking.Status.COMPLETED,
            completed_at=now,
            completed_by=by_user,
        )
    if not changed:
        booking.refresh_from_db()
        raise BookingError("This booking can no longer be completed.")
    booking.refresh_from_db()
    return booking


def bookings_for_day(restaurant, day):
    """Every booking of the restaurant on that day, cancelled ones included."""
    return (
        Booking.objects.filter(table__restaurant=restaurant, date=day)
        .select_related("user", "table")
        .order_by("time", "table__name")
    )
