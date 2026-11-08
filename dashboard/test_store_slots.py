"""Owner edits booking slots on Store Details: parse, save (JSON + plain), permissions."""

from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings import services as booking_services
from bookings.models import Booking
from restaurants import services
from restaurants.models import BookingSlot, Restaurant

from .store_test_utils import AJAX, make_owner, valid_data


def slot_fields(*rows):
    """rows: (time, tables, seats, available) -> the repeated fields the page posts."""
    return {
        "slots_present": "1",
        "slot_time": [r[0] for r in rows],
        "slot_tables": [str(r[1]) for r in rows],
        "slot_seats": [str(r[2]) for r in rows],
        "slot_available": [r[3] if len(r) > 3 else "1" for r in rows],
    }


class ParseBookingSlotsTests(TestCase):
    def parse(self, times, tables, seats, available=None):
        return services.parse_booking_slots(times, tables, seats, available or ["1"] * len(times))

    def test_valid_rows_and_blank_rows_skipped(self):
        rows = self.parse(["18:00", "", "19:30"], ["3", "", "2"], ["4", "", "6"], ["1", "1", "0"])
        self.assertEqual(
            [(r["time"], r["table_count"], r["seats_per_table"], r["is_available"]) for r in rows],
            [(time(18, 0), 3, 4, True), (time(19, 30), 2, 6, False)],
        )

    def test_rejects_bad_rows(self):
        for times, tables, seats in (
            (["xx"], ["2"], ["4"]),
            (["18:00", "18:00"], ["2", "2"], ["4", "4"]),
            (["18:00"], ["0"], ["4"]),
            (["18:00"], ["2"], ["13"]),
            (["18:00"], ["abc"], ["4"]),
            (["18:00"], ["2"], [""]),
        ):
            with self.subTest(times=times, tables=tables, seats=seats):
                with self.assertRaises(services.RestaurantError):
                    self.parse(times, tables, seats)

    def test_too_many_slots(self):
        times = [f"{h:02d}:{m}" for h in range(8, 20) for m in ("00", "30")][:21]
        with self.assertRaises(services.RestaurantError):
            self.parse(times, ["1"] * 21, ["2"] * 21)


class StoreSlotsPageTests(TestCase):
    def setUp(self):
        self.owner = make_owner("slot-owner")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="slot-page", name="Slot Page", address="1 Rd"
        )
        self.url = reverse("owner_store_details")
        self.client.force_login(self.owner)

    def post(self, rows, ajax=True, **fields):
        data = {**valid_data(name="Slot Page", address="1 Rd"), **slot_fields(*rows), **fields}
        return self.client.post(self.url, data, **(AJAX if ajax else {}))

    def test_page_shows_default_slots_until_saved(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="slot_time"', count=len(booking_services.SLOTS))
        self.assertContains(response, "default times")
        self.assertFalse(BookingSlot.objects.exists())

    def test_save_creates_slots_and_returns_them(self):
        response = self.post([("18:00", 3, 4), ("20:00", 2, 6, "0")])
        self.assertEqual(response.status_code, 200)
        slots = list(BookingSlot.objects.order_by("time"))
        self.assertEqual([(s.time, s.table_count, s.seats_per_table, s.is_available) for s in slots],
                         [(time(18, 0), 3, 4, True), (time(20, 0), 2, 6, False)])
        self.assertEqual(response.json()["booking_slots"][1]["available"], False)
        self.assertNotContains(self.client.get(self.url), "default times")

    def test_save_updates_and_removes_but_keeps_existing_bookings(self):
        self.post([("18:00", 2, 4), ("20:00", 1, 2)])
        customer = make_owner("slot-guest")
        day = timezone.localdate() + timedelta(days=1)
        booking = booking_services.create_booking(customer, self.store, day, "20:00", 2)
        response = self.post([("18:00", 5, 8)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BookingSlot.objects.get().table_count, 5)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_invalid_rows_save_nothing_at_all(self):
        self.store.name = "Before"
        self.store.save()
        response = self.post([("18:00", 0, 4)], name="After")
        self.assertEqual(response.status_code, 400)
        self.assertIn("booking_slots", response.json()["errors"])
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Before")
        self.assertFalse(BookingSlot.objects.exists())

    def test_plain_form_post_redirects_and_saves(self):
        response = self.post([("18:00", 2, 4)], ajax=False)
        self.assertRedirects(response, self.url)
        self.assertEqual(BookingSlot.objects.count(), 1)

    def test_invalid_plain_post_redraws_the_typed_rows(self):
        response = self.post([("18:00", 0, 4)], ajax=False)
        self.assertContains(response, "จำนวนโต๊ะ")
        self.assertContains(response, 'value="18:00"')

    def test_empty_table_returns_to_default_slots(self):
        self.post([("18:00", 2, 4)])
        response = self.post([])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BookingSlot.objects.exists())

    def test_posts_without_slots_present_leave_slots_alone(self):
        self.post([("18:00", 2, 4)])
        self.client.post(self.url, valid_data(name="Renamed", address="1 Rd"), **AJAX)
        self.assertEqual(BookingSlot.objects.count(), 1)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Renamed")

    def test_cannot_touch_another_owners_slots(self):
        other = make_owner("slot-other")
        other_store = Restaurant.objects.create(owner=other, slug="slot-theirs", name="Theirs")
        BookingSlot.objects.create(restaurant=other_store, time=time(9, 0), table_count=1, seats_per_table=2)
        self.post([("18:00", 2, 4)])
        self.assertEqual(other_store.booking_slots.count(), 1)
        self.assertEqual(self.store.booking_slots.count(), 1)

    def test_confirm_dialog_is_on_the_page(self):
        self.assertContains(self.client.get(self.url), "ยืนยันการเปลี่ยนแปลง")
