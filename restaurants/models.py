from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

MAX_GALLERY_IMAGES = 4  # จำนวนช่อง Pictures บนหน้า Store Details
MAX_BOOKING_SLOTS = 20  # รอบเวลาจองต่อร้าน
MAX_TABLES_PER_SLOT = 100
MAX_SEATS_PER_TABLE = 12
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
    # public_id ของรูปที่อัปโหลดผ่านหน้า Store Details (ใช้ลบรูปเก่าบน Cloudinary)
    # ว่างได้: รูปเก่าก่อน Phase 6 หรือ URL ที่วางเองจะไม่มีค่านี้ และจะไม่ถูกลบ
    image_public_id = models.CharField(max_length=255, blank=True)
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


class RestaurantImage(models.Model):
    """รูปในส่วน Pictures ของร้าน (แยกจากรูปหลัก Restaurant.image) ร้านละไม่เกิน MAX_GALLERY_IMAGES รูป"""

    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="gallery_images"
    )
    # ช่องที่ 1..MAX_GALLERY_IMAGES บนหน้า Store Details (ช่องว่างข้ามได้ เช่น มีแค่ช่อง 1 กับ 3)
    slot = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_GALLERY_IMAGES)]
    )
    image = models.URLField()
    # public_id บน Cloudinary ใช้ลบรูปเก่าตอนแทนที่/ลบ ว่างได้ถ้าไม่ใช่รูปที่อัปโหลดผ่านระบบ
    public_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("slot",)
        constraints = (
            models.UniqueConstraint(
                fields=("restaurant", "slot"), name="unique_gallery_slot_per_restaurant"
            ),
        )

    def __str__(self):
        return f"{self.restaurant} #{self.slot}"


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


class BookingSlot(models.Model):
    """รอบเวลาจองที่เจ้าของร้านกำหนด: จำนวนโต๊ะและจำนวนที่นั่งต่อโต๊ะของรอบนั้น

    ร้านที่ยังไม่มีรอบเลยจะใช้รอบและโต๊ะแบบเดิม (bookings.services.SLOTS) จึงไม่กระทบร้านเก่า
    """

    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="booking_slots"
    )
    time = models.TimeField()
    table_count = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_TABLES_PER_SLOT)]
    )
    seats_per_table = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_SEATS_PER_TABLE)]
    )
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ("time",)
        constraints = (
            models.UniqueConstraint(
                fields=("restaurant", "time"), name="unique_booking_slot_time_per_restaurant"
            ),
        )

    def __str__(self):
        return f"{self.restaurant} {self.time:%H:%M} ({self.table_count} tables x {self.seats_per_table} seats)"


class BookingSlotDate(models.Model):
    """รอบเวลาจองของ "วันที่ระบุ" ที่เจ้าของกำหนดล่วงหน้าจากปฏิทิน

    ถ้าวันนั้นมีแถวอยู่ แถวเหล่านี้จะแทนที่รอบปกติของร้านทั้งหมดสำหรับวันนั้น
    (ปิดรอบ = ติ๊ก Available ออก, ลบทุกแถว = กลับไปใช้รอบปกติ)
    """

    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="booking_slot_dates"
    )
    date = models.DateField()
    time = models.TimeField()
    table_count = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_TABLES_PER_SLOT)]
    )
    seats_per_table = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_SEATS_PER_TABLE)]
    )
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ("date", "time")
        constraints = (
            models.UniqueConstraint(
                fields=("restaurant", "date", "time"),
                name="unique_booking_slot_date_time_per_restaurant",
            ),
        )

    def __str__(self):
        return f"{self.restaurant} {self.date} {self.time:%H:%M}"


class Review(models.Model):
    """One star rating (with optional comment) per customer per restaurant."""

    MAX_MESSAGE_LENGTH = 500

    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="review_set"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    message = models.CharField(max_length=MAX_MESSAGE_LENGTH, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["restaurant", "user"], name="one_review_per_user_and_restaurant"
            ),
        )

    def __str__(self):
        return f"{self.restaurant.name} · {self.rating}★ by {self.user}"
