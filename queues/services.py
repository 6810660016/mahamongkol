"""Queue rules. Views stay thin; every state change goes through here.

Each change locks the restaurant row first, so two owners' devices (or a double
click) can never hand out the same number or serve two parties at once.
"""

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from restaurants.models import Restaurant

from .models import QueueEntry, QueueSetting

MAX_PARTY_SIZE = 20
ACTIVE_STATUSES = (QueueEntry.Status.WAITING, QueueEntry.Status.SERVING)


class QueueError(Exception):
    """A queue action that is not allowed right now (message is safe to show)."""


def service_day():
    return timezone.localdate()


def _lock(restaurant):
    return Restaurant.objects.select_for_update().get(pk=restaurant.pk)


def _todays(restaurant):
    return QueueEntry.objects.filter(restaurant=restaurant, day=service_day())


def _waiting_in_order(restaurant):
    return _todays(restaurant).filter(status=QueueEntry.Status.WAITING).order_by(
        "-is_priority", "number"
    )


def is_paused(restaurant):
    return QueueSetting.objects.filter(restaurant=restaurant, is_paused=True).exists()


def _party_size(value):
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise QueueError("Party size must be a number.") from None
    if not 1 <= size <= MAX_PARTY_SIZE:
        raise QueueError(f"Party size must be between 1 and {MAX_PARTY_SIZE}.")
    return size


def _serve(entry):
    entry.status = QueueEntry.Status.SERVING
    entry.is_priority = False
    entry.called_at = timezone.now()
    entry.call_count += 1
    entry.save(update_fields=["status", "is_priority", "called_at", "call_count"])
    return entry


def _serve_next_if_idle(restaurant):
    if _todays(restaurant).filter(status=QueueEntry.Status.SERVING).exists():
        return None
    entry = _waiting_in_order(restaurant).first()
    return _serve(entry) if entry else None


def _current(restaurant):
    return _todays(restaurant).filter(status=QueueEntry.Status.SERVING).first()


def _require_queue(restaurant):
    if not restaurant.accepts_queue:
        raise QueueError("This restaurant does not use the queue.")


@transaction.atomic
def add_entry(restaurant, name="", party_size=2):
    """The owner adds a walk-in guest to today's line."""
    restaurant = _lock(restaurant)
    _require_queue(restaurant)
    if is_paused(restaurant):
        raise QueueError("New queues are paused.")
    size = _party_size(party_size)
    last = _todays(restaurant).aggregate(last=Max("number"))["last"] or 0
    return QueueEntry.objects.create(
        restaurant=restaurant,
        day=service_day(),
        number=last + 1,
        name=(name or "").strip()[:60],
        party_size=size,
        source=QueueEntry.Source.WALK_IN,
    )


@transaction.atomic
def call_next(restaurant):
    restaurant = _lock(restaurant)
    if _current(restaurant):
        raise QueueError("Finish or skip the current queue first.")
    entry = _serve_next_if_idle(restaurant)
    if entry is None:
        raise QueueError("No queues are waiting.")
    return entry


@transaction.atomic
def call_again(restaurant):
    restaurant = _lock(restaurant)
    entry = _current(restaurant)
    if entry is None:
        raise QueueError("No queue is being served.")
    entry.call_count += 1
    entry.called_at = timezone.now()
    entry.save(update_fields=["call_count", "called_at"])
    return entry


def _finish(restaurant, status):
    restaurant = _lock(restaurant)
    entry = _current(restaurant)
    if entry is None:
        raise QueueError("No queue is being served.")
    entry.status = status
    entry.finished_at = timezone.now()
    entry.save(update_fields=["status", "finished_at"])
    return entry, _serve_next_if_idle(restaurant)


@transaction.atomic
def complete(restaurant):
    """Finish the current party and call the next one. Returns (finished, next_or_None)."""
    return _finish(restaurant, QueueEntry.Status.COMPLETED)


@transaction.atomic
def skip(restaurant):
    """Skip the current party and call the next one. Returns (skipped, next_or_None)."""
    return _finish(restaurant, QueueEntry.Status.SKIPPED)


@transaction.atomic
def recall(restaurant, entry_id):
    """Put a skipped party at the front of the line (served now if nobody is)."""
    restaurant = _lock(restaurant)
    entry = _todays(restaurant).filter(pk=entry_id, status=QueueEntry.Status.SKIPPED).first()
    if entry is None:
        raise QueueError("That queue is not in the skipped list.")
    entry.status = QueueEntry.Status.WAITING
    entry.is_priority = True
    entry.finished_at = None
    entry.save(update_fields=["status", "is_priority", "finished_at"])
    _serve_next_if_idle(restaurant)
    entry.refresh_from_db()
    return entry


