import json
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from restaurants.models import Restaurant, Table

User = get_user_model()
PASSWORD = "Queue-pass-2026"


def make_owner(username):
    return User.objects.create_user(
        username, f"{username}@example.com", PASSWORD, role=User.Role.OWNER
    )


def bookings_in(response):
    """The list the page hands to owner_bookings.js through json_script."""
    html = response.content.decode()
    marker = '<script id="bookings-data" type="application/json">'
    start = html.index(marker) + len(marker)
    return json.loads(html[start : html.index("</script>", start)])


class OwnerBookingsPageTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.owner = make_owner("bk-owner")
        self.store = Restaurant.objects.create(owner=self.owner, slug="mine", name="Mine")
        self.table = Table.objects.create(restaurant=self.store, name="T1", capacity=4)
        self.table2 = Table.objects.create(restaurant=self.store, name="A1", capacity=2)

        self.other_owner = make_owner("bk-other")
        self.other_store = Restaurant.objects.create(
            owner=self.other_owner, slug="theirs", name="Theirs"
        )
        self.other_table = Table.objects.create(restaurant=self.other_store, name="X1", capacity=4)

        self.customer = User.objects.create_user(
            "bk-customer", "bk-customer@example.com", PASSWORD,
            first_name="Somchai", last_name="Jaidee",
        )
        self.plain_customer = User.objects.create_user(
            "bk-plain", "bk-plain@example.com", PASSWORD
        )
        self.client.force_login(self.owner)

    def book(self, table, day=None, at=time(19, 0), guests=2, user=None, **extra):
        return Booking.objects.create(
            user=user or self.customer, table=table, date=day or self.today,
            time=at, guests=guests, **extra,
        )

    def get_page(self, **params):
        return self.client.get(reverse("owner_bookings"), params)

    def test_page_has_no_mockup_text(self):
        response = self.get_page()
        self.assertEqual(response.status_code, 200)
        for text in ("SAMPLE DATA", "Booking preview", "Sample bookings", "SAMPLE"):
            self.assertNotContains(response, text)

    def test_owner_sees_own_bookings_for_the_day(self):
        mine = self.book(self.table, guests=3)
        response = self.get_page()
        data = bookings_in(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(
            data[0],
            {
                "id": f"B{mine.id:03d}",
                "time": "19:00",
                "name": "Somchai Jaidee",
                "party": 3,
                "table": "T1",
                "status": "confirmed",
                "cancelUrl": reverse("owner_booking_cancel", args=[mine.id]),
            },
        )
        self.assertContains(response, reverse("owner_queue"))

    def test_name_falls_back_to_username(self):
        self.book(self.table, user=self.plain_customer)
        self.assertEqual(bookings_in(self.get_page())[0]["name"], "bk-plain")

    def test_does_not_show_other_stores_or_other_days(self):
        self.book(self.other_table)
        self.book(self.table, day=self.today + timedelta(days=1))
        self.assertEqual(bookings_in(self.get_page()), [])

    def test_cancelled_bookings_are_included(self):
        self.book(self.table, status=Booking.Status.CANCELLED)
        data = bookings_in(self.get_page())
        self.assertEqual([item["status"] for item in data], ["cancelled"])

    def test_sorted_by_time_then_table_name(self):
        self.book(self.table, at=time(20, 30))
        self.book(self.table, at=time(11, 30))
        self.book(self.table2, at=time(19, 0))
        self.book(self.table, at=time(19, 0), user=self.plain_customer)
        data = bookings_in(self.get_page())
        self.assertEqual(
            [(item["time"], item["table"]) for item in data],
            [("11:30", "T1"), ("19:00", "A1"), ("19:00", "T1"), ("20:30", "T1")],
        )

    def test_date_parameter_selects_the_day(self):
        tomorrow = self.today + timedelta(days=1)
        self.book(self.table, day=tomorrow)
        response = self.get_page(date=tomorrow.isoformat())
        self.assertEqual(len(bookings_in(response)), 1)
        self.assertContains(response, f'value="{tomorrow.isoformat()}"')

    def test_invalid_date_uses_today(self):
        self.book(self.table)
        for bad in ("not-a-date", "2026-13-40", "06/11/2026", ""):
            with self.subTest(date=bad):
                response = self.get_page(date=bad)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(bookings_in(response)), 1)
                self.assertContains(response, f'value="{self.today.isoformat()}"')

    @override_settings(BOOKING_MAX_ADVANCE_MONTHS=1)
    def test_owner_can_view_dates_beyond_the_booking_window(self):
        far = self.today + timedelta(days=400)
        self.book(self.table, day=far)
        past = self.today - timedelta(days=30)
        self.book(self.table, day=past)
        for day in (far, past):
            with self.subTest(day=day):
                self.assertEqual(len(bookings_in(self.get_page(date=day.isoformat()))), 1)

    def test_owner_without_a_store_gets_an_empty_page(self):
        lonely = make_owner("bk-lonely")
        self.client.force_login(lonely)
        response = self.get_page()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(bookings_in(response), [])
        self.assertContains(response, "ยังไม่มีร้าน")
        self.assertContains(response, "Add a store")

    def test_customer_cannot_open_the_page(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.get_page().status_code, 302)


class OwnerBookingCancelTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.owner = make_owner("cx-owner")
        self.store = Restaurant.objects.create(owner=self.owner, slug="cx-mine", name="Mine")
        self.table = Table.objects.create(restaurant=self.store, name="T1", capacity=4)
        self.other_owner = make_owner("cx-other")
        self.other_store = Restaurant.objects.create(
            owner=self.other_owner, slug="cx-theirs", name="Theirs"
        )
        self.other_table = Table.objects.create(restaurant=self.other_store, name="X1", capacity=4)
        self.customer = User.objects.create_user("cx-customer", "cx@example.com", PASSWORD)
        self.day = self.today + timedelta(days=3)
        self.booking = Booking.objects.create(
            user=self.customer, table=self.table, date=self.day, time=time(19, 0), guests=2
        )
        self.client.force_login(self.owner)

    def url(self, booking):
        return reverse("owner_booking_cancel", args=[booking.id])

    def test_owner_can_cancel_and_returns_to_the_same_date(self):
        response = self.client.post(self.url(self.booking))
        self.assertRedirects(
            response, f"{reverse('owner_bookings')}?date={self.day.isoformat()}"
        )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertIsNotNone(self.booking.cancelled_at)

    def test_success_message_is_shown_on_the_page(self):
        response = self.client.post(self.url(self.booking), follow=True)
        self.assertContains(response, f"ยกเลิกการจอง B{self.booking.id:03d} แล้ว")

    def test_cancelling_twice_is_harmless(self):
        self.client.post(self.url(self.booking))
        response = self.client.post(self.url(self.booking))
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)

    def test_cannot_cancel_another_stores_booking(self):
        theirs = Booking.objects.create(
            user=self.customer, table=self.other_table, date=self.day,
            time=time(19, 0), guests=2,
        )
        response = self.client.post(self.url(theirs))
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, Booking.Status.CONFIRMED)

    def test_owner_without_a_store_cannot_cancel(self):
        self.client.force_login(make_owner("cx-lonely"))
        self.assertEqual(self.client.post(self.url(self.booking)).status_code, 404)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url(self.booking))
        self.assertEqual(response.status_code, 405)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_unknown_booking_is_404(self):
        self.assertEqual(
            self.client.post(reverse("owner_booking_cancel", args=[999999])).status_code, 404
        )

    def test_customer_cannot_use_the_endpoint(self):
        self.client.force_login(self.customer)
        self.client.post(self.url(self.booking))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        response = self.client.post(self.url(self.booking))
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_csrf_is_enforced(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url(self.booking)).status_code, 403)

    def test_page_renders_a_csrf_protected_cancel_form(self):
        response = self.client.get(reverse("owner_bookings"))
        self.assertContains(response, "data-cancel-form")
        self.assertContains(response, "csrfmiddlewaretoken")


class BookingsForDayServiceTests(TestCase):
    def test_returns_only_that_restaurants_bookings_for_the_day(self):
        from bookings import services

        owner = make_owner("svc-owner")
        store = Restaurant.objects.create(owner=owner, slug="svc-a", name="A")
        other = Restaurant.objects.create(slug="svc-b", name="B")
        t1 = Table.objects.create(restaurant=store, name="T1", capacity=2)
        t2 = Table.objects.create(restaurant=other, name="T2", capacity=2)
        customer = User.objects.create_user("svc-c", "svc-c@example.com", PASSWORD)
        day = date(2026, 12, 1)
        keep = Booking.objects.create(user=customer, table=t1, date=day, time=time(19, 0), guests=2)
        gone = Booking.objects.create(
            user=customer, table=t1, date=day, time=time(20, 30), guests=2,
            status=Booking.Status.CANCELLED,
        )
        Booking.objects.create(user=customer, table=t2, date=day, time=time(19, 0), guests=2)
        Booking.objects.create(
            user=customer, table=t1, date=day + timedelta(days=1), time=time(19, 0), guests=2
        )
        self.assertEqual(list(services.bookings_for_day(store, day)), [keep, gone])
