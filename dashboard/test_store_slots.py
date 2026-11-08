"""Owner edits booking slots on Store Details: parse, save (JSON + plain), permissions."""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings import services as booking_services
from bookings.models import Booking
from restaurants import services
from restaurants.models import BookingSlot, Restaurant

from .store_test_utils import AJAX, PASSWORD, make_owner, valid_data


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


class StoreDateScheduleTests(TestCase):
    def setUp(self):
        self.owner = make_owner("cal-owner")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="cal-store", name="Cal Store", address="1 Rd"
        )
        self.url = reverse("owner_store_details")
        self.client.force_login(self.owner)
        self.day = timezone.localdate() + timedelta(days=3)

    def post(self, rows, day=None, ajax=True):
        data = {**valid_data(name="Cal Store", address="1 Rd"), **slot_fields(*rows)}
        data["slots_date"] = day.isoformat() if day else ""
        return self.client.post(self.url, data, **(AJAX if ajax else {}))

    def test_saving_with_a_date_sets_only_that_dates_schedule(self):
        self.post([("18:00", 2, 4)])
        response = self.post([("12:00", 1, 2)], day=self.day)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.booking_slots.get().time, time(18, 0))
        override = self.store.booking_slot_dates.get()
        self.assertEqual((override.date, override.time, override.table_count), (self.day, time(12, 0), 1))
        self.assertEqual(response.json()["custom_dates"], [self.day.isoformat()])
        self.assertEqual(response.json()["booking_slots"][0]["time"], "12:00")

    def test_saving_a_date_again_replaces_it_and_empty_rows_remove_it(self):
        self.post([("12:00", 1, 2), ("13:00", 1, 2)], day=self.day)
        self.assertEqual(self.store.booking_slot_dates.count(), 2)
        self.post([("14:00", 3, 4)], day=self.day)
        self.assertEqual([o.time for o in self.store.booking_slot_dates.all()], [time(14, 0)])
        self.post([], day=self.day)
        self.assertFalse(self.store.booking_slot_dates.exists())

    def test_date_outside_the_booking_window_is_rejected(self):
        for bad in (timezone.localdate() - timedelta(days=1), timezone.localdate() + timedelta(days=400)):
            with self.subTest(day=bad):
                response = self.post([("12:00", 1, 2)], day=bad)
                self.assertEqual(response.status_code, 400)
                self.assertIn("booking_slots", response.json()["errors"])
        self.assertFalse(self.store.booking_slot_dates.exists())

    def test_closing_a_day_hides_it_from_customers(self):
        self.post([("12:00", 1, 2, "0")], day=self.day)
        slots = booking_services.slot_options(self.store, self.day)
        self.assertEqual(slots, [])

    def test_slots_endpoint_reports_source_and_booked_counts(self):
        url = reverse("owner_slots")
        data = self.client.get(url, {"date": self.day.isoformat()}).json()
        self.assertEqual(data["source"], "default")
        self.post([("12:00", 2, 4)], day=self.day)
        guest = make_owner("cal-guest")
        booking_services.create_booking(guest, self.store, self.day, "12:00", 2)
        data = self.client.get(url, {"date": self.day.isoformat()}).json()
        self.assertEqual(data["source"], "date")
        self.assertEqual((data["rows"][0]["time"], data["rows"][0]["booked"]), ("12:00", 1))

    def test_slots_endpoint_validates_date_and_needs_a_store(self):
        url = reverse("owner_slots")
        self.assertEqual(self.client.get(url, {"date": "nope"}).status_code, 400)
        lonely = make_owner("cal-lonely")
        self.client.force_login(lonely)
        self.assertEqual(self.client.get(url, {"date": self.day.isoformat()}).status_code, 404)

    def test_slots_endpoint_is_for_owners_only(self):
        customer = get_user_model().objects.create_user("cal-cust", "cal-cust@example.com", PASSWORD)
        self.client.force_login(customer)
        response = self.client.get(reverse("owner_slots"), {"date": self.day.isoformat()})
        self.assertNotEqual(response.status_code, 200)

    def test_page_has_calendar_and_marks_dates_with_own_schedule(self):
        self.post([("12:00", 1, 2)], day=self.day)
        response = self.client.get(self.url)
        self.assertContains(response, "data-calendar")
        self.assertContains(response, f'data-custom-dates="{self.day.isoformat()}"')

    def test_other_owners_date_schedules_are_untouched(self):
        other = make_owner("cal-other")
        other_store = Restaurant.objects.create(owner=other, slug="cal-theirs", name="Theirs")
        other_store.booking_slot_dates.create(
            date=self.day, time=time(9, 0), table_count=1, seats_per_table=2
        )
        self.post([("12:00", 1, 2)], day=self.day)
        self.assertEqual(other_store.booking_slot_dates.count(), 1)


