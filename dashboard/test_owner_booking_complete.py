from datetime import time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from restaurants.models import Restaurant, Table

from .test_owner_bookings import PASSWORD, bookings_in, make_owner

User = get_user_model()


class CompleteTestBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.owner = make_owner("cm-owner")
        self.store = Restaurant.objects.create(owner=self.owner, slug="cm-mine", name="Mine")
        self.table = Table.objects.create(restaurant=self.store, name="T1", capacity=4)
        self.other_owner = make_owner("cm-other")
        self.other_store = Restaurant.objects.create(
            owner=self.other_owner, slug="cm-theirs", name="Theirs"
        )
        self.other_table = Table.objects.create(restaurant=self.other_store, name="X1", capacity=4)
        self.customer = User.objects.create_user("cm-customer", "cm@example.com", PASSWORD)
        # Today, late in the day: it can be completed now and the grace period
        # cannot turn it into a no-show while the tests run.
        self.day = self.today
        self.booking = self.book(self.table, at=time(23, 59))
        self.client.force_login(self.owner)

    def book(self, table, day=None, at=time(19, 0), **extra):
        return Booking.objects.create(
            user=self.customer, table=table, date=day or self.day, time=at, guests=2, **extra
        )

    def url(self, booking):
        return reverse("owner_booking_complete", args=[booking.id])

    def status_of(self, booking):
        booking.refresh_from_db()
        return booking.status


class OwnerBookingCompleteTests(CompleteTestBase):
    def test_owner_completes_and_returns_to_the_same_date(self):
        response = self.client.post(self.url(self.booking))
        self.assertRedirects(
            response, f"{reverse('owner_bookings')}?date={self.day.isoformat()}"
        )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.COMPLETED)
        self.assertIsNotNone(self.booking.completed_at)
        self.assertEqual(self.booking.completed_by, self.owner)

    def test_success_message_is_shown_on_the_page(self):
        response = self.client.post(self.url(self.booking), follow=True)
        self.assertContains(response, f"บันทึกการจอง {self.booking.code} เป็นเสร็จสิ้นแล้ว")

    def test_page_then_shows_the_booking_as_completed(self):
        self.client.post(self.url(self.booking))
        response = self.client.get(reverse("owner_bookings"), {"date": self.day.isoformat()})
        item = bookings_in(response)[0]
        self.assertEqual(item["status"], "completed")
        self.assertFalse(item["canComplete"])
        self.assertFalse(item["canCancel"])

    def test_cannot_complete_another_stores_booking(self):
        theirs = self.book(self.other_table)
        self.assertEqual(self.client.post(self.url(theirs)).status_code, 404)
        self.assertEqual(self.status_of(theirs), Booking.Status.CONFIRMED)
        theirs.refresh_from_db()
        self.assertIsNone(theirs.completed_by)

    def test_owner_without_a_store_cannot_complete(self):
        self.client.force_login(make_owner("cm-lonely"))
        self.assertEqual(self.client.post(self.url(self.booking)).status_code, 404)
        self.assertEqual(self.status_of(self.booking), Booking.Status.CONFIRMED)

    def test_booking_of_a_future_day_cannot_be_completed(self):
        future = self.book(self.table, day=self.today + timedelta(days=1))
        response = self.client.post(self.url(future), follow=True)
        self.assertContains(response, "ยังไม่ถึงวันที่จอง")
        self.assertEqual(self.status_of(future), Booking.Status.CONFIRMED)
        future.refresh_from_db()
        self.assertIsNone(future.completed_at)
        self.assertIsNone(future.completed_by)

    def test_get_does_not_change_the_status(self):
        self.assertEqual(self.client.get(self.url(self.booking)).status_code, 405)
        self.assertEqual(self.status_of(self.booking), Booking.Status.CONFIRMED)

    def test_customer_cannot_use_the_endpoint(self):
        self.client.force_login(self.customer)
        self.client.post(self.url(self.booking))
        self.assertEqual(self.status_of(self.booking), Booking.Status.CONFIRMED)

    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        response = self.client.post(self.url(self.booking))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.status_of(self.booking), Booking.Status.CONFIRMED)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url(self.booking)).status_code, 403)
        self.assertEqual(self.status_of(self.booking), Booking.Status.CONFIRMED)

    def test_cancelled_booking_cannot_be_completed(self):
        cancelled = self.book(self.table, at=time(20, 30), status=Booking.Status.CANCELLED)
        response = self.client.post(self.url(cancelled), follow=True)
        self.assertContains(response, "การจองที่ยกเลิกแล้วไม่สามารถเปลี่ยนเป็นเสร็จสิ้นได้")
        self.assertEqual(self.status_of(cancelled), Booking.Status.CANCELLED)

    def test_completing_twice_keeps_the_first_record(self):
        self.client.post(self.url(self.booking))
        self.booking.refresh_from_db()
        first = self.booking.completed_at
        second_owner_view = self.client.post(self.url(self.booking), follow=True)
        self.assertContains(second_owner_view, "การจองนี้เสร็จสิ้นไปแล้ว")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.completed_at, first)

    def test_no_show_can_be_completed_on_its_day(self):
        booking = self.book(self.table, day=self.today, status=Booking.Status.NO_SHOW)
        self.client.post(self.url(booking))
        self.assertEqual(self.status_of(booking), Booking.Status.COMPLETED)
        booking.refresh_from_db()
        self.assertEqual(booking.completed_by, self.owner)

    def test_no_show_cannot_be_completed_after_its_day(self):
        booking = self.book(
            self.table, day=self.today - timedelta(days=1), status=Booking.Status.NO_SHOW
        )
        response = self.client.post(self.url(booking), follow=True)
        self.assertContains(response, "เลยวันที่จองแล้ว")
        self.assertEqual(self.status_of(booking), Booking.Status.NO_SHOW)
        booking.refresh_from_db()
        self.assertIsNone(booking.completed_at)

    def test_overdue_confirmed_booking_is_a_locked_no_show_by_the_time_of_the_request(self):
        booking = self.book(self.table, day=self.today - timedelta(days=2))
        self.client.post(self.url(booking))
        self.assertEqual(self.status_of(booking), Booking.Status.NO_SHOW)

    def test_unknown_booking_is_404(self):
        url = reverse("owner_booking_complete", args=[999999])
        self.assertEqual(self.client.post(url).status_code, 404)


