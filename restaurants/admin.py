from typing import ClassVar

from django.contrib import admin

from .models import Restaurant, Table


class TableInline(admin.TabularInline):
    model = Table
    extra = 1


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "type")
    search_fields = ("name", "address")
    prepopulated_fields: ClassVar = {"slug": ("name",)}
    inlines = (TableInline,)
