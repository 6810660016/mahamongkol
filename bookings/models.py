from django.conf import settings
from django.db import models
from django.db.models import Q


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No Show"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    table = models.ForeignKey(
        "restaurants.Table",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    date = models.DateField()
    time = models.TimeField()
    guests = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.CONFIRMED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_bookings",
    )

    class Meta:
        ordering = ("date", "time")
        constraints = (
            models.UniqueConstraint(
                fields=["table", "date", "time"],
                condition=Q(status="confirmed"),
                name="unique_confirmed_booking_per_table_slot",
            ),
        )
    
    
    @property
    def restaurant(self):
        return self.table.restaurant

    @property
    def slug(self):
        return self.table.restaurant.slug

    @property
    def image(self):
        return self.table.restaurant.image

    @property
    def code(self):
        return f"B{self.id:03d}"

    @property
    def is_confirmed(self):
        return self.status == self.Status.CONFIRMED

    def __str__(self):
        return f"{self.user} · {self.table} · {self.date} {self.time:%H:%M}"
