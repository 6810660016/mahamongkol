from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

DEFAULT_NO_SHOW_GRACE_MINUTES = 30
MAX_NO_SHOW_GRACE_MINUTES = 240


class RestaurantQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Restaurant.Status.PUBLISHED)

class Restaurant(models.Model):
    class Category(models.TextChoices):
        RESTAURANT = "Restaurant", "Restaurant"
        CAFE = "Café", "Café"
        WELLNESS = "Wellness", "Wellness"
        OTHER = "Other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        
    class ServiceMode(models.TextChoices):
        BOTH = "both", "Bookings and queue"
        BOOKING = "booking", "Bookings only"
        QUEUE = "queue", "Queue only"

    # หนึ่งบัญชีเจ้าของมีได้ 1 ร้าน (ร้านที่ไม่มีเจ้าของ เช่น ร้าน seed เป็น NULL ได้หลายร้าน)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="restaurant",
    )
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.RESTAURANT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED)
    is_open = models.BooleanField(default=True)
    # How guests can get a place: reserve a table in advance, join the line, or both.
    service_mode = models.CharField(
        max_length=10, choices=ServiceMode.choices, default=ServiceMode.BOTH
    )
    extra_details = models.JSONField(default=list, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    reviews = models.PositiveIntegerField(default=0)
    price = models.CharField(max_length=60, blank=True)
    address = models.CharField(max_length=200, blank=True)
    hours = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    # ลิงก์ Google Maps ฯลฯ ยาวได้เกิน 200 ตัวอักษร จึงตั้ง max_length เอง
    map_url = models.URLField(max_length=500, blank=True)
    image = models.URLField(blank=True)
    description = models.TextField(blank=True)
    # นาทีที่รอลูกค้าหลังเวลานัด ก่อนนับการจองที่ยัง confirmed เป็น No Show
    no_show_grace_minutes = models.PositiveSmallIntegerField(
        default=DEFAULT_NO_SHOW_GRACE_MINUTES,
        validators=[MaxValueValidator(MAX_NO_SHOW_GRACE_MINUTES)],
    )
    objects = RestaurantQuerySet.as_manager()

    class Meta:
        ordering = ("id",)

    @property
    def accepts_bookings(self):
        return self.service_mode in (self.ServiceMode.BOTH, self.ServiceMode.BOOKING)

    @property
    def accepts_queue(self):
        return self.service_mode in (self.ServiceMode.BOTH, self.ServiceMode.QUEUE)

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
