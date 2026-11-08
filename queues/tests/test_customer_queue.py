from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from bookings import services as booking_services
from bookings.models import Booking

from .. import services
from ..models import QueueEntry
from .test_queue_system import QueueTestBase, make_user

User = get_user_model()


class CustomerQueueTests(QueueTestBase):
    def setUp(self):
        super().setUp()
        self.guest = make_user("queue-guest")
        self.client.force_login(self.guest)

    def join(self, slug="salvia", party="2"):
        return self.client.post(reverse("queue_join", args=[slug]), {"party": party})

    def test_detail_page_has_a_join_button(self):
        page = self.client.get(reverse("restaurant_detail", args=["salvia"]))
        self.assertContains(page, reverse("queue_join", args=["salvia"]))
        self.assertContains(page, "Join the queue")

    def test_closed_restaurant_page_has_no_join_button(self):
        self.restaurant.is_open = False
        self.restaurant.save()
        page = self.client.get(reverse("restaurant_detail", args=["salvia"]))
        self.assertNotContains(page, reverse("queue_join", args=["salvia"]))

    def test_guest_joins_and_the_owner_sees_the_party(self):
        self.assertRedirects(self.join(party="3"), reverse("my_queues"))
        entry = QueueEntry.objects.get()
        self.assertEqual((entry.user, entry.party_size, entry.source), (self.guest, 3, "online"))
        self.assertEqual(entry.code, "Q001")
        snapshot = services.snapshot(self.restaurant)
        self.assertEqual(snapshot["waiting"][0]["source"], "Online")
        self.assertEqual(snapshot["waiting"][0]["name"], "queue-guest")

    def test_my_q_page_shows_the_live_section_and_message(self):
        page = self.client.get(reverse("my_queues"))
        self.assertContains(page, reverse("my_queue_data"))
        joined = self.client.post(reverse("queue_join", args=["salvia"]), {"party": "2"}, follow=True)
        self.assertContains(joined, "You&#x27;re in line at Salvia: Q001.")

    def test_live_data_shows_position_and_updates_as_the_line_moves(self):
        self.walk_in("Ahead 1")
        self.walk_in("Ahead 2")
        self.join()
        data = self.client.get(reverse("my_queue_data")).json()["queues"][0]
        self.assertEqual((data["code"], data["ahead"], data["nowServing"]), ("Q003", 2, None))
        services.call_next(self.restaurant)
        data = self.client.get(reverse("my_queue_data")).json()["queues"][0]
        self.assertEqual((data["ahead"], data["nowServing"]), (1, "Q001"))
        services.complete(self.restaurant)
        services.complete(self.restaurant)
        data = self.client.get(reverse("my_queue_data")).json()["queues"][0]
        self.assertEqual((data["status"], data["ahead"]), ("serving", None))

    def test_recalled_party_jumps_ahead_in_the_live_position(self):
        self.walk_in("First")
        skipped = self.walk_in("Second")
        self.join()
        services.call_next(self.restaurant)
        services.skip(self.restaurant)  # Q001 skipped, Q002 serving
        services.recall(self.restaurant, QueueEntry.objects.get(number=1).pk)
        data = self.client.get(reverse("my_queue_data")).json()["queues"][0]
        self.assertEqual(data["ahead"], 1)
        self.assertEqual(skipped.number, 2)

    def test_cannot_join_twice_while_active_but_can_after_finishing(self):
        self.join()
        self.join()
        self.assertEqual(QueueEntry.objects.count(), 1)
        services.call_next(self.restaurant)
        services.complete(self.restaurant)
        self.join()
        self.assertEqual(QueueEntry.objects.count(), 2)

    def test_database_blocks_a_second_active_entry_for_the_same_guest(self):
        services.join_queue(self.guest, self.restaurant, 2)
        with self.assertRaises(services.QueueError):
            services.join_queue(self.guest, self.restaurant, 2)

    def test_guest_can_join_two_different_restaurants(self):
        self.join()
        self.join("garden-table")
        self.assertEqual(len(self.client.get(reverse("my_queue_data")).json()["queues"]), 2)

    def test_refused_when_paused_closed_or_bad_party_size(self):
        services.set_paused(self.restaurant, True)
        self.join()
        services.set_paused(self.restaurant, False)
        self.restaurant.is_open = False
        self.restaurant.save()
        self.join()
        self.restaurant.is_open = True
        self.restaurant.save()
        self.join(party="0")
        self.join(party="abc")
        self.assertEqual(QueueEntry.objects.count(), 0)

    def test_draft_restaurant_cannot_be_joined(self):
        self.restaurant.status = "draft"
        self.restaurant.save()
        self.assertEqual(self.join().status_code, 404)

    def test_guest_can_leave_while_waiting_and_the_line_closes_up(self):
        self.join()
        entry = QueueEntry.objects.get()
        later = self.walk_in("Later")
        response = self.client.post(reverse("queue_leave", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["queues"], [])
        entry.refresh_from_db()
        self.assertEqual(entry.status, QueueEntry.Status.CANCELLED)
        self.assertEqual(services.call_next(self.restaurant), later)
        self.join()  # may take a fresh number afterwards
        self.assertEqual(QueueEntry.objects.filter(user=self.guest, status="waiting").count(), 1)

    def test_cannot_leave_while_being_served_or_someone_elses_entry(self):
        self.join()
        entry = QueueEntry.objects.get()
        services.call_next(self.restaurant)
        self.assertEqual(self.client.post(reverse("queue_leave", args=[entry.pk])).status_code, 409)
        entry.refresh_from_db()
        self.assertEqual(entry.status, QueueEntry.Status.SERVING)
        stranger = make_user("stranger")
        self.client.force_login(stranger)
        self.assertEqual(self.client.post(reverse("queue_leave", args=[entry.pk])).status_code, 409)
        self.assertEqual(self.client.get(reverse("my_queue_data")).json()["queues"], [])

    def test_customer_endpoints_need_login_post_and_csrf(self):
        self.assertEqual(self.client.get(reverse("queue_join", args=["salvia"])).status_code, 405)
        self.assertEqual(self.client.get(reverse("queue_leave", args=[1])).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.guest)
        self.assertEqual(strict.post(reverse("queue_join", args=["salvia"]), {"party": "2"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("my_queue_data")).status_code, 302)
        self.assertEqual(self.join().status_code, 302)
        self.assertEqual(QueueEntry.objects.count(), 0)



class ServiceModeTests(QueueTestBase):
    def setUp(self):
        super().setUp()
        self.guest = make_user("mode-guest")

    def set_mode(self, mode):
        self.restaurant.service_mode = mode
        self.restaurant.save()

    def test_default_mode_offers_both(self):
        self.assertEqual(self.restaurant.service_mode, "both")
        self.assertTrue(self.restaurant.accepts_bookings and self.restaurant.accepts_queue)
        self.client.force_login(self.guest)
        page = self.client.get(reverse("restaurant_detail", args=["salvia"]))
        self.assertContains(page, reverse("booking", args=["salvia"]))
        self.assertContains(page, reverse("queue_join", args=["salvia"]))

    def test_queue_only_hides_booking_and_blocks_it(self):
        self.set_mode("queue")
        self.client.force_login(self.guest)
        page = self.client.get(reverse("restaurant_detail", args=["salvia"]))
        self.assertNotContains(page, reverse("booking", args=["salvia"]))
        self.assertContains(page, reverse("queue_join", args=["salvia"]))
        self.assertRedirects(
            self.client.get(reverse("booking", args=["salvia"])),
            reverse("restaurant_detail", args=["salvia"]),
        )
        with self.assertRaises(booking_services.BookingError):
            booking_services.create_booking(
                self.guest, self.restaurant, services.service_day(), "19:00", 2
            )
        self.assertEqual(Booking.objects.count(), 0)
        self.client.post(reverse("queue_join", args=["salvia"]), {"party": "2"})
        self.assertEqual(QueueEntry.objects.count(), 1)

    def test_booking_only_hides_queue_and_blocks_it(self):
        # Freeze the clock at midday so the 19:00 slot is always still in the future.
        noon = datetime(2026, 11, 8, 12, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
        patcher = mock.patch("django.utils.timezone.now", return_value=noon)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.set_mode("booking")
        self.client.force_login(self.guest)
        page = self.client.get(reverse("restaurant_detail", args=["salvia"]))
        self.assertContains(page, reverse("booking", args=["salvia"]))
        self.assertNotContains(page, reverse("queue_join", args=["salvia"]))
        self.client.post(reverse("queue_join", args=["salvia"]), {"party": "2"})
        self.assertEqual(QueueEntry.objects.count(), 0)
        with self.assertRaises(services.QueueError):
            services.join_queue(self.guest, self.restaurant, 2)
        with self.assertRaises(services.QueueError):
            self.walk_in()
        self.assertEqual(booking_services.create_booking(
            self.guest, self.restaurant, services.service_day(), "19:00", 2
        ).status, Booking.Status.CONFIRMED)

    def test_owner_queue_page_explains_when_the_queue_is_off(self):
        self.set_mode("booking")
        self.client.force_login(self.owner)
        page = self.client.get(reverse("owner_queue"))
        self.assertContains(page, "Queue is turned off")
        self.assertContains(page, 'data-queue-enabled="0"')
        data = self.client.get(reverse("owner_queue_data")).json()
        self.assertFalse(data["queueEnabled"])
        self.assertEqual(self.client.post(reverse("owner_queue_add"), {"party": "2"}).status_code, 409)
        self.set_mode("both")
        self.assertNotContains(self.client.get(reverse("owner_queue")), "Queue is turned off")

    def test_owner_add_dialog_is_walk_in_only(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse("owner_queue"))
        self.assertNotContains(page, "Booking (check in)")
        self.assertNotContains(page, "Queue source")
        self.assertNotContains(page, "Add booking or walk-in")
        self.assertEqual(page.content.decode().count("data-open-add"), 1)
        self.assertNotIn("bookingsToCheckIn", self.client.get(reverse("owner_queue_data")).json())

    def test_owner_can_choose_the_mode_from_the_store_form(self):
        self.client.force_login(self.owner)
        data = {
            "name": "Salvia", "category": "Restaurant", "price": "", "address": "1 Road",
            "hours": "", "image": "", "description": "", "service_mode": "queue",
        }
        self.client.post(reverse("owner_store_update", args=["salvia"]), data)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.service_mode, "queue")
        # Leaving the field out keeps the current mode; junk values are rejected.
        del data["service_mode"]
        self.client.post(reverse("owner_store_update", args=["salvia"]), data)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.service_mode, "queue")
        self.client.post(reverse("owner_store_update", args=["salvia"]), {**data, "service_mode": "nonsense"})
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.service_mode, "queue")
        page = self.client.get(reverse("owner_dashboard"))
        self.assertContains(page, '"serviceMode": "queue"')
