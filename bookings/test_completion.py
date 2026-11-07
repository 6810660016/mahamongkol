from datetime import date, datetime, time, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from restaurants.models import Restaurant, Table

from . import services
from .models import Booking

User = get_user_model()
PASSWORD = "Queue-pass-2026"
DAY = date(2026, 12, 1)


def at(day, hour, minute=0):
    """An aware datetime in the project time zone (Asia/Bangkok)."""
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def make_user(username, role=User.Role.USER):
    return User.objects.create_user(
        username, f"{username}@example.com", PASSWORD, role=role
    )


class CompletionBase(TestCase):
    def setUp(self):
        self.owner = make_user("cp-owner", User.Role.OWNER)
        self.other_owner = make_user("cp-other-owner", User.Role.OWNER)
        self.customer = make_user("cp-customer")
        self.other_customer = make_user("cp-other-customer")
        self.store = Restaurant.objects.create(owner=self.owner, slug="cp-a", name="A")
        self.other_store = Restaurant.objects.create(
            owner=self.other_owner, slug="cp-b", name="B"
        )
        self.table = Table.objects.create(restaurant=self.store, name="T1", capacity=4)
        self.other_table = Table.objects.create(
            restaurant=self.other_store, name="X1", capacity=4
        )

    def book(self, table=None, day=DAY, at_time=time(19, 0), user=None, **extra):
        return Booking.objects.create(
            user=user or self.customer, table=table or self.table, date=day,
            time=at_time, guests=2, **extra,
        )


class CompleteBookingTests(CompletionBase):
    def test_owner_completes_own_confirmed_booking(self):
        booking = self.book()
        now = at(DAY, 20, 0)
        services.complete_booking(booking, self.owner, now=now)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)
        self.assertEqual(booking.completed_at, now)
        self.assertEqual(booking.completed_by, self.owner)

    def test_other_owner_customer_and_anonymous_style_users_are_refused(self):
        booking = self.book()
        for user in (self.other_owner, self.customer, self.other_customer):
            with self.subTest(user=user.username), self.assertRaises(services.BookingError):
                services.complete_booking(booking, user)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertIsNone(booking.completed_at)
        self.assertIsNone(booking.completed_by)

    def test_cancelled_booking_cannot_be_completed(self):
        booking = self.book(status=Booking.Status.CANCELLED)
        with self.assertRaises(services.BookingError):
            services.complete_booking(booking, self.owner)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_completing_twice_is_rejected_and_keeps_the_first_record(self):
        booking = self.book()
        first = at(DAY, 20, 0)
        services.complete_booking(booking, self.owner, now=first)
        with self.assertRaises(services.BookingError):
            services.complete_booking(booking, self.owner, now=at(DAY, 21, 0))
        booking.refresh_from_db()
        self.assertEqual(booking.completed_at, first)
        self.assertEqual(booking.completed_by, self.owner)

    def test_stale_object_cannot_overwrite_a_completed_booking(self):
        booking = self.book()
        stale = Booking.objects.get(pk=booking.pk)
        services.complete_booking(booking, self.owner, now=at(DAY, 20, 0))
        with self.assertRaises(services.BookingError):
            services.complete_booking(stale, self.owner, now=at(DAY, 22, 0))
        booking.refresh_from_db()
        self.assertEqual(booking.completed_at, at(DAY, 20, 0))

    def test_confirmed_booking_can_be_completed_early_on_its_own_day(self):
        booking = self.book()  # 19:00
        self.assertTrue(services.can_complete(booking, now=at(DAY, 0, 0)))
        services.complete_booking(booking, self.owner, now=at(DAY, 18, 30))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_confirmed_booking_of_a_future_day_cannot_be_completed(self):
        booking = self.book()
        day_before = at(DAY - timedelta(days=1), 23, 59)
        self.assertFalse(services.can_complete(booking, now=day_before))
        with self.assertRaises(services.BookingError):
            services.complete_booking(booking, self.owner, now=day_before)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertIsNone(booking.completed_at)
        self.assertIsNone(booking.completed_by)

    def test_no_show_can_be_completed_until_the_end_of_its_day(self):
        booking = self.book(status=Booking.Status.NO_SHOW)
        self.assertTrue(services.can_complete(booking, now=at(DAY, 23, 59)))
        services.complete_booking(booking, self.owner, now=at(DAY, 23, 59))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_no_show_is_locked_from_the_next_day(self):
        booking = self.book(status=Booking.Status.NO_SHOW)
        next_day = at(DAY + timedelta(days=1), 0, 1)
        self.assertFalse(services.can_complete(booking, now=next_day))
        with self.assertRaises(services.BookingError):
            services.complete_booking(booking, self.owner, now=next_day)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.NO_SHOW)

    def test_admin_role_can_complete_any_booking(self):
        admin = make_user("cp-admin", User.Role.ADMIN)
        booking = self.book()
        services.complete_booking(booking, admin, now=at(DAY, 20, 0))
        booking.refresh_from_db()
        self.assertEqual(booking.completed_by, admin)

    def test_completed_slot_does_not_block_a_new_confirmed_booking(self):
        booking = self.book()
        services.complete_booking(booking, self.owner, now=at(DAY, 20, 0))
        self.book(user=self.other_customer)  # same table, date and time

    def test_completed_booking_cannot_be_cancelled(self):
        booking = self.book(status=Booking.Status.COMPLETED)
        with self.assertRaises(services.BookingError):
            services.cancel_booking(booking, self.customer)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_no_show_booking_cannot_be_cancelled(self):
        booking = self.book(status=Booking.Status.NO_SHOW)
        with self.assertRaises(services.BookingError):
            services.cancel_booking(booking, self.owner)

    def test_existing_confirmed_booking_can_still_be_cancelled(self):
        booking = self.book()
        services.cancel_booking(booking, self.customer)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertIsNotNone(booking.cancelled_at)


