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
        self.assertContains(response, "My stores")
        self.assertContains(response, 'id="stores-data"')
        self.assertNotContains(response, "Prototype workspace")
        self.assertContains(response, "Sign out")
        self.assertContains(response, "Switch to customer")
        self.assertContains(response, reverse("owner_queue"))

    def test_queue_mockup_is_available_to_owner(self):
        response = self.client.get(reverse("owner_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not connected to real bookings or walk-ins")
        self.assertContains(response, "Skipped queues")

    def test_new_owner_mockup_pages_are_available_and_marked_as_sample(self):
        for name, text in (("owner_overview", "Sample dashboard"), ("owner_store_details", "Store details mockup"), ("owner_bookings", "Booking preview")):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)
                self.assertContains(response, reverse("owner_queue"))

    def test_all_owner_pages_render_the_shared_navigation(self):
        for name in ("owner_dashboard", "owner_overview", "owner_store_details", "owner_bookings", "owner_queue"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, "dashboard/css/owner_navigation.css")
                self.assertContains(response, 'aria-label="Owner workspace navigation"')
                self.assertContains(response, "Service Home")
                self.assertContains(response, "My stores")
                self.assertContains(response, "Store details")
                self.assertContains(response, "Booking management")
                self.assertContains(response, "Queue management")
                self.assertContains(response, "Add a store")
                self.assertContains(response, "Switch to customer")
                self.assertContains(response, "Sign out")
                self.assertContains(response, 'class="owner-topbar"')

    def test_new_owner_pages_are_not_available_to_customer(self):
        customer = User.objects.create_user("pages-customer", "pages@example.com", "Queue-pass-2026")
        self.client.force_login(customer)
        for name in ("owner_overview", "owner_store_details", "owner_bookings"):
            with self.subTest(page=name):
                self.assertRedirects(self.client.get(reverse(name), follow=True), reverse("owner_signup"))

    def test_queue_mockup_is_not_available_to_unapproved_customer(self):
        customer = User.objects.create_user(
            "queue-customer", "queue-customer@example.com", "Queue-pass-2026",
        )
        self.client.force_login(customer)
        response = self.client.get(reverse("owner_queue"), follow=True)
        self.assertRedirects(response, reverse("owner_signup"))

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