class OwnerBookingsPageStatusTests(CompleteTestBase):
    """The Booking Details data and markup the owner page hands to the browser."""

    def page(self, day):
        return self.client.get(reverse("owner_bookings"), {"date": day.isoformat()})

    def test_flags_for_every_status(self):
        day = self.today + timedelta(days=5)
        confirmed = self.book(self.table, day=day, at=time(11, 30))
        completed = self.book(self.table, day=day, at=time(13, 0), status=Booking.Status.COMPLETED)
        cancelled = self.book(self.table, day=day, at=time(17, 30), status=Booking.Status.CANCELLED)
        flags = {
            item["id"]: (item["status"], item["canComplete"], item["canCancel"])
            for item in bookings_in(self.page(day))
        }
        # Confirmed but still days away: it can be cancelled, not completed yet.
        self.assertEqual(flags[confirmed.code], ("confirmed", False, True))
        self.assertEqual(flags[completed.code], ("completed", False, False))
        self.assertEqual(flags[cancelled.code], ("cancelled", False, False))

    def test_confirmed_booking_of_today_can_be_completed(self):
        item = next(i for i in bookings_in(self.page(self.today)) if i["id"] == self.booking.code)
        self.assertEqual((item["status"], item["canComplete"]), ("confirmed", True))

    def test_no_show_flags_follow_the_booking_day(self):
        today_no_show = self.book(self.table, day=self.today, status=Booking.Status.NO_SHOW)
        old = self.book(
            self.table, day=self.today - timedelta(days=1), status=Booking.Status.NO_SHOW
        )
        today_item = bookings_in(self.page(self.today))[0]
        old_item = bookings_in(self.page(self.today - timedelta(days=1)))[0]
        self.assertEqual(
            (today_item["id"], today_item["status"], today_item["canComplete"]),
            (today_no_show.code, "no_show", True),
        )
        self.assertEqual(
            (old_item["id"], old_item["status"], old_item["canComplete"]),
            (old.code, "no_show", False),
        )

    def test_opening_the_page_marks_overdue_bookings_as_no_show(self):
        overdue = self.book(self.table, day=self.today - timedelta(days=3))
        item = bookings_in(self.page(overdue.date))[0]
        self.assertEqual(item["status"], "no_show")
        self.assertEqual(self.status_of(overdue), Booking.Status.NO_SHOW)

    def test_other_stores_bookings_are_not_touched_by_the_page(self):
        theirs = self.book(self.other_table, day=self.today - timedelta(days=3))
        self.page(self.today)
        self.assertEqual(self.status_of(theirs), Booking.Status.CONFIRMED)

    def test_summary_card_is_reserved_not_confirmed(self):
        response = self.page(self.day)
        self.assertContains(response, "<small>Reserved</small>")
        self.assertContains(response, "data-summary-reserved")
        self.assertNotContains(response, "data-summary-confirmed")

    def test_reserved_count_is_computed_from_confirmed_and_completed(self):
        js = (settings.BASE_DIR / "dashboard/static/dashboard/js/owner_bookings.js").read_text(encoding="utf-8")
        line = next(l for l in js.splitlines() if "data-summary-reserved" in l)
        self.assertIn('item.status === "confirmed" || item.status === "completed"', line)

    def test_page_renders_csrf_protected_complete_form_and_filters(self):
        response = self.page(self.day)
        self.assertContains(response, "data-complete-form")
        self.assertContains(response, "Mark as Completed")
        self.assertContains(response, 'data-booking-filter="completed"')
        self.assertContains(response, 'data-booking-filter="no_show"')
        # The summary card counts confirmed + completed (computed in owner_bookings.js).
        self.assertContains(response, "<small>Reserved</small>")
        self.assertContains(response, "data-summary-reserved")
        self.assertNotContains(response, "data-summary-confirmed")
        self.assertContains(response, "csrfmiddlewaretoken")


