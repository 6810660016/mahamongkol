import calendar
import re
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
PAST_TIME_MESSAGE = "That time has already passed. Please choose a later time."
FULL_MESSAGE = "This time is fully booked (เต็ม). Please choose another time."
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


def slot_times_for_day(restaurant, day):
    """Every time the owner should see on that date, as sorted "HH:MM" strings.

    The restaurant's configured times for the date (default times when it set none),
    plus any time that already has a booking, so nothing booked ever disappears from view.
    """
    custom = day_slots(restaurant, day)
    times = {f"{t:%H:%M}" for t, *_ in custom} if custom is not None else set(SLOTS)
    booked = Booking.objects.filter(table__restaurant=restaurant, date=day)
    times |= {f"{t:%H:%M}" for t in booked.values_list("time", flat=True)}
    return sorted(times)


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


def day_slots(restaurant, day):
    """The owner's slots for one date as (time, tables, seats, available) tuples, or None.

    A schedule set for that exact date (from the calendar) wins over the restaurant's
    usual slots; None means the owner set nothing, so the default times and tables apply.
    """
    for rows in (
        restaurant.booking_slot_dates.filter(date=day),
        restaurant.booking_slots.all(),
    ):
        slots = [
            (row.time, row.table_count, row.seats_per_table, row.is_available) for row in rows
        ]
        if slots:
            return slots
    return None


def uses_custom_slots(restaurant, day=None):
    """True once the owner has set up their own time slots (otherwise the default slots apply)."""
    if day is not None:
        return day_slots(restaurant, day) is not None
    return (
        restaurant.booking_slots.exists() or restaurant.booking_slot_dates.exists()
    )


def is_past_slot(day, slot_time, now=None):
    """Whether this date and time has already started, in the project time zone."""
    local = timezone.localtime(now or timezone.now())
    if day != local.date():
        return day < local.date()
    return slot_time <= local.time().replace(second=0, microsecond=0)


def slot_options(restaurant, day, guests=None, now=None):
    """Every time the customer could pick on `day`, with how many tables are left.

    `state` is open, full, past (already started) or too_large (the party does not fit
    one table at that time). Used for both the booking page and its JSON endpoint.
    """
    custom = day_slots(restaurant, day)
    if custom is not None:
        slots = [(t, count, seats) for t, count, seats, available in custom if available]
    else:
        tables = list(restaurant.tables.all())
        slots = [(parse_slot(value), None, None) for value in SLOTS]

    options = []
    for slot_time, table_count, seats in slots:
        booked = booked_table_ids(restaurant, day, slot_time)
        if table_count is not None:
            remaining = max(0, table_count - len(booked))
            too_large = bool(guests) and guests > seats
        else:
            free = [t for t in tables if t.id not in booked]
            remaining = len(free)
            too_large = bool(guests) and not any(t.capacity >= guests for t in free) and remaining > 0
        if is_past_slot(day, slot_time, now):
            state = "past"
        elif remaining == 0:
            state = "full"
        elif too_large:
            state = "too_large"
        else:
            state = "open"
        options.append(
            {
                "value": f"{slot_time:%H:%M}",
                "seats": seats,
                "remaining": remaining,
                "state": state,
            }
        )
    return options


def _natural_key(name):
    """T2 before T10: split digits out so names sort the way people read them."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def _free_table(restaurant, booked, guests):
    """The smallest free table that seats the party (ties: natural name order), or None."""
    fitting = restaurant.tables.filter(capacity__gte=guests).exclude(id__in=booked)
    return min(fitting, key=lambda t: (t.capacity, _natural_key(t.name)), default=None)


def _next_table(restaurant, seats):
    """Add a table for slot bookings when the restaurant has fewer tables than a slot needs."""
    number = restaurant.tables.count() + 1
    while restaurant.tables.filter(name=f"T{number}").exists():
        number += 1
    return restaurant.tables.create(name=f"T{number}", capacity=seats)


def _create_slot_booking(user, restaurant, day, slot_value, guests):
    """Book one of the owner's configured time slots: N tables of S seats each."""
    try:
        slot_time = time.fromisoformat(slot_value)
    except (TypeError, ValueError):
        raise BookingError(INVALID_INPUT_MESSAGE) from None
    try:
        with transaction.atomic():
            # Locking the restaurant row makes simultaneous bookings count one at a time.
            Restaurant.objects.select_for_update().get(pk=restaurant.pk)
            match = next(
                (
                    (count, seats)
                    for t, count, seats, available in day_slots(restaurant, day) or ()
                    if t == slot_time and available
                ),
                None,
            )
            if match is None or not 1 <= guests <= MAX_GUESTS:
                raise BookingError(INVALID_INPUT_MESSAGE)
            table_count, seats_per_table = match
            if is_past_slot(day, slot_time):
                raise BookingError(PAST_TIME_MESSAGE)
            if guests > seats_per_table:
                raise BookingError(f"Tables at this time seat up to {seats_per_table} guests.")
            booked = booked_table_ids(restaurant, day, slot_time)
            if len(booked) >= table_count:
                raise BookingError(FULL_MESSAGE)
            table = _free_table(restaurant, booked, guests) or _next_table(
                restaurant, seats_per_table
            )
            return Booking.objects.create(
                user=user, table=table, date=day, time=slot_time, guests=guests
            )
    except IntegrityError:
        raise BookingError("That table was just taken. Please try again.") from None


def create_booking(user, restaurant, day, slot_value, guests):
    """Reserve a table: the owner's time slots when set up, else the smallest free table."""
    if restaurant.status != Restaurant.Status.PUBLISHED or not restaurant.is_open:
        raise BookingError("ร้านนี้ปิดรับจองชั่วคราว")
    if not restaurant.accepts_bookings:
        raise BookingError("This restaurant does not take table bookings. Join the queue instead.")

    custom = uses_custom_slots(restaurant, day)
    if custom:
        try:
            slot = time.fromisoformat(slot_value)
        except (TypeError, ValueError):
            slot = None
    else:
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
    if custom:
        return _create_slot_booking(user, restaurant, day, slot_value, guests)
    if is_past_slot(day, slot):
        raise BookingError(PAST_TIME_MESSAGE)

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
