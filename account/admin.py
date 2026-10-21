from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role",) + BaseUserAdmin.list_filter

    # หน้าแก้ไขผู้ใช้
    fieldsets = BaseUserAdmin.fieldsets + (
        ("บทบาท", {"fields": ("role",)}),
    )

    # หน้าเพิ่มผู้ใช้
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "role", "password1", "password2"),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        # พนักงาน (role admin) ต้องเข้าหน้า Django admin ได้
        if obj.role == User.Role.ADMIN:
            obj.is_staff = True
        super().save_model(request, obj, form, change)
