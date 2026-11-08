from datetime import date, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from restaurants.models import Restaurant

from . import services
from .models import Booking

User = get_user_model()


class AddMonthsTests(TestCase):
    def test_same_day_number_in_a_later_month(self):
        self.assertEqual(services.add_months(date(2026, 11, 6), 1), date(2026, 12, 6))
        self.assertEqual(services.add_months(date(2026, 11, 6), 3), date(2027, 2, 6))

    def test_short_months_use_their_last_day(self):
        self.assertEqual(services.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(services.add_months(date(2028, 1, 31), 1), date(2028, 2, 29))
        self.assertEqual(services.add_months(date(2026, 3, 31), 1), date(2026, 4, 30))

    def test_year_rollover(self):
        self.assertEqual(services.add_months(date(2026, 12, 15), 1), date(2027, 1, 15))
        self.assertEqual(services.add_months(date(2026, 12, 31), 12), date(2027, 12, 31))

    def test_zero_months_is_the_same_day(self):
        self.assertEqual(services.add_months(date(2026, 11, 6), 0), date(2026, 11, 6))


@override_settings(BOOKING_MAX_ADVANCE_MONTHS=1)
class BookingWindowTests(TestCase):
    def test_window_starts_today_and_ends_after_the_configured_months(self):
        today = timezone.localdate()
        first, last = services.booking_window()
        self.assertEqual(first, today)
        self.assertEqual(last, services.add_months(today, 1))

    @override_settings(BOOKING_MAX_ADVANCE_MONTHS=3)
    def test_window_follows_the_setting(self):
        today = timezone.localdate()
        self.assertEqual(services.booking_window()[1], services.add_months(today, 3))

    def test_built_in_default_is_one_month_when_the_setting_is_missing(self):
        with override_settings():
            del settings.BOOKING_MAX_ADVANCE_MONTHS
            self.assertEqual(services.advance_months(), 1)

    def test_window_can_be_computed_for_a_given_day(self):
        self.assertEqual(
            services.booking_window(date(2026, 1, 31)), (date(2026, 1, 31), date(2026, 2, 28))
        )


@override_settings(BOOKING_MAX_ADVANCE_MONTHS=1)
class BookingDateRangeTests(TestCase):
    def setUp(self):
        # Freeze the clock at midday so the evening slots are always still in the future.
        noon = datetime(2026, 11, 8, 12, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
        patcher = mock.patch("django.utils.timezone.now", return_value=noon)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.customer = User.objects.create_user("customer", "customer@example.com", "Queue-pass-2026")
        self.client.force_login(self.customer)
        self.salvia = Restaurant.objects.get(slug="salvia")
        self.today = timezone.localdate()
        self.last_day = services.booking_window()[1]

    def book(self, day, slot="20:30", guests="2"):
        return self.client.post(
            reverse("booking", args=["salvia"]),
            {"date": day.isoformat(), "time": slot, "guests": guests},
        )

    def test_today_can_be_booked(self):
        self.assertRedirects(self.book(self.today), reverse("my_queues"))
        self.assertEqual(Booking.objects.get().date, self.today)

    def test_last_day_of_the_window_can_be_booked(self):
        self.assertRedirects(self.book(self.last_day), reverse("my_queues"))
        self.assertEqual(Booking.objects.get().date, self.last_day)

    def test_day_after_the_window_is_rejected(self):
        response = self.book(self.last_day + timedelta(days=1))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bookings are open up to")
        self.assertContains(response, f"{self.last_day:%Y-%m-%d}")
        self.assertContains(response, "1 month ahead")
        self.assertEqual(Booking.objects.count(), 0)

    def test_dates_far_in_the_future_are_rejected(self):
        for days in (60, 365, 3650):
            with self.subTest(days=days):
                response = self.book(self.today + timedelta(days=days))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Bookings are open up to")
        self.assertEqual(Booking.objects.count(), 0)

    def test_yesterday_is_still_rejected(self):
        response = self.book(self.today - timedelta(days=1))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please choose a valid date")
        self.assertEqual(Booking.objects.count(), 0)

    @override_settings(BOOKING_MAX_ADVANCE_MONTHS=3)
    def test_a_longer_window_accepts_later_dates_and_names_the_months(self):
        two_months_ahead = services.add_months(self.today, 2)
        self.assertRedirects(self.book(two_months_ahead), reverse("my_queues"))

        response = self.book(services.add_months(self.today, 3) + timedelta(days=1))
        self.assertContains(response, "3 months ahead")

    def test_a_one_month_window_does_not_reach_two_months(self):
        response = self.book(services.add_months(self.today, 2))
        self.assertContains(response, "Bookings are open up to")
        self.assertEqual(Booking.objects.count(), 0)

    def test_booking_page_limits_the_date_picker(self):
        response = self.client.get(reverse("booking", args=["salvia"]))
        self.assertContains(response, f'min="{self.today:%Y-%m-%d}"')
        self.assertContains(response, f'max="{self.last_day:%Y-%m-%d}"')
        self.assertContains(response, f"up to {self.last_day:%Y-%m-%d}.")
        self.assertEqual(response.context["min_date"], self.today)
        self.assertEqual(response.context["max_date"], self.last_day)

    def test_service_raises_a_booking_error_outside_the_window(self):
        with self.assertRaises(services.BookingError):
            services.create_booking(
                self.customer, self.salvia, self.last_day + timedelta(days=1), "19:00", 2
            )
        self.assertEqual(Booking.objects.count(), 0)

    def test_managers_can_still_browse_any_date(self):
        owner = User.objects.create_user(
            "owner", "owner@example.com", "Queue-pass-2026", role=User.Role.OWNER
        )
        self.salvia.owner = owner
        self.salvia.save()
        self.client.force_login(owner)
        far = self.today + timedelta(days=400)
        response = self.client.get(
            reverse("manage_bookings", args=["salvia"]), {"date": far.isoformat(), "time": "19:00"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["day"], far)
