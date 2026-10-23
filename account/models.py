from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "user", "ลูกค้า"
        ADMIN = "admin", "พนักงาน"

    email = models.EmailField("อีเมล", unique=True)
    role = models.CharField(
        "บทบาท",
        max_length=10,
        choices=Role.choices,
        default=Role.USER,
    )

    REQUIRED_FIELDS = ["email"]

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_user_role(self):
        return self.role == self.Role.USER
