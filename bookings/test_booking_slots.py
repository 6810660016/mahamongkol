"""Owner-defined booking slots: N tables x S seats per time, full / past handling."""

from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings import services
from bookings.models import Booking
from restaurants.models import BookingSlot, Restaurant

User = get_user_model()
PASSWORD = "Queue-pass-2026"


class SlotBookingBase(TestCase):
    def setUp(self):
        self.store = Restaurant.objects.create(slug="slot-store", name="Slot Store")
        self.slot = BookingSlot.objects.create(
            restaurant=self.store, time=time(18, 0), table_count=2, seats_per_table=4
        )
        self.today = timezone.localdate()
        self.day = self.today + timedelta(days=1)
        self.users = [
            User.objects.create_user(f"slot-u{i}", f"slot-u{i}@example.com", PASSWORD)
            for i in range(4)
        ]

    def book(self, user, guests=2, day=None, at="18:00"):
        return services.create_booking(user, self.store, day or self.day, at, guests)


class SlotCapacityTests(SlotBookingBase):
    def test_slot_fills_up_then_says_full(self):
        self.book(self.users[0])
        self.book(self.users[1])
        with self.assertRaisesMessage(services.BookingError, "เต็ม"):
            self.book(self.users[2])
        self.assertEqual(Booking.objects.count(), 2)

    def test_cancelling_frees_a_table(self):
        first = self.book(self.users[0])
        self.book(self.users[1])
        services.cancel_booking(first, self.users[0])
        self.book(self.users[2])
        self.assertEqual(Booking.objects.filter(status="confirmed").count(), 2)

    def test_full_slot_does_not_block_other_days_or_times(self):
        BookingSlot.objects.create(
            restaurant=self.store, time=time(20, 0), table_count=1, seats_per_table=2
        )
        self.book(self.users[0])
        self.book(self.users[1])
        self.book(self.users[2], day=self.day + timedelta(days=1))
        self.book(self.users[3], at="20:00")

    def test_party_larger_than_seats_per_table_is_rejected(self):
        with self.assertRaisesMessage(services.BookingError, "up to 4"):
            self.book(self.users[0], guests=5)
        self.assertFalse(Booking.objects.exists())

    def test_unknown_or_closed_slot_is_rejected(self):
        with self.assertRaises(services.BookingError):
            self.book(self.users[0], at="19:00")
        self.slot.is_available = False
        self.slot.save()
        with self.assertRaises(services.BookingError):
            self.book(self.users[0])

    def test_other_restaurants_are_unaffected(self):
        other = Restaurant.objects.create(slug="slot-other", name="Other")
        self.assertFalse(services.uses_custom_slots(other))
        self.assertTrue(services.uses_custom_slots(self.store))

    def test_default_slots_still_work_without_custom_ones(self):
        other = Restaurant.objects.create(slug="slot-default", name="Default")
        other.tables.create(name="T1", capacity=4)
        booking = services.create_booking(self.users[0], other, self.day, "19:00", 2)
        self.assertEqual(booking.restaurant, other)