class DefaultRowsAreNotSavedByAccidentTests(TestCase):
    """Renaming the store must not silently switch it to its own slots."""

    def setUp(self):
        self.owner = make_owner("def-owner")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="def-store", name="Def Store", address="1 Rd"
        )
        for name, seats in (("T1", 2), ("T2", 2), ("T3", 2), ("T4", 8)):
            self.store.tables.create(name=name, capacity=seats)
        self.url = reverse("owner_store_details")
        self.client.force_login(self.owner)

    def default_rows(self):
        return [(t, 4, 2, "1") for t in booking_services.SLOTS]

    def test_posting_the_untouched_default_rows_saves_nothing(self):
        data = {**valid_data(name="Renamed", address="1 Rd"), **slot_fields(*self.default_rows())}
        response = self.client.post(self.url, data, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BookingSlot.objects.exists())
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Renamed")

    def test_editing_a_row_does_save(self):
        rows = self.default_rows()
        rows[0] = (rows[0][0], 2, 2, "1")
        data = {**valid_data(name="Def Store", address="1 Rd"), **slot_fields(*rows)}
        self.client.post(self.url, data, **AJAX)
        self.assertEqual(BookingSlot.objects.count(), len(rows))

    def test_default_suggestion_uses_the_common_table_size(self):
        shown = self.client.get(self.url).context["slot_rows"]
        self.assertEqual({(r["table_count"], r["seats"]) for r in shown}, {(4, 2)})

    def test_suggestion_never_exceeds_the_form_limits(self):
        from restaurants.models import MAX_SEATS_PER_TABLE, MAX_TABLES_PER_SLOT

        self.store.tables.all().delete()
        for index in range(MAX_TABLES_PER_SLOT + 5):
            self.store.tables.create(name=f"B{index}", capacity=MAX_SEATS_PER_TABLE + 4)
        shown = self.client.get(self.url).context["slot_rows"]
        self.assertTrue(all(r["table_count"] <= MAX_TABLES_PER_SLOT for r in shown))
        self.assertTrue(all(r["seats"] <= MAX_SEATS_PER_TABLE for r in shown))

    def test_unchanged_date_rows_are_not_saved_either(self):
        day = timezone.localdate() + timedelta(days=2)
        shown = self.client.get(reverse("owner_slots"), {"date": day.isoformat()}).json()["rows"]
        rows = [(r["time"], r["table_count"], r["seats"], "1") for r in shown]
        data = {**valid_data(name="Def Store", address="1 Rd"), **slot_fields(*rows), "slots_date": day.isoformat()}
        self.client.post(self.url, data, **AJAX)
        self.assertFalse(self.store.booking_slot_dates.exists())

    def test_page_script_only_sends_slots_when_the_table_is_edited(self):
        from pathlib import Path

        source = Path("dashboard/static/dashboard/js/owner_store_details.js").read_text(encoding="utf-8")
        self.assertIn("presentInput.disabled = !value", source)
        self.assertContains(self.client.get(self.url), "data-slots-present")