class MarkNoShowsTests(CompletionBase):
    def test_becomes_no_show_only_after_the_grace_period(self):
        booking = self.book()  # 19:00, default grace 30 minutes
        for minute, expected in ((29, "confirmed"), (30, "confirmed"), (31, "no_show")):
            with self.subTest(minute=minute):
                services.mark_no_shows(now=at(DAY, 19, minute))
                booking.refresh_from_db()
                self.assertEqual(booking.status, expected)

    def test_grace_period_is_per_restaurant(self):
        self.other_store.no_show_grace_minutes = 90
        self.other_store.save()
        mine = self.book()
        theirs = self.book(table=self.other_table)
        services.mark_no_shows(now=at(DAY, 20, 0))
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual(mine.status, Booking.Status.NO_SHOW)
        self.assertEqual(theirs.status, Booking.Status.CONFIRMED)
        services.mark_no_shows(now=at(DAY, 20, 31))
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, Booking.Status.NO_SHOW)

    def test_zero_grace_means_no_show_right_after_the_time(self):
        self.store.no_show_grace_minutes = 0
        self.store.save()
        booking = self.book()
        services.mark_no_shows(now=at(DAY, 19, 1))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.NO_SHOW)

    def test_default_grace_is_30_minutes(self):
        self.assertEqual(self.store.no_show_grace_minutes, 30)

    def test_other_statuses_are_untouched(self):
        completed = self.book(at_time=time(11, 30), status=Booking.Status.COMPLETED)
        cancelled = self.book(at_time=time(13, 0), status=Booking.Status.CANCELLED)
        services.mark_no_shows(now=at(DAY, 23, 0))
        completed.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual(completed.status, Booking.Status.COMPLETED)
        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)

    def test_future_bookings_are_untouched(self):
        booking = self.book(day=DAY + timedelta(days=1))
        services.mark_no_shows(now=at(DAY, 23, 0))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_is_idempotent_and_reports_the_count(self):
        self.book()
        self.assertEqual(services.mark_no_shows(now=at(DAY, 22, 0)), 1)
        self.assertEqual(services.mark_no_shows(now=at(DAY, 22, 0)), 0)

    def test_can_be_limited_to_one_restaurant_or_one_customer(self):
        mine = self.book()
        theirs = self.book(table=self.other_table, user=self.other_customer)
        services.mark_no_shows(restaurant=self.store, now=at(DAY, 22, 0))
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual(mine.status, Booking.Status.NO_SHOW)
        self.assertEqual(theirs.status, Booking.Status.CONFIRMED)
        services.mark_no_shows(user=self.other_customer, now=at(DAY, 22, 0))
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, Booking.Status.NO_SHOW)

    def test_management_command_marks_overdue_bookings(self):
        booking = self.book(day=DAY - timedelta(days=400))
        out = StringIO()
        call_command("mark_no_shows", stdout=out)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.NO_SHOW)
        self.assertIn("1 booking(s)", out.getvalue())


