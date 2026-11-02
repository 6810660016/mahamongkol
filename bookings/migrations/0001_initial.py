import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("restaurants", "0002_seed_restaurants"),
    ]

    operations = [
        migrations.CreateModel(
            name="Booking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("time", models.TimeField()),
                ("guests", models.PositiveSmallIntegerField()),
                ("status", models.CharField(choices=[("confirmed", "Confirmed"), ("cancelled", "Cancelled")], default="confirmed", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("table", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bookings", to="restaurants.table")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bookings", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("date", "time"),
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("status", "confirmed")), fields=("table", "date", "time"), name="unique_confirmed_booking_per_table_slot"),
                ],
            },
        ),
    ]
