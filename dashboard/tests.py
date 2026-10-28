from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class OwnerPreviewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "preview-owner", "preview-owner@example.com", "Queue-pass-2026",
            role=User.Role.OWNER,
        )
        self.client.force_login(self.owner)

    def test_owner_preview_page_loads(self):
        response = self.client.get("/owner/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/owner_dashboard.html")
        self.assertContains(response, "Prototype workspace")
        self.assertContains(response, "Publish approval rules are still to be confirmed")
        self.assertContains(response, "Sign out")
        self.assertContains(response, "Switch to customer")

    def test_owner_preview_form_has_flexible_store_fields(self):
        response = self.client.get("/owner/")

        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'name="address"')
        self.assertContains(response, 'name="hours"')
        self.assertContains(response, 'name="price"')
        self.assertContains(response, 'name="description"')
        self.assertContains(response, 'name="image"')
        self.assertContains(response, "Add detail")

    def test_customer_is_redirected_away_from_owner_workspace(self):
        customer = User.objects.create_user(
            "preview-customer", "preview-customer@example.com", "Queue-pass-2026",
        )
        self.client.force_login(customer)

        response = self.client.get(reverse("owner_dashboard"), follow=True)
        self.assertRedirects(response, reverse("owner_signup"))

    def test_legacy_owner_can_also_use_customer_pages(self):
        for url in (reverse("home"), reverse("restaurants"), reverse("my_queues"), reverse("settings")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
                self.assertEqual(self.client.session['active_ui'], 'customer')
