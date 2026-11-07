"""Ownership checks for the store edit / status / delete endpoints.

The store URLs use the public slug (e.g. /owner/stores/<slug>/delete/), so any
owner could try another owner's slug. These tests make sure only the store's
own owner can change it, and that the store is left untouched otherwise.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from account.models import OwnerApplication
from restaurants.models import Restaurant
from restaurants.services import can_manage

User = get_user_model()

PASSWORD = "Queue-pass-2026"

UPDATE_FORM = {
    "name": "Renamed Store", "category": "Restaurant", "price": "$$ · Mid-range",
    "address": "Changed address", "hours": "08:00-22:00",
}


def make_owner(username, status=OwnerApplication.Status.APPROVED):
    owner = User.objects.create_user(
        username, f"{username}@example.com", PASSWORD, role=User.Role.OWNER,
    )
    OwnerApplication.objects.create(
        user=owner, contact_name=username, business_name=f"{username} business",
        status=status,
    )
    return owner


class StoreOwnershipTests(TestCase):
    def setUp(self):
        self.owner_a = make_owner("owner-a")
        self.owner_b = make_owner("owner-b")
        self.store_a = Restaurant.objects.create(
            owner=self.owner_a, slug="store-a", name="Store A",
            address="Original address", status=Restaurant.Status.PUBLISHED, is_open=True,
        )
        self.store_b = Restaurant.objects.create(owner=self.owner_b, slug="store-b", name="Store B")
        # Seed-style store without an owner: no owner may manage it.
        self.unowned = Restaurant.objects.create(slug="no-owner", name="No Owner")

    def url(self, name, store):
        return reverse(name, args=[store.slug])

    def assert_store_unchanged(self, store, **expected):
        store.refresh_from_db()
        for field, value in expected.items():
            self.assertEqual(getattr(store, field), value, field)

    # --- another owner's store ---------------------------------------------

    def test_owner_cannot_update_another_owners_store(self):
        self.client.force_login(self.owner_b)
        response = self.client.post(self.url("owner_store_update", self.store_a), UPDATE_FORM)
        self.assertEqual(response.status_code, 404)
        self.assert_store_unchanged(self.store_a, name="Store A", address="Original address")

    def test_owner_cannot_change_status_of_another_owners_store(self):
        self.client.force_login(self.owner_b)
        response = self.client.post(
            self.url("owner_store_status", self.store_a), {"status": "draft", "is_open": "0"},
        )
        self.assertEqual(response.status_code, 404)
        self.assert_store_unchanged(
            self.store_a, status=Restaurant.Status.PUBLISHED, is_open=True,
        )

    def test_owner_cannot_delete_another_owners_store(self):
        self.client.force_login(self.owner_b)
        response = self.client.post(self.url("owner_store_delete", self.store_a))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Restaurant.objects.filter(pk=self.store_a.pk).exists())

    def test_owner_cannot_manage_a_store_without_an_owner(self):
        self.client.force_login(self.owner_a)
        for name, data in (
            ("owner_store_update", UPDATE_FORM),
            ("owner_store_status", {"status": "draft"}),
            ("owner_store_delete", {}),
        ):
            with self.subTest(endpoint=name):
                response = self.client.post(self.url(name, self.unowned), data)
                self.assertEqual(response.status_code, 404)
        self.assert_store_unchanged(
            self.unowned, name="No Owner", status=Restaurant.Status.PUBLISHED,
        )

    # --- own store ---------------------------------------------------------

    def test_owner_can_update_own_store(self):
        self.client.force_login(self.owner_a)
        response = self.client.post(self.url("owner_store_update", self.store_a), UPDATE_FORM)
        self.assertRedirects(response, reverse("owner_dashboard"))
        self.assert_store_unchanged(
            self.store_a, name="Renamed Store", address="Changed address", slug="store-a",
        )

    def test_owner_can_change_status_of_own_store(self):
        self.client.force_login(self.owner_a)
        response = self.client.post(
            self.url("owner_store_status", self.store_a), {"status": "draft", "is_open": "0"},
        )
        self.assertRedirects(response, reverse("owner_dashboard"))
        self.assert_store_unchanged(self.store_a, status=Restaurant.Status.DRAFT, is_open=False)

    def test_owner_can_delete_own_store(self):
        self.client.force_login(self.owner_a)
        response = self.client.post(self.url("owner_store_delete", self.store_a))
        self.assertRedirects(response, reverse("owner_dashboard"))
        self.assertFalse(Restaurant.objects.filter(pk=self.store_a.pk).exists())

    # --- not an approved owner ---------------------------------------------

    def test_anonymous_user_is_sent_to_login(self):
        for name in ("owner_store_update", "owner_store_status", "owner_store_delete"):
            with self.subTest(endpoint=name):
                response = self.client.post(self.url(name, self.store_a), UPDATE_FORM)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assert_store_unchanged(self.store_a, name="Store A")

    def test_customer_cannot_manage_stores(self):
        customer = User.objects.create_user("customer", "customer@example.com", PASSWORD)
        self.assert_blocked_from_store_a(customer)

    def test_pending_owner_cannot_manage_stores(self):
        self.assert_blocked_from_store_a(make_owner("pending", OwnerApplication.Status.PENDING))

    def test_rejected_owner_cannot_manage_stores(self):
        self.assert_blocked_from_store_a(make_owner("rejected", OwnerApplication.Status.REJECTED))

    def assert_blocked_from_store_a(self, user):
        self.client.force_login(user)
        for name, data in (
            ("owner_store_update", UPDATE_FORM),
            ("owner_store_status", {"status": "draft"}),
            ("owner_store_delete", {}),
        ):
            with self.subTest(endpoint=name):
                response = self.client.post(self.url(name, self.store_a), data)
                self.assertRedirects(
                    response, reverse("owner_application_status"), fetch_redirect_response=False,
                )
        self.assert_store_unchanged(
            self.store_a, name="Store A", status=Restaurant.Status.PUBLISHED,
        )

    # --- service-level rule ------------------------------------------------

    def test_can_manage_rule(self):
        admin = User.objects.create_user(
            "staff-admin", "staff-admin@example.com", PASSWORD, role=User.Role.ADMIN,
        )
        self.assertTrue(can_manage(self.owner_a, self.store_a))
        self.assertFalse(can_manage(self.owner_a, self.store_b))
        self.assertFalse(can_manage(self.owner_a, self.unowned))
        self.assertTrue(can_manage(admin, self.store_a))
        self.assertTrue(can_manage(admin, self.unowned))