class PastTimeTests(SlotBookingBase):
    def fake_now(self, hour, minute=0):
        local = datetime.combine(self.today, time(hour, minute), tzinfo=timezone.get_current_timezone())
        return local.astimezone(dt_timezone.utc)

    def test_cannot_book_a_time_that_already_started_today(self):
        with patch("django.utils.timezone.now", return_value=self.fake_now(18, 30)):
            with self.assertRaisesMessage(services.BookingError, "already passed"):
                services.create_booking(self.users[0], self.store, self.today, "18:00", 2)
        self.assertFalse(Booking.objects.exists())

    def test_later_time_today_is_allowed(self):
        with patch("django.utils.timezone.now", return_value=self.fake_now(17, 0)):
            services.create_booking(self.users[0], self.store, self.today, "18:00", 2)
        self.assertEqual(Booking.objects.count(), 1)

    def test_past_date_is_rejected(self):
        with self.assertRaises(services.BookingError):
            services.create_booking(self.users[0], self.store, self.today - timedelta(days=1), "18:00", 2)

    def test_default_slots_also_reject_past_times_today(self):
        other = Restaurant.objects.create(slug="past-default", name="Past Default")
        other.tables.create(name="T1", capacity=4)
        with patch("django.utils.timezone.now", return_value=self.fake_now(23, 0)):
            with self.assertRaisesMessage(services.BookingError, "already passed"):
                services.create_booking(self.users[0], other, self.today, "19:00", 2)

    def test_slot_options_flag_states(self):
        self.book(self.users[0])
        self.book(self.users[1])
        full = services.slot_options(self.store, self.day)[0]
        self.assertEqual((full["state"], full["remaining"]), ("full", 0))
        with patch("django.utils.timezone.now", return_value=self.fake_now(19, 0)):
            past = services.slot_options(self.store, self.today)[0]
        self.assertEqual(past["state"], "past")
        too_large = services.slot_options(self.store, self.day + timedelta(days=2), guests=9)[0]
        self.assertEqual(too_large["state"], "too_large")
        open_ = services.slot_options(self.store, self.day + timedelta(days=2), guests=2)[0]
        self.assertEqual((open_["state"], open_["remaining"]), ("open", 2))


class SlotViewTests(SlotBookingBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.users[0])

    def test_slots_endpoint_reports_remaining_tables(self):
        self.book(self.users[1])
        response = self.client.get(
            reverse("booking_slots", args=[self.store.slug]), {"date": self.day.isoformat(), "guests": "2"}
        )
        self.assertEqual(response.status_code, 200)
        slot = response.json()["slots"][0]
        self.assertEqual((slot["value"], slot["remaining"], slot["state"]), ("18:00", 1, "open"))

    def test_slots_endpoint_validates_the_date(self):
        url = reverse("booking_slots", args=[self.store.slug])
        self.assertEqual(self.client.get(url, {"date": "nope"}).status_code, 400)
        past = (self.today - timedelta(days=1)).isoformat()
        self.assertEqual(self.client.get(url, {"date": past}).status_code, 400)

    def test_booking_page_marks_full_slots(self):
        self.book(self.users[1])
        self.book(self.users[2])
        response = self.client.post(
            reverse("booking", args=[self.store.slug]),
            {"date": self.day.isoformat(), "time": "18:00", "guests": "2"},
        )
        self.assertContains(response, "เต็ม")
        self.assertEqual(Booking.objects.count(), 2)

    def test_booking_post_creates_booking_for_a_free_slot(self):
        response = self.client.post(
            reverse("booking", args=[self.store.slug]),
            {"date": self.day.isoformat(), "time": "18:00", "guests": "3"},
        )
        self.assertRedirects(response, reverse("my_queues"))
        self.assertEqual(Booking.objects.get().guests, 3)


class DateScheduleTests(SlotBookingBase):
    """A schedule set for one calendar date replaces the usual slots for that date only."""

    def set_date_slot(self, day, at=time(12, 0), tables=1, seats=2, available=True):
        return self.store.booking_slot_dates.create(
            date=day, time=at, table_count=tables, seats_per_table=seats, is_available=available
        )

    def test_date_schedule_replaces_usual_slots_for_that_date_only(self):
        self.set_date_slot(self.day)
        self.assertEqual([o["value"] for o in services.slot_options(self.store, self.day)], ["12:00"])
        other_day = self.day + timedelta(days=1)
        self.assertEqual([o["value"] for o in services.slot_options(self.store, other_day)], ["18:00"])
        with self.assertRaises(services.BookingError):
            self.book(self.users[0], at="18:00")
        self.book(self.users[0], at="12:00")
        self.book(self.users[1], day=other_day, at="18:00")

    def test_date_capacity_comes_from_the_date_schedule(self):
        self.set_date_slot(self.day, tables=1, seats=2)
        self.book(self.users[0], at="12:00")
        with self.assertRaisesMessage(services.BookingError, "เต็ม"):
            self.book(self.users[1], at="12:00")
        with self.assertRaisesMessage(services.BookingError, "up to 2"):
            self.book(self.users[2], guests=3, at="12:00")

    def test_closed_day_has_no_times(self):
        self.set_date_slot(self.day, available=False)
        self.assertEqual(services.slot_options(self.store, self.day), [])
        with self.assertRaises(services.BookingError):
            self.book(self.users[0], at="12:00")

    def test_date_schedule_works_for_a_store_without_usual_slots(self):
        plain = Restaurant.objects.create(slug="date-only", name="Date Only")
        plain.booking_slot_dates.create(
            date=self.day, time=time(12, 0), table_count=1, seats_per_table=4
        )
        self.assertTrue(services.uses_custom_slots(plain, self.day))
        self.assertFalse(services.uses_custom_slots(plain, self.day + timedelta(days=1)))
        services.create_booking(self.users[0], plain, self.day, "12:00", 2)


