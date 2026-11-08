"""Phase 5b: the Edit button on /owner/ goes to the Store Details page instead of opening the modal.

The data the page's JS builds the card from comes from `stores_data` (json_script), so the link
target is checked there. The modal stays for creating a store; the store_update endpoint stays too.
"""

from django.test import TestCase
from django.urls import reverse

from restaurants.models import Restaurant

from .store_test_utils import make_owner


class OwnerDashboardEditLinkTests(TestCase):
    def setUp(self):
        self.owner = make_owner("owner-link")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="baan-suan", name="Baan Suan", category="Café", address="1 Old Rd",
        )
        self.client.force_login(self.owner)

    def test_store_card_data_points_edit_to_store_details(self):
        response = self.client.get(reverse("owner_dashboard"))
        urls = response.context["stores_data"][0]["urls"]
        self.assertEqual(urls["details"], reverse("owner_store_details"))

    def test_store_card_data_no_longer_offers_a_modal_edit_url(self):
        response = self.client.get(reverse("owner_dashboard"))
        self.assertNotIn("edit", response.context["stores_data"][0]["urls"])

    def test_status_and_delete_urls_are_still_provided(self):
        urls = self.client.get(reverse("owner_dashboard")).context["stores_data"][0]["urls"]
        self.assertEqual(urls["status"], reverse("owner_store_status", args=[self.store.slug]))
        self.assertEqual(urls["delete"], reverse("owner_store_delete", args=[self.store.slug]))

    def test_dashboard_page_still_loads_without_a_store(self):
        self.store.delete()
        response = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stores_data"], [])

    def test_create_dialog_is_still_on_the_page(self):
        self.store.delete()
        self.assertContains(self.client.get(reverse("owner_dashboard")), "data-store-dialog")

    def test_store_update_endpoint_still_works(self):
        # kept on purpose: other tests and any old client still post here
        response = self.client.post(
            reverse("owner_store_update", args=[self.store.slug]),
            {"name": "Renamed", "category": "Café", "address": "1 Old Rd"},
        )
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Renamed")
