from django.conf import settings
from django.db import models
from django.db.models import Q


class QueueEntry(models.Model):
    """One party in a restaurant's line for one service day (walk-in or checked-in booking)."""

    class Source(models.TextChoices):
        BOOKING = "booking", "Booking"
        WALK_IN = "walkin", "Walk-in"
        ONLINE = "online", "Online"

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        SERVING = "serving", "Serving"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"
        CANCELLED = "cancelled", "Left the queue"

    restaurant = models.ForeignKey(
        "restaurants.Restaurant", on_delete=models.CASCADE, related_name="queue_entries"
    )
    day = models.DateField()
    number = models.PositiveIntegerField()
    # Set when the guest joined from the customer side or checked in a booking.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="queue_entries",
    )
    name = models.CharField(max_length=60, blank=True)
    party_size = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.WALK_IN)
    booking = models.OneToOneField(
        "bookings.Booking",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="queue_entry",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.WAITING, db_index=True
    )
    # A recalled (previously skipped) party is called before the rest of the line.
    is_priority = models.BooleanField(default=False)
    call_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    called_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("day", "number")
        constraints = (
            models.UniqueConstraint(
                fields=["restaurant", "day", "number"],
                name="unique_queue_number_per_restaurant_day",
            ),
            # A signed-in guest can be in a restaurant's line only once at a time.
            models.UniqueConstraint(
                fields=["restaurant", "day", "user"],
                condition=Q(status__in=["waiting", "serving"], user__isnull=False),
                name="one_active_queue_entry_per_user_and_day",
            ),
            # At most one party is being served at a time.
            models.UniqueConstraint(
                fields=["restaurant", "day"],
                condition=Q(status="serving"),
                name="one_serving_entry_per_restaurant_day",
            ),
        )

    @property
    def code(self):
        return f"Q{self.number:03d}"

    def __str__(self):
        return f"{self.restaurant.name} · {self.code} ({self.get_status_display()})"


class QueueSetting(models.Model):
    """Per-restaurant switch to stop taking new queue entries."""

    restaurant = models.OneToOneField(
        "restaurants.Restaurant", on_delete=models.CASCADE, related_name="queue_setting"
    )
    is_paused = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.restaurant.name} · {'paused' if self.is_paused else 'open'}"