class BookingPageNextDayTests(SlotBookingBase):
    """Late in the day, tomorrow's morning time must still be bookable."""

    def test_tomorrow_morning_is_open_when_today_has_passed(self):
        BookingSlot.objects.create(
            restaurant=self.store, time=time(11, 0), table_count=1, seats_per_table=4
        )
        evening = datetime.combine(
            self.today, time(18, 18), tzinfo=timezone.get_current_timezone()
        ).astimezone(dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=evening):
            today_states = {o["value"]: o["state"] for o in services.slot_options(self.store, self.today)}
            next_states = {o["value"]: o["state"] for o in services.slot_options(self.store, self.day)}
            booking = services.create_booking(self.users[0], self.store, self.day, "11:00", 2)
        self.assertEqual(today_states["11:00"], "past")
        self.assertEqual(next_states["11:00"], "open")
        self.assertEqual(booking.time, time(11, 0))

    def test_page_versions_its_assets_and_tells_js_which_day_it_drew(self):
        self.client.force_login(self.users[0])
        response = self.client.get(reverse("booking", args=[self.store.slug]))
        self.assertContains(response, "booking.js?v=")
        self.assertContains(response, f'data-shown-day="{self.today.isoformat()}"')


class TableChoiceTests(SlotBookingBase):
    """The table given to a booking must seat the party; smallest fitting table first."""

    def setUp(self):
        super().setUp()
        self.slot.table_count = 3
        self.slot.seats_per_table = 6
        self.slot.save()

    def test_party_never_gets_a_table_that_is_too_small(self):
        small = self.store.tables.create(name="T1", capacity=2)
        booking = self.book(self.users[0], guests=6)
        self.assertNotEqual(booking.table_id, small.id)
        self.assertGreaterEqual(booking.table.capacity, 6)

    def test_smallest_fitting_table_and_natural_name_order(self):
        self.store.tables.create(name="T10", capacity=4)
        self.store.tables.create(name="T2", capacity=4)
        self.store.tables.create(name="T3", capacity=8)
        self.slot.seats_per_table = 8
        self.slot.save()
        self.assertEqual(self.book(self.users[0], guests=3).table.name, "T2")
        self.assertEqual(self.book(self.users[1], guests=3).table.name, "T10")
        self.assertEqual(self.book(self.users[2], guests=3).table.name, "T3")

    def test_booked_tables_are_skipped(self):
        self.store.tables.create(name="T1", capacity=6)
        self.store.tables.create(name="T2", capacity=6)
        first = self.book(self.users[0], guests=4)
        second = self.book(self.users[1], guests=4)
        self.assertNotEqual(first.table_id, second.table_id)


class BookingJsFallbackTests(SlotBookingBase):
    def test_script_restores_or_unlocks_instead_of_keeping_stale_states(self):
        from pathlib import Path

        source = Path("bookings/static/bookings/js/booking.js").read_text(encoding="utf-8")
        self.assertIn("const fallback", source)
        self.assertNotIn("unlockOtherDay", source)
        self.assertIn("shownSelect", source)
