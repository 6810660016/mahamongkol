from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from restaurants.models import Restaurant

from .. import services
from ..models import QueueEntry

User = get_user_model()
PASSWORD = "Queue-pass-2026"


def make_user(username, role=User.Role.USER, **extra):
    return User.objects.create_user(username, f"{username}@example.com", PASSWORD, role=role, **extra)


class QueueTestBase(TestCase):
    def setUp(self):
        self.owner = make_user("queue-owner", User.Role.OWNER)
        self.restaurant = Restaurant.objects.get(slug="salvia")
        self.restaurant.owner = self.owner
        self.restaurant.save()
        self.other_owner = make_user("other-queue-owner", User.Role.OWNER)
        self.other = Restaurant.objects.get(slug="garden-table")
        self.other.owner = self.other_owner
        self.other.save()

    def walk_in(self, name="", size=2, restaurant=None):
        return services.add_entry(restaurant or self.restaurant, name=name, party_size=size)


class ServiceTests(QueueTestBase):
    def test_numbers_count_up_per_restaurant(self):
        a, b = self.walk_in("A"), self.walk_in("B")
        other = self.walk_in("C", restaurant=self.other)
        self.assertEqual((a.number, b.number, other.number), (1, 2, 1))
        self.assertEqual(a.code, "Q001")
        self.assertEqual(a.source, QueueEntry.Source.WALK_IN)
        self.assertEqual(a.status, QueueEntry.Status.WAITING)

    def test_party_size_is_validated(self):
        for bad in (0, 21, "x", None):
            with self.subTest(bad=bad), self.assertRaises(services.QueueError):
                self.walk_in(size=bad)
        self.assertEqual(QueueEntry.objects.count(), 0)

    def test_call_next_serves_the_oldest_waiting_party(self):
        first, second = self.walk_in("A"), self.walk_in("B")
        self.assertEqual(services.call_next(self.restaurant), first)
        first.refresh_from_db()
        self.assertEqual(first.status, QueueEntry.Status.SERVING)
        self.assertEqual(first.call_count, 1)
        self.assertEqual(second.status, QueueEntry.Status.WAITING)

    def test_cannot_call_next_while_serving_or_when_empty(self):
        with self.assertRaises(services.QueueError):
            services.call_next(self.restaurant)
        self.walk_in()
        self.walk_in()
        services.call_next(self.restaurant)
        with self.assertRaises(services.QueueError):
            services.call_next(self.restaurant)

    def test_call_again_counts_calls(self):
        entry = self.walk_in()
        with self.assertRaises(services.QueueError):
            services.call_again(self.restaurant)
        services.call_next(self.restaurant)
        services.call_again(self.restaurant)
        entry.refresh_from_db()
        self.assertEqual(entry.call_count, 2)

    def test_complete_finishes_and_calls_the_next_party(self):
        a, b = self.walk_in("A"), self.walk_in("B")
        services.call_next(self.restaurant)
        finished, following = services.complete(self.restaurant)
        a.refresh_from_db()
        self.assertEqual(finished, a)
        self.assertEqual(a.status, QueueEntry.Status.COMPLETED)
        self.assertIsNotNone(a.finished_at)
        self.assertEqual(following, b)
        self.assertEqual(services.snapshot(self.restaurant)["current"]["code"], "Q002")
        self.assertEqual(services.complete(self.restaurant)[1], None)
        self.assertIsNone(services.snapshot(self.restaurant)["current"])

    def test_skip_then_recall_goes_to_the_front(self):
        a, _, c = self.walk_in("A"), self.walk_in("B"), self.walk_in("C")
        services.call_next(self.restaurant)
        services.skip(self.restaurant)  # A skipped, B serving
        a.refresh_from_db()
        self.assertEqual(a.status, QueueEntry.Status.SKIPPED)
        recalled = services.recall(self.restaurant, a.pk)
        self.assertTrue(recalled.is_priority)
        self.assertEqual(recalled.status, QueueEntry.Status.WAITING)
        waiting = [e["code"] for e in services.snapshot(self.restaurant)["waiting"]]
        self.assertEqual(waiting, ["Q001", "Q003"])
        self.assertEqual(services.complete(self.restaurant)[1], a)
        self.assertEqual(c.status, QueueEntry.Status.WAITING)

    def test_recall_serves_immediately_when_nobody_is_being_served(self):
        a = self.walk_in("A")
        services.call_next(self.restaurant)
        services.skip(self.restaurant)
        self.assertEqual(services.recall(self.restaurant, a.pk).status, QueueEntry.Status.SERVING)

    def test_recall_only_works_for_skipped_entries_of_this_store(self):
        a = self.walk_in("A")
        with self.assertRaises(services.QueueError):
            services.recall(self.restaurant, a.pk)
        services.call_next(self.restaurant)
        services.skip(self.restaurant)
        with self.assertRaises(services.QueueError):
            services.recall(self.other, a.pk)

    def test_pause_blocks_new_entries_only(self):
        self.walk_in()
        services.set_paused(self.restaurant, True)
        with self.assertRaises(services.QueueError):
            self.walk_in()
        self.assertEqual(services.call_next(self.restaurant).number, 1)
        services.set_paused(self.restaurant, False)
        self.assertEqual(self.walk_in().number, 2)

    def test_database_allows_only_one_serving_entry(self):
        a, b = self.walk_in(), self.walk_in()
        QueueEntry.objects.filter(pk=a.pk).update(status="serving")
        with self.assertRaises(IntegrityError), transaction.atomic():
            QueueEntry.objects.filter(pk=b.pk).update(status="serving")

    def test_yesterdays_line_does_not_show_today(self):
        old = self.walk_in()
        QueueEntry.objects.filter(pk=old.pk).update(day=services.service_day() - timedelta(days=1))
        self.assertEqual(services.snapshot(self.restaurant)["waiting"], [])
        self.assertEqual(self.walk_in().number, 1)