class MyQueuesHistoryTests(CompletionBase):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.upcoming = self.book(day=today + timedelta(days=2))
        self.completed = self.book(
            day=today - timedelta(days=5), status=Booking.Status.COMPLETED
        )
        self.no_show = self.book(
            day=today - timedelta(days=6), status=Booking.Status.NO_SHOW
        )
        self.cancelled = self.book(
            day=today + timedelta(days=4), status=Booking.Status.CANCELLED
        )
        self.theirs = self.book(
            day=today + timedelta(days=2), at_time=time(13, 0), user=self.other_customer
        )
        self.theirs_cancelled = self.book(
            day=today + timedelta(days=9), user=self.other_customer,
            status=Booking.Status.CANCELLED,
        )
        self.client.force_login(self.customer)

    def tab(self, name=None):
        params = {"tab": name} if name else {}
        return self.client.get(reverse("my_queues"), params)

    def ids(self, response):
        return [booking.id for booking in response.context["bookings"]]

    def test_default_tab_is_upcoming_with_confirmed_bookings_only(self):
        response = self.tab()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_tab"], "upcoming")
        self.assertEqual(self.ids(response), [self.upcoming.id])
        self.assertContains(response, "Confirmed")

    def test_past_tab_shows_completed_and_no_show(self):
        response = self.tab("past")
        self.assertEqual(self.ids(response), [self.completed.id, self.no_show.id])
        self.assertContains(response, "Completed")
        self.assertContains(response, "No Show")
        self.assertNotContains(response, "Cancel booking")

    def test_cancelled_tab_shows_cancelled_bookings(self):
        response = self.tab("cancelled")
        self.assertEqual(self.ids(response), [self.cancelled.id])
        self.assertContains(response, "Cancelled")

    def test_never_shows_another_customers_bookings(self):
        for name in ("upcoming", "past", "cancelled"):
            with self.subTest(tab=name):
                ids = self.ids(self.tab(name))
                self.assertNotIn(self.theirs.id, ids)
                self.assertNotIn(self.theirs_cancelled.id, ids)

    def test_tab_counts_are_shown(self):
        counts = {tab["key"]: tab["count"] for tab in self.tab().context["tabs"]}
        self.assertEqual(counts, {"upcoming": 1, "past": 2, "cancelled": 1})

    def test_unknown_tab_falls_back_to_upcoming(self):
        self.assertEqual(self.tab("nope").context["active_tab"], "upcoming")

    def test_cards_show_code_table_and_guests(self):
        response = self.tab()
        self.assertContains(response, self.upcoming.code)
        self.assertContains(response, "Table T1")
        self.assertContains(response, "2 guests")

    def test_cancel_link_only_on_upcoming(self):
        self.assertContains(self.tab(), reverse("cancel_booking", args=[self.upcoming.id]))
        self.assertNotContains(self.tab("cancelled"), "Cancel booking")

    def test_overdue_confirmed_booking_moves_to_past_as_no_show(self):
        overdue = self.book(day=timezone.localdate() - timedelta(days=2), at_time=time(11, 30))
        self.assertNotIn(overdue.id, self.ids(self.tab("upcoming")))
        self.assertIn(overdue.id, self.ids(self.tab("past")))
        overdue.refresh_from_db()
        self.assertEqual(overdue.status, Booking.Status.NO_SHOW)

    def test_empty_states_render(self):
        lonely = make_user("cp-lonely")
        self.client.force_login(lonely)
        texts = {
            "upcoming": "NOTHING ON THE CALENDAR",
            "past": "NO PAST VISITS YET",
            "cancelled": "NOTHING CANCELLED",
        }
        for name, text in texts.items():
            with self.subTest(tab=name):
                response = self.tab(name)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)

    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        self.assertEqual(self.tab().status_code, 302)

    def test_url_and_nav_label_are_unchanged(self):
        self.assertEqual(reverse("my_queues"), "/my-queues/")
        self.assertContains(self.tab(), "My Q")
