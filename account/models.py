from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "user", "ลูกค้า"
        OWNER = "owner", "เจ้าของร้าน"
        ADMIN = "admin", "พนักงาน"

    email = models.EmailField("อีเมล", unique=True)
    role = models.CharField(
        "บทบาท",
        max_length=10,
        choices=Role.choices,
        default=Role.USER,
    )

    REQUIRED_FIELDS = ["email"]

    class Meta(AbstractUser.Meta):
        constraints = [
            # Login looks users up by email, so emails must be unique ignoring case
            models.UniqueConstraint(
                Lower("email"),
                name="account_user_email_ci_unique",
                violation_error_message="A user with that email already exists.",
            ),
        ]

    def save(self, *args, **kwargs):
        # Admin and createsuperuser only lowercase the domain part
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_user_role(self):
        return self.role in (self.Role.USER, self.Role.OWNER)

    @property
    def is_owner_role(self):
        if self.role != self.Role.OWNER:
            return False
        try:
            return self.owner_application.status == OwnerApplication.Status.APPROVED
        except OwnerApplication.DoesNotExist:
            # Owner accounts created before application review retain their access.
            return True


class OwnerApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="owner_application",
    )
    contact_name = models.CharField(max_length=120)
    business_name = models.CharField(max_length=160)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_owner_applications",
    )

    class Meta:
        ordering = ("-submitted_at",)

    def __str__(self):
        return f"{self.business_name} · {self.get_status_display()}"
