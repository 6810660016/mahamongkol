from typing import ClassVar

from django.contrib import admin

from .models import Restaurant, RestaurantImage, Table


class TableInline(admin.TabularInline):
    model = Table
    extra = 1


class RestaurantImageInline(admin.TabularInline):
    model = RestaurantImage
    extra = 0


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "type", "no_show_grace_minutes")
    search_fields = ("name", "address")
    prepopulated_fields: ClassVar = {"slug": ("name",)}
    inlines = (TableInline, RestaurantImageInline)
