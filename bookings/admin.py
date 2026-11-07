from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "table", "date", "time", "guests", "status")
    list_filter = ("status", "date", "table__restaurant")
    search_fields = ("user__username", "user__email", "table__restaurant__name")
    readonly_fields = ("created_at", "cancelled_at", "completed_at", "completed_by")
