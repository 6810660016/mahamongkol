from django.shortcuts import render


def login_view(request):
    """Render the login screen; authentication can be connected later."""
    return render(request, 'account/login.html')


def welcome_view(request):
    return render(request, 'account/welcome.html')


def home_view(request):
    categories = [
        ('restaurant', 'Restaurants', 'Discover handpicked menus'),
        ('coffee', 'Cafés', 'Slow down and enjoy the moment'),
        ('spa', 'Wellness', 'Relax and recharge with ease'),
        ('service', 'More services', 'Book everything in one place'),
    ]
    favourites = [
        {
            'name': 'Salvia',
            'type': 'Restaurant · Italian cuisine',
            'image': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=900&q=85',
        },
        {
            'name': 'The Garden Table',
            'type': 'Restaurant · All-day dining',
            'image': 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=900&q=85',
        },
        {
            'name': 'Mellow Coffee',
            'type': 'Café · Coffee and pastry',
            'image': 'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=900&q=85',
        },
    ]
    return render(request, 'account/home.html', {
        'categories': categories,
        'favourites': favourites,
    })
