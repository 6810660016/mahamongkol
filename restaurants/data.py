RESTAURANTS = [
    {
        "slug": "salvia",
        "name": "Salvia",
        "type": "Italian cuisine",
        "rating": "4.8",
        "reviews": 128,
        "price": "$$ · Italian",
        "address": "Central Embassy, Bangkok",
        "hours": "Daily · 11:00 AM – 10:00 PM",
        "image": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=85",
        "description": "A warm Italian dining room for handmade pasta, seasonal ingredients and memorable evenings.",
    },
    {
        "slug": "garden-table",
        "name": "The Garden Table",
        "type": "All-day dining",
        "rating": "4.7",
        "reviews": 96,
        "price": "$$ · International",
        "address": "Sukhumvit, Bangkok",
        "hours": "Daily · 08:00 AM – 09:00 PM",
        "image": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1200&q=85",
        "description": "A relaxed neighbourhood favourite serving thoughtful seasonal dishes in a garden-inspired space.",
    },
    {
        "slug": "mellow-coffee",
        "name": "Mellow Coffee",
        "type": "Coffee and pastry",
        "rating": "4.9",
        "reviews": 84,
        "price": "$ · Café",
        "address": "Ari, Bangkok",
        "hours": "Daily · 08:00 AM – 06:00 PM",
        "image": "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=1200&q=85",
        "description": "Slow mornings, carefully sourced coffee and a little something sweet, made fresh every day.",
    },
]


def get_restaurant(slug):
    return next((item for item in RESTAURANTS if item["slug"] == slug), None)
