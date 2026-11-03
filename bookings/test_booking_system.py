from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from restaurants.models import Restaurant

from . import services
from .models import Booking

User = get_user_model()

TOMORROW = date.today() + timedelta(days=1)


def make_user(username, role=User.Role.USER, **extra):
    return User.objects.create_user(
        username, f"{username}@example.com", "Queue-pass-2026", role=role, **extra
    )


def book(client, slug="salvia", guests="2", slot="19:00", day=TOMORROW):
    return client.post(
        reverse("booking", args=[slug]),
        {"date": day.isoformat(), "time": slot, "guests": guests},
    )


class SeedDataTests(TestCase):
    def test_existing_restaurants_are_seeded_with_tables(self):
        self.assertEqual(
            list(Restaurant.objects.values_list("slug", flat=True)),
            ["salvia", "garden-table", "mellow-coffee"],
        )
        for restaurant in Restaurant.objects.all():
            self.assertTrue(restaurant.tables.exists())


class CreateAndCancelTests(TestCase):
    def setUp(self):
        self.customer = make_user("customer")
        self.other = make_user("other-customer")
        self.client.force_login(self.customer)

    def test_booking_is_saved_in_the_database(self):
        self.assertRedirects(book(self.client), reverse("my_queues"))
        booking = Booking.objects.get()
        self.assertEqual(booking.user, self.customer)
        self.assertEqual(booking.restaurant.slug, "salvia")
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertGreaterEqual(booking.table.capacity, 2)

    def test_booking_is_visible_to_the_same_user_in_a_new_session(self):
        book(self.client)
        self.client.logout()
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse("my_queues")), "Salvia")

    def test_smallest_fitting_table_is_used(self):
        book(self.client, guests="3")
        self.assertEqual(Booking.objects.get().table.capacity, 4)

    def test_invalid_input_is_rejected(self):
        for payload in (
            {"date": "not-a-date", "time": "19:00", "guests": "2"},
            {"date": (date.today() - timedelta(days=1)).isoformat(), "time": "19:00", "guests": "2"},
            {"date": TOMORROW.isoformat(), "time": "03:00", "guests": "2"},
            {"date": TOMORROW.isoformat(), "time": "19:00", "guests": "0"},
            {"date": TOMORROW.isoformat(), "time": "19:00", "guests": "13"},
            {"date": TOMORROW.isoformat(), "time": "19:00", "guests": "x"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(reverse("booking", args=["salvia"]), payload)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Please choose a valid date")
        self.assertEqual(Booking.objects.count(), 0)

    def test_same_table_cannot_be_booked_twice_for_one_slot(self):
        book(self.client, guests="12")
        response = book(self.client, guests="12")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no table is free")
        self.assertEqual(Booking.objects.filter(status="confirmed").count(), 1)

    def test_database_constraint_blocks_a_duplicate_confirmed_booking(self):
        book(self.client)
        first = Booking.objects.get()
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(
                user=self.other, table=first.table, date=first.date,
                time=first.time, guests=2,
            )

    def test_different_slot_or_restaurant_is_not_blocked(self):
        book(self.client, guests="12")
        book(self.client, guests="12", slot="20:30")
        book(self.client, slug="garden-table", guests="12")
        self.assertEqual(Booking.objects.count(), 3)

    def test_cancelled_table_can_be_booked_again(self):
        book(self.client, guests="12")
        booking = Booking.objects.get()
        self.client.post(reverse("cancel_booking", args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertIsNotNone(booking.cancelled_at)
        self.assertRedirects(book(self.client, guests="12"), reverse("my_queues"))
        self.assertEqual(Booking.objects.count(), 2)

    def test_cancelled_booking_leaves_my_queue(self):
        book(self.client)
        booking = Booking.objects.get()
        self.client.post(reverse("cancel_booking", args=[booking.id]))
        self.assertContains(
            self.client.get(reverse("my_queues")), "Your next favourite moment"
        )

    def test_customer_cannot_cancel_someone_elses_booking(self):
        book(self.client)
        booking = Booking.objects.get()
        self.client.force_login(self.other)
        response = self.client.post(reverse("cancel_booking", args=[booking.id]))
        self.assertRedirects(response, reverse("my_queues"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_my_queue_only_lists_own_bookings(self):
        book(self.client)
        self.client.force_login(self.other)
        self.assertContains(
            self.client.get(reverse("my_queues")), "Your next favourite moment"
        )

    def test_booking_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("booking", args=["salvia"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_unknown_restaurant_is_404(self):
        self.assertEqual(
            self.client.get(reverse("booking", args=["nope"])).status_code, 404
        )

    def test_services_validate_without_the_web_layer(self):
        salvia = Restaurant.objects.get(slug="salvia")
        with self.assertRaises(services.BookingError):
            services.create_booking(self.customer, salvia, TOMORROW, "03:00", 2)


class ManagementTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner", role=User.Role.OWNER)
        self.rival_owner = make_user("rival", role=User.Role.OWNER)
        self.admin = make_user("staff", role=User.Role.ADMIN)
        self.customer = make_user("customer")
        self.salvia = Restaurant.objects.get(slug="salvia")
        self.salvia.owner = self.owner
        self.salvia.save()
        garden = Restaurant.objects.get(slug="garden-table")
        garden.owner = self.rival_owner
        garden.save()

        self.client.force_login(self.customer)
        book(self.client, guests="12")
        self.booking = Booking.objects.get()
        self.url = reverse("manage_bookings", args=["salvia"])
        self.query = {"date": TOMORROW.isoformat(), "time": "19:00"}

    def test_booked_table_is_shown_as_booked(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url, self.query)
        self.assertEqual(response.status_code, 200)
        rows = {row["table"].name: row for row in response.context["rows"]}
        booked_name = self.booking.table.name
        self.assertEqual(rows[booked_name]["status"], "Booked")
        self.assertEqual(rows[booked_name]["booking"], self.booking)
        others = [r for name, r in rows.items() if name != booked_name]
        self.assertTrue(all(r["status"] == "Available" for r in others))
        self.assertContains(response, "Booked")
        self.assertContains(response, "customer")

    def test_other_slot_shows_everything_available(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url, {**self.query, "time": "13:00"})
        self.assertTrue(all(r["status"] == "Available" for r in response.context["rows"]))

    def test_table_becomes_available_after_cancellation(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("manage_cancel", args=[self.booking.id]))
        self.assertRedirects(response, f"{self.url}?date={TOMORROW.isoformat()}&time=19%3A00")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        response = self.client.get(self.url, self.query)
        self.assertTrue(all(r["status"] == "Available" for r in response.context["rows"]))

    def test_admin_can_manage_any_restaurant_and_cancel(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url, self.query).status_code, 200)
        self.client.post(reverse("manage_cancel", args=[self.booking.id]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)

    def test_superuser_can_manage(self):
        superuser = User.objects.create_superuser("root", "root@example.com", "Queue-pass-2026")
        self.client.force_login(superuser)
        self.assertEqual(self.client.get(self.url, self.query).status_code, 200)

    def test_owner_only_sees_own_restaurants(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manage_restaurants"))
        self.assertContains(response, "Salvia")
        self.assertNotContains(response, "The Garden Table")

    def test_admin_sees_all_restaurants(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_restaurants"))
        for name in ("Salvia", "The Garden Table", "Mellow Coffee"):
            self.assertContains(response, name)

    def test_owner_cannot_open_another_restaurant(self):
        self.client.force_login(self.rival_owner)
        self.assertEqual(self.client.get(self.url, self.query).status_code, 404)

    def test_owner_cannot_cancel_another_restaurants_booking(self):
        self.client.force_login(self.rival_owner)
        response = self.client.post(reverse("manage_cancel", args=[self.booking.id]))
        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_plain_customer_is_forbidden(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("manage_restaurants")).status_code, 403)
        self.assertEqual(self.client.get(self.url, self.query).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("manage_cancel", args=[self.booking.id])).status_code, 403
        )

    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_cancel_endpoint_rejects_get(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manage_cancel", args=[self.booking.id]))
        self.assertEqual(response.status_code, 405)

    def test_owner_waiting_for_approval_cannot_manage(self):
        from account.models import OwnerApplication

        pending = make_user("pending", role=User.Role.OWNER)
        OwnerApplication.objects.create(
            user=pending, contact_name="P", business_name="Pending Bistro"
        )
        self.client.force_login(pending)
        response = self.client.get(reverse("manage_restaurants"))
        self.assertRedirects(
            response, reverse("owner_application_status"), fetch_redirect_response=False
        )

    def test_bad_filter_values_fall_back_to_defaults(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url, {"date": "oops", "time": "99:99"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["slot"], services.SLOTS[0])
