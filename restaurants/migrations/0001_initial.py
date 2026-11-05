import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Restaurant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("name", models.CharField(max_length=120)),
                ("type", models.CharField(blank=True, max_length=120)),
                ("rating", models.DecimalField(decimal_places=1, default=0, max_digits=2)),
                ("reviews", models.PositiveIntegerField(default=0)),
                ("price", models.CharField(blank=True, max_length=60)),
                ("address", models.CharField(blank=True, max_length=200)),
                ("hours", models.CharField(blank=True, max_length=100)),
                ("image", models.URLField(blank=True)),
                ("description", models.TextField(blank=True)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="restaurants", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("id",),
            },
        ),
        migrations.CreateModel(
            name="Table",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=30)),
                ("capacity", models.PositiveSmallIntegerField(default=2)),
                ("restaurant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tables", to="restaurants.restaurant")),
            ],
            options={
                "ordering": ("name",),
                "constraints": [
                    models.UniqueConstraint(fields=("restaurant", "name"), name="unique_table_name_per_restaurant"),
                ],
            },
        ),
    ]
