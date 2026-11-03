from decimal import Decimal

from django.db import migrations

SEED_RESTAURANTS = [{'slug': 'salvia',
  'name': 'Salvia',
  'type': 'Italian cuisine',
  'rating': '4.8',
  'reviews': 128,
  'price': '$$ · Italian',
  'address': 'Central Embassy, Bangkok',
  'hours': 'Daily · 11:00 AM – 10:00 PM',
  'image': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=85',
  'description': 'A warm Italian dining room for handmade pasta, seasonal ingredients and '
                 'memorable evenings.'},
 {'slug': 'garden-table',
  'name': 'The Garden Table',
  'type': 'All-day dining',
  'rating': '4.7',
  'reviews': 96,
  'price': '$$ · International',
  'address': 'Sukhumvit, Bangkok',
  'hours': 'Daily · 08:00 AM – 09:00 PM',
  'image': 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1200&q=85',
  'description': 'A relaxed neighbourhood favourite serving thoughtful seasonal dishes in a '
                 'garden-inspired space.'},
 {'slug': 'mellow-coffee',
  'name': 'Mellow Coffee',
  'type': 'Coffee and pastry',
  'rating': '4.9',
  'reviews': 84,
  'price': '$ · Café',
  'address': 'Ari, Bangkok',
  'hours': 'Daily · 08:00 AM – 06:00 PM',
  'image': 'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=1200&q=85',
  'description': 'Slow mornings, carefully sourced coffee and a little something sweet, made fresh '
                 'every day.'}]

SEED_TABLE_CAPACITIES = [2, 2, 4, 4, 6, 12]


def seed(apps, schema_editor):
    Restaurant = apps.get_model("restaurants", "Restaurant")
    Table = apps.get_model("restaurants", "Table")
    for item in SEED_RESTAURANTS:
        restaurant, _ = Restaurant.objects.update_or_create(
            slug=item["slug"],
            defaults={
                "name": item["name"],
                "type": item["type"],
                "rating": Decimal(item["rating"]),
                "reviews": item["reviews"],
                "price": item["price"],
                "address": item["address"],
                "hours": item["hours"],
                "image": item["image"],
                "description": item["description"],
            },
        )
        if not restaurant.tables.exists():
            for number, seats in enumerate(SEED_TABLE_CAPACITIES, start=1):
                Table.objects.create(
                    restaurant=restaurant, name=f"T{number}", capacity=seats
                )


def unseed(apps, schema_editor):
    Restaurant = apps.get_model("restaurants", "Restaurant")
    Restaurant.objects.filter(
        slug__in=[item["slug"] for item in SEED_RESTAURANTS], owner__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
