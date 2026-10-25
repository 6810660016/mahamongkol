from datetime import date

from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect, render

from .forms import SignupForm


RESTAURANTS = [
    {
        'slug': 'salvia', 'name': 'Salvia', 'type': 'Italian cuisine', 'rating': '4.8',
        'reviews': 128, 'price': '$$ · Italian', 'address': 'Central Embassy, Bangkok',
        'hours': 'Daily · 11:00 AM – 10:00 PM',
        'image': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=85',
        'description': 'A warm Italian dining room for handmade pasta, seasonal ingredients and memorable evenings.',
    },
    {
        'slug': 'garden-table', 'name': 'The Garden Table', 'type': 'All-day dining', 'rating': '4.7',
        'reviews': 96, 'price': '$$ · International', 'address': 'Sukhumvit, Bangkok',
        'hours': 'Daily · 08:00 AM – 09:00 PM',
        'image': 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1200&q=85',
        'description': 'A relaxed neighbourhood favourite serving thoughtful seasonal dishes in a garden-inspired space.',
    },
    {
        'slug': 'mellow-coffee', 'name': 'Mellow Coffee', 'type': 'Coffee and pastry', 'rating': '4.9',
        'reviews': 84, 'price': '$ · Café', 'address': 'Ari, Bangkok',
        'hours': 'Daily · 08:00 AM – 06:00 PM',
        'image': 'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=1200&q=85',
        'description': 'Slow mornings, carefully sourced coffee and a little something sweet, made fresh every day.',
    },
]


def login_view(request):
    """Render the login screen; authentication can be connected later."""
    return render(request, 'account/login.html')


def signup_view(request):
    """Customer sign up; staff (admin role) accounts are created in Django admin."""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = SignupForm()

    return render(request, 'account/signup.html', {'form': form})


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
            'slug': 'salvia',
            'name': 'Salvia',
            'type': 'Restaurant · Italian cuisine',
            'image': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=900&q=85',
        },
        {
            'slug': 'garden-table',
            'name': 'The Garden Table',
            'type': 'Restaurant · All-day dining',
            'image': 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=900&q=85',
        },
        {
            'slug': 'mellow-coffee',
            'name': 'Mellow Coffee',
            'type': 'Café · Coffee and pastry',
            'image': 'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=900&q=85',
        },
    ]
    return render(request, 'account/home.html', {
        'categories': categories,
        'favourites': favourites,
    })


def restaurants_view(request):
    query = request.GET.get('q', '').strip()
    restaurants = RESTAURANTS
    if query:
        restaurants = [place for place in RESTAURANTS if query.casefold() in f"{place['name']} {place['type']} {place['address']}".casefold()]
    return render(request, 'account/restaurants.html', {'restaurants': restaurants, 'query': query})


def restaurant_detail_view(request, slug):
    restaurant = next((item for item in RESTAURANTS if item['slug'] == slug), None)
    if restaurant is None:
        raise Http404('Restaurant not found')
    return render(request, 'account/restaurant_detail.html', {'restaurant': restaurant})


def booking_view(request, slug):
    restaurant = next((item for item in RESTAURANTS if item['slug'] == slug), None)
    if restaurant is None:
        raise Http404('Restaurant not found')
    error = ''
    if request.method == 'POST':
        booking_date = request.POST.get('date', '')
        booking_time = request.POST.get('time', '')
        guests = request.POST.get('guests', '2')
        try:
            parsed_date = date.fromisoformat(booking_date)
            guest_count = int(guests)
            if parsed_date < date.today():
                raise ValueError
            if booking_time not in ('11:30', '13:00', '17:30', '19:00', '20:30') or not 1 <= guest_count <= 12:
                raise ValueError
        except (TypeError, ValueError):
            error = 'Please choose a valid date, time and party size.'
        else:
            bookings = request.session.get('bookings', [])
            booking_id = max((item['id'] for item in bookings), default=0) + 1
            bookings.append({
                'id': booking_id,
                'restaurant': restaurant['name'],
                'slug': restaurant['slug'],
                'image': restaurant['image'],
                'date': booking_date,
                'time': booking_time,
                'guests': guest_count,
                'status': 'Confirmed',
            })
            request.session['bookings'] = bookings
            return redirect('my_queues')
    return render(request, 'account/booking.html', {
        'restaurant': restaurant,
        'error': error,
        'slots': ('11:30', '13:00', '17:30', '19:00', '20:30'),
    })


def my_queues_view(request):
    bookings = request.session.get('bookings', [])
    return render(request, 'account/my_queues.html', {'bookings': bookings})


def cancel_booking_view(request, booking_id):
    bookings = request.session.get('bookings', [])
    booking = next((item for item in bookings if item['id'] == booking_id), None)
    if booking is None:
        return redirect('my_queues')
    if request.method == 'POST':
        request.session['bookings'] = [item for item in bookings if item['id'] != booking_id]
        return redirect('my_queues')
    return render(request, 'account/cancel_booking.html', {'booking': booking})