class StoreGracePeriodSettingTests(TestCase):
    def setUp(self):
        self.owner = make_owner("gp-owner")
        self.store = Restaurant.objects.create(owner=self.owner, slug="gp-store", name="Store")
        self.client.force_login(self.owner)

    def post(self, **extra):
        data = {"name": "Store", "category": "Restaurant"}
        data.update(extra)
        return self.client.post(reverse("owner_store_update", args=[self.store.slug]), data)

    def test_owner_can_change_the_grace_period(self):
        self.post(no_show_grace_minutes="45")
        self.store.refresh_from_db()
        self.assertEqual(self.store.no_show_grace_minutes, 45)

    def test_blank_value_keeps_the_current_one(self):
        self.store.no_show_grace_minutes = 50
        self.store.save()
        self.post(no_show_grace_minutes="")
        self.store.refresh_from_db()
        self.assertEqual(self.store.no_show_grace_minutes, 50)

    def test_out_of_range_values_are_rejected(self):
        for bad in ("-1", "241", "abc"):
            with self.subTest(value=bad):
                self.post(no_show_grace_minutes=bad)
                self.store.refresh_from_db()
                self.assertEqual(self.store.no_show_grace_minutes, 30)

    def test_new_stores_default_to_30_minutes(self):
        owner = make_owner("gp-new")
        self.client.force_login(owner)
        self.client.post(
            reverse("owner_store_create"),
            {"name": "Brand New", "category": "Restaurant"},
        )
        self.assertEqual(Restaurant.objects.get(owner=owner).no_show_grace_minutes, 30)

    def test_dashboard_exposes_the_current_value_to_the_edit_form(self):
        response = self.client.get(reverse("owner_dashboard"))
        self.assertContains(response, "noShowGraceMinutes")
        self.assertContains(response, 'name="no_show_grace_minutes"')
