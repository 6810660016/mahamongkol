from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from dashboard import stats
from queues.models import QueueEntry
from restaurants.models import Restaurant, Review, Table

User = get_user_model()
PASSWORD = "Queue-pass-2026"


def make_user(name, **extra):
    return User.objects.create_user(name, f"{name}@example.com", PASSWORD, **extra)


class OwnerOverviewStatsTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.owner = make_user("ov-owner", role=User.Role.OWNER)
        self.store = Restaurant.objects.create(owner=self.owner, slug="ov-mine", name="Mine")
        self.table = Table.objects.create(restaurant=self.store, name="T1", capacity=8)
        other_owner = make_user("ov-other", role=User.Role.OWNER)
        self.other = Restaurant.objects.create(owner=other_owner, slug="ov-theirs", name="Theirs")
        self.other_table = Table.objects.create(restaurant=self.other, name="X1", capacity=4)
        self.alice = make_user("ov-alice")
        self.bob = make_user("ov-bob")

    def book(self, user, days_ago, slot, guests, status=Booking.Status.CONFIRMED, table=None):
        return Booking.objects.create(
            user=user, table=table or self.table, date=self.today - timedelta(days=days_ago),
            time=time.fromisoformat(slot), guests=guests, status=status,
        )

    def test_no_store_gives_empty_stats(self):
        result = stats.owner_overview_stats(None, 7)
        self.assertEqual(result["total_bookings"], 0)
        self.assertEqual(result["total_customers"], 0)
        self.assertIsNone(result["rating_average"])

    def test_booking_counts_cancel_rate_and_isolation(self):
        self.book(self.alice, 0, "19:00", 2)
        self.book(self.bob, 1, "19:00", 4)
        self.book(self.alice, 2, "13:00", 6, status=Booking.Status.CANCELLED)
        self.book(self.bob, 0, "19:00", 2, table=self.other_table)
        result = stats.owner_overview_stats(self.store, 7)
        self.assertEqual(result["total_bookings"], 3)
        self.assertEqual(result["cancel_rate"], 33)
        self.assertEqual(result["chart"]["total"], 2)
        popular = {s["label"]: s["count"] for s in result["popular"]}
        self.assertEqual(popular["19:00"], 2)
        self.assertEqual(popular["13:00"], 0)
        guests = {g["label"]: g["count"] for g in result["guests"]}
        self.assertEqual((guests["1–2"], guests["4"], guests["6+"]), (1, 1, 0))

    def test_range_switches_between_7_and_30_days(self):
        self.book(self.alice, 3, "19:00", 2)
        self.book(self.alice, 20, "19:00", 2)
        self.assertEqual(stats.owner_overview_stats(self.store, 7)["chart"]["total"], 1)
        self.assertEqual(stats.owner_overview_stats(self.store, 30)["chart"]["total"], 2)
        self.assertEqual(stats.parse_range("30"), 30)
        self.assertEqual(stats.parse_range("abc"), 7)
        self.assertEqual(stats.parse_range("99"), 7)

    def test_total_customers_combines_bookings_and_queue(self):
        self.book(self.alice, 0, "19:00", 2)
        self.book(self.alice, 1, "19:00", 2)
        QueueEntry.objects.create(restaurant=self.store, day=self.today, number=1, user=self.alice, party_size=2)
        QueueEntry.objects.create(restaurant=self.store, day=self.today, number=2, user=self.bob, party_size=2)
        QueueEntry.objects.create(restaurant=self.store, day=self.today, number=3, name="Walk-in", party_size=3)
        QueueEntry.objects.create(
            restaurant=self.store, day=self.today, number=4, name="Gone", party_size=1,
            status=QueueEntry.Status.CANCELLED,
        )
        self.assertEqual(stats.owner_overview_stats(self.store, 7)["total_customers"], 3)

    def test_rating_is_average_of_review_stars(self):
        Review.objects.create(restaurant=self.store, user=self.alice, rating=5)
        Review.objects.create(restaurant=self.store, user=self.bob, rating=4)
        Review.objects.create(restaurant=self.other, user=self.bob, rating=1)
        result = stats.owner_overview_stats(self.store, 7)
        self.assertEqual(result["rating_average"], "4.50")
        self.assertEqual(result["rating_count"], 2)

    def test_page_renders_real_numbers_without_views_card(self):
        self.book(self.alice, 0, "19:00", 2)
        Review.objects.create(restaurant=self.store, user=self.alice, rating=3)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("owner_overview"), {"range": "30"})
        self.assertContains(response, "Bookings over time")
        self.assertContains(response, "Average of 1 review")
        self.assertContains(response, "3.00")
        self.assertNotContains(response, "Views")
        self.assertNotContains(response, "Sample")
        self.assertEqual(response.context["stats"]["days"], 30)

    def test_owner_without_store_sees_page(self):
        lonely = make_user("ov-lonely", role=User.Role.OWNER)
        self.client.force_login(lonely)
        response = self.client.get(reverse("owner_overview"))
        self.assertContains(response, "No store yet")


class ReviewEndpointTests(TestCase):
    def setUp(self):
        self.customer = make_user("rv-customer")
        self.store = Restaurant.objects.create(slug="rv-store", name="Store")
        self.url = reverse("restaurant_review", args=[self.store.slug])
        self.client.force_login(self.customer)

    def test_post_creates_then_updates_single_review(self):
        self.assertEqual(self.client.post(self.url, {"rating": "4", "message": " Nice "}).status_code, 200)
        self.client.post(self.url, {"rating": "2"})
        review = Review.objects.get()
        self.assertEqual((review.rating, review.message), (2, ""))

    def test_invalid_rating_is_rejected(self):
        for value in ("", "0", "6", "x"):
            with self.subTest(value=value):
                self.assertEqual(self.client.post(self.url, {"rating": value}).status_code, 400)
        self.assertFalse(Review.objects.exists())

    def test_get_not_allowed_and_message_is_trimmed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.post(self.url, {"rating": "5", "message": "x" * 800})
        self.assertEqual(len(Review.objects.get().message), 500)

    def test_anonymous_cannot_review(self):
        self.client.logout()
        self.assertNotEqual(self.client.post(self.url, {"rating": "5"}).status_code, 200)
        self.assertFalse(Review.objects.exists())
