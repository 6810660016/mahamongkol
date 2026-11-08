"""Real statistics for the owner Service Home page (one store per owner)."""

from collections import Counter
from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone

from bookings import services as booking_services
from bookings.models import Booking
from queues.models import QueueEntry
from restaurants.models import Review

RANGE_CHOICES = (7, 30)
DEFAULT_RANGE = 7

# SVG plot area of the "bookings over time" chart (viewBox 0 0 600 170).
CHART_WIDTH = 600
CHART_TOP = 25
CHART_BOTTOM = 145
GUEST_BUCKETS = ("1–2", "3", "4", "5", "6+")


def parse_range(value):
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RANGE
    return days if days in RANGE_CHOICES else DEFAULT_RANGE


def _guest_bucket(guests):
    if guests <= 2:
        return GUEST_BUCKETS[0]
    if guests >= 6:
        return GUEST_BUCKETS[4]
    return str(guests)


def _percent(value, peak):
    return round(value / peak * 100) if peak else 0


def _chart(counts_by_day, days, today):
    dates = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    values = [counts_by_day.get(day, 0) for day in dates]
    # The axis shows four evenly spaced whole-number ticks: 0, 1/3, 2/3 and max.
    top = max(3, -(-max(values) // 3) * 3)
    span = CHART_BOTTOM - CHART_TOP
    step = CHART_WIDTH / (len(values) - 1)
    points = [
        (round(index * step, 1), round(CHART_BOTTOM - value / top * span, 1))
        for index, value in enumerate(values)
    ]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x} {y}" for i, (x, y) in enumerate(points))
    area = f"{line} L{CHART_WIDTH} 160 L0 160Z"
    label_every = 1 if days <= 7 else 5
    labels = [
        f"{day.day}/{day.month}" if (index % label_every == 0 or index == len(dates) - 1) else ""
        for index, day in enumerate(dates)
    ]
    return {
        "line": line,
        "area": area,
        "ticks": [top, top * 2 // 3, top // 3, 0],
        "labels": labels,
        "total": sum(values),
        "description": ", ".join(f"{d:%d %b}: {v}" for d, v in zip(dates, values)),
    }


MAX_POPULAR_BARS = 8


def _popular_slots(restaurant, slot_counts):
    """(time, bookings) bars: the store's own times (default times if it set none) plus any
    time that was actually booked. Beyond MAX_POPULAR_BARS keep the busiest, in time order."""
    configured = set()
    if restaurant is not None:
        configured |= {f"{t:%H:%M}" for t in restaurant.booking_slots.values_list("time", flat=True)}
        configured |= {
            f"{t:%H:%M}" for t in restaurant.booking_slot_dates.values_list("time", flat=True)
        }
    if not configured:
        configured = set(booking_services.SLOTS)
    times = sorted(configured | set(slot_counts))
    if len(times) > MAX_POPULAR_BARS:
        busiest = sorted(times, key=lambda t: (-slot_counts.get(t, 0), t))[:MAX_POPULAR_BARS]
        times = sorted(busiest)
    return [(t, slot_counts.get(t, 0)) for t in times]


def owner_overview_stats(restaurant, days=DEFAULT_RANGE, today=None):
    today = today or timezone.localdate()
    bookings = Booking.objects.filter(table__restaurant=restaurant) if restaurant else Booking.objects.none()
    queue = QueueEntry.objects.filter(restaurant=restaurant) if restaurant else QueueEntry.objects.none()

    active = bookings.exclude(status=Booking.Status.CANCELLED)
    total = bookings.count()
    cancelled = bookings.filter(status=Booking.Status.CANCELLED).count()

    since = today - timedelta(days=days - 1)
    per_day = dict(
        active.filter(date__range=(since, today))
        .values_list("date")
        .annotate(n=Count("id"))
        .values_list("date", "n")
    )

    slot_counts = Counter(f"{t:%H:%M}" for t in active.values_list("time", flat=True))
    slots = _popular_slots(restaurant, slot_counts)
    peak_slot = max((count for _, count in slots), default=0)

    guest_counts = Counter(_guest_bucket(g) for g in active.values_list("guests", flat=True))
    peak_guests = max(guest_counts.values(), default=0)

    # Total customers = distinct signed-in guests across bookings and the queue,
    # plus walk-in queue entries that have no account (each counts as one guest).
    live_queue = queue.exclude(status=QueueEntry.Status.CANCELLED)
    people = set(active.values_list("user_id", flat=True))
    people |= set(live_queue.filter(user__isnull=False).values_list("user_id", flat=True))
    walk_ins = live_queue.filter(user__isnull=True).count()

    reviews = Review.objects.filter(restaurant=restaurant) if restaurant else Review.objects.none()
    rating = reviews.aggregate(avg=Avg("rating"), n=Count("id"))

    return {
        "days": days,
        "range_choices": RANGE_CHOICES,
        "chart": _chart(per_day, days, today),
        "total_bookings": total,
        "cancel_rate": round(cancelled / total * 100) if total else 0,
        "popular": [
            {"label": label, "count": count, "height": _percent(count, peak_slot)}
            for label, count in slots
        ],
        "guests": [
            {"label": b, "count": guest_counts.get(b, 0), "width": _percent(guest_counts.get(b, 0), peak_guests)}
            for b in GUEST_BUCKETS
        ],
        "total_customers": len(people) + walk_ins,
        "rating_average": f"{rating['avg']:.2f}" if rating["n"] else None,
        "rating_count": rating["n"],
    }
