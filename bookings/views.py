from datetime import date

from django.http import Http404
from django.shortcuts import redirect, render

from restaurants.data import get_restaurant

SLOTS = ("11:30", "13:00", "17:30", "19:00", "20:30")

def booking_view(request, slug):
    restaurant = get_restaurant(slug)
    if restaurant is None:
        raise Http404("Restaurant not found")
    error = ""
    if request.method == "POST":
        booking_date = request.POST.get("date", "")
        booking_time = request.POST.get("time", "")
        guests = request.POST.get("guests", "2")
        try:
            parsed_date = date.fromisoformat(booking_date)
            guest_count = int(guests)
            if parsed_date < date.today():
                raise ValueError
            if booking_time not in SLOTS or not 1 <= guest_count <= 12:
                raise ValueError
        except (TypeError, ValueError):
            error = "Please choose a valid date, time and party size."
        else:
            bookings = request.session.get("bookings", [])
            booking_id = max((item["id"] for item in bookings), default=0) + 1
            bookings.append(
                {
                    "id": booking_id,
                    "restaurant": restaurant["name"],
                    "slug": restaurant["slug"],
                    "image": restaurant["image"],
                    "date": booking_date,
                    "time": booking_time,
                    "guests": guest_count,
                    "status": "Confirmed",
                }
            )
            request.session["bookings"] = bookings
            return redirect("my_queues")
    return render(
        request,
        "bookings/booking.html",
        {
            "restaurant": restaurant,
            "error": error,
            "slots": SLOTS,
        },
    )

def my_queues_view(request):
    bookings = request.session.get("bookings", [])
    return render(request, "bookings/my_queues.html", {"bookings": bookings})

def cancel_booking_view(request, booking_id):
    bookings = request.session.get("bookings", [])
    booking = next((item for item in bookings if item["id"] == booking_id), None)
    if booking is None:
        return redirect("my_queues")
    if request.method == "POST":
        request.session["bookings"] = [
            item for item in bookings if item["id"] != booking_id
        ]
        return redirect("my_queues")
    return render(request, "bookings/cancel_booking.html", {"booking": booking})