@transaction.atomic
def set_paused(restaurant, paused):
    restaurant = _lock(restaurant)
    setting, _ = QueueSetting.objects.get_or_create(restaurant=restaurant)
    setting.is_paused = bool(paused)
    setting.save(update_fields=["is_paused"])
    return setting.is_paused


def _entry_data(entry):
    return {
        "id": entry.pk,
        "number": entry.number,
        "code": entry.code,
        "name": entry.name,
        "party": entry.party_size,
        "source": entry.get_source_display(),
        "priority": entry.is_priority,
        "joinedAt": int(entry.created_at.timestamp() * 1000),
        "callCount": entry.call_count,
    }


def snapshot(restaurant):
    """Everything the owner queue page shows, as plain JSON-able data."""
    entries = list(_todays(restaurant).order_by("number"))
    current = next((e for e in entries if e.status == QueueEntry.Status.SERVING), None)
    waiting = sorted(
        (e for e in entries if e.status == QueueEntry.Status.WAITING),
        key=lambda e: (not e.is_priority, e.number),
    )
    skipped = [e for e in entries if e.status == QueueEntry.Status.SKIPPED]
    completed = sum(1 for e in entries if e.status == QueueEntry.Status.COMPLETED)

    return {
        "queueEnabled": restaurant.accepts_queue,
        "paused": is_paused(restaurant),
        "current": _entry_data(current) if current else None,
        "waiting": [_entry_data(e) for e in waiting],
        "skipped": [_entry_data(e) for e in skipped],
        "completed": completed,
        "serverTime": int(timezone.now().timestamp() * 1000),
    }


# Customer side ---------------------------------------------------------------


@transaction.atomic
def join_queue(user, restaurant, party_size=2):
    """A signed-in guest takes a number for the restaurant's line today."""
    restaurant = _lock(restaurant)
    if not restaurant.is_open or restaurant.status != Restaurant.Status.PUBLISHED:
        raise QueueError("This restaurant is not taking queues right now.")
    _require_queue(restaurant)
    if is_paused(restaurant):
        raise QueueError("This restaurant has paused new queues.")
    size = _party_size(party_size)
    if _todays(restaurant).filter(user=user, status__in=ACTIVE_STATUSES).exists():
        raise QueueError("You are already in this restaurant's queue.")
    last = _todays(restaurant).aggregate(last=Max("number"))["last"] or 0
    return QueueEntry.objects.create(
        restaurant=restaurant,
        day=service_day(),
        number=last + 1,
        name=user.get_full_name() or user.username,
        party_size=size,
        source=QueueEntry.Source.ONLINE,
        user=user,
    )


@transaction.atomic
def leave_queue(user, entry_id):
    """A guest gives up their own place while still waiting."""
    entry = QueueEntry.objects.filter(pk=entry_id, user=user, day=service_day()).first()
    if entry is None:
        raise QueueError("That queue was not found.")
    restaurant = _lock(entry.restaurant)
    entry = _todays(restaurant).get(pk=entry.pk)
    if entry.status == QueueEntry.Status.SERVING:
        raise QueueError("You are being served. Please tell the staff if you need to leave.")
    if entry.status != QueueEntry.Status.WAITING:
        raise QueueError("That queue is no longer active.")
    entry.status = QueueEntry.Status.CANCELLED
    entry.finished_at = timezone.now()
    entry.save(update_fields=["status", "finished_at"])
    return entry


def guest_queues(user):
    """The signed-in guest's live places in line today, for the My Q page."""
    mine = list(
        QueueEntry.objects.filter(
            user=user,
            day=service_day(),
            status__in=(*ACTIVE_STATUSES, QueueEntry.Status.SKIPPED),
        ).select_related("restaurant")
    )
    result = []
    for entry in mine:
        restaurant = entry.restaurant
        current = _current(restaurant)
        ahead = None
        if entry.status == QueueEntry.Status.WAITING:
            order = list(_waiting_in_order(restaurant).values_list("pk", flat=True))
            ahead = order.index(entry.pk) if entry.pk in order else None
        result.append(
            {
                "id": entry.pk,
                "code": entry.code,
                "status": entry.status,
                "party": entry.party_size,
                "ahead": ahead,
                "callCount": entry.call_count,
                "nowServing": current.code if current else None,
                "restaurant": restaurant.name,
                "slug": restaurant.slug,
                "image": restaurant.image,
            }
        )
    return result