class QueueApiTests(QueueTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def post(self, name, data=None, args=None, client=None):
        return (client or self.client).post(reverse(name, args=args or []), data or {})

    def test_page_and_data_are_scoped_to_the_signed_in_owner(self):
        self.walk_in("Mine")
        self.walk_in("Theirs", restaurant=self.other)
        data = self.client.get(reverse("owner_queue_data")).json()
        self.assertEqual([e["name"] for e in data["waiting"]], ["Mine"])
        self.client.force_login(self.other_owner)
        data = self.client.get(reverse("owner_queue_data")).json()
        self.assertEqual([e["name"] for e in data["waiting"]], ["Theirs"])

    def test_walk_in_can_be_added_from_the_page(self):
        response = self.post("owner_queue_add", {"source": "walkin", "name": " Somchai ", "party": "4"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["message"], "Q001 added to the queue.")
        self.assertEqual(body["waiting"][0]["name"], "Somchai")
        self.assertEqual(body["waiting"][0]["party"], 4)
        self.assertEqual(body["waiting"][0]["source"], "Walk-in")

    def test_full_flow_over_http(self):
        for name in ("A", "B"):
            self.post("owner_queue_add", {"name": name, "party": "2"})
        self.assertEqual(self.post("owner_queue_call_next").json()["current"]["code"], "Q001")
        self.assertIn("Calling Q001", self.post("owner_queue_call_again").json()["message"])
        done = self.post("owner_queue_complete").json()
        self.assertEqual(done["message"], "Q001 completed. Q002 is now being served.")
        self.assertEqual(done["completed"], 1)
        skipped = self.post("owner_queue_skip").json()
        self.assertEqual(skipped["message"], "Q002 skipped. No queues are waiting.")
        entry_id = skipped["skipped"][0]["id"]
        recalled = self.post("owner_queue_recall", args=[entry_id]).json()
        self.assertEqual(recalled["current"]["code"], "Q002")

    def test_errors_are_409_with_a_message_and_the_current_state(self):
        response = self.post("owner_queue_call_next")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "No queues are waiting.")
        self.assertIn("waiting", response.json())
        self.assertEqual(self.post("owner_queue_add", {"party": "99"}).status_code, 409)

    def test_pause_over_http(self):
        self.post("owner_queue_pause", {"paused": "1"})
        self.assertTrue(self.client.get(reverse("owner_queue_data")).json()["paused"])
        self.assertEqual(self.post("owner_queue_add", {"party": "2"}).status_code, 409)
        self.post("owner_queue_pause", {"paused": "0"})
        self.assertEqual(self.post("owner_queue_add", {"party": "2"}).status_code, 200)

    def test_actions_are_post_only_and_need_csrf(self):
        self.assertEqual(self.client.get(reverse("owner_queue_add")).status_code, 405)
        self.assertEqual(self.client.post(reverse("owner_queue_data")).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(reverse("owner_queue_add"), {"party": "2"}).status_code, 403)
        self.assertEqual(QueueEntry.objects.count(), 0)

    def test_customers_anonymous_users_and_storeless_owners_are_kept_out(self):
        customer = make_user("plain-customer")
        self.client.force_login(customer)
        for name in ("owner_queue_data", "owner_queue_add", "owner_queue_call_next"):
            with self.subTest(name=name):
                response = (
                    self.client.get(reverse(name)) if name == "owner_queue_data" else self.post(name)
                )
                self.assertEqual(response.status_code, 302)
                self.assertRedirects(response, reverse("owner_application_status"), fetch_redirect_response=False)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("owner_queue_data")).status_code, 302)

        storeless = make_user("storeless-owner", User.Role.OWNER)
        self.client.force_login(storeless)
        self.assertEqual(self.client.get(reverse("owner_queue_data")).status_code, 404)
        self.assertEqual(self.post("owner_queue_add", {"party": "2"}).status_code, 404)

    def test_owner_cannot_recall_another_stores_entry(self):
        entry = self.walk_in("Theirs", restaurant=self.other)
        services.call_next(self.other)
        services.skip(self.other)
        response = self.post("owner_queue_recall", args=[entry.pk])
        self.assertEqual(response.status_code, 409)
        entry.refresh_from_db()
        self.assertEqual(entry.status, QueueEntry.Status.SKIPPED)

    def test_queue_page_renders_for_owner_with_and_without_a_store(self):
        page = self.client.get(reverse("owner_queue"))
        self.assertContains(page, reverse("owner_queue_add"))
        self.assertNotContains(page, "No store yet")
        self.client.force_login(make_user("page-storeless", User.Role.OWNER))
        self.assertContains(self.client.get(reverse("owner_queue")), "No store yet")
