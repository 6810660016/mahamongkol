from django.conf import settings
from django.db import models


class Restaurant(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="restaurants",
    )
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=120, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    reviews = models.PositiveIntegerField(default=0)
    price = models.CharField(max_length=60, blank=True)
    address = models.CharField(max_length=200, blank=True)
    hours = models.CharField(max_length=100, blank=True)
    image = models.URLField(blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return self.name


class Table(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="tables"
    )
    name = models.CharField(max_length=30)
    capacity = models.PositiveSmallIntegerField(default=2)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=["restaurant", "name"],
                name="unique_table_name_per_restaurant",
            ),
        )

    def __str__(self):
        return f"{self.restaurant.name} · {self.name} ({self.capacity} seats)"
