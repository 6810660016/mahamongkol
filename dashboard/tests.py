from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from restaurants.models import Restaurant

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

    def test_queue_page_is_available_to_owner(self):
        response = self.client.get(reverse("owner_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "not connected to real bookings")
        self.assertContains(response, reverse("owner_queue_data"))
        self.assertContains(response, "Skipped queues")

    def test_new_owner_mockup_pages_are_available_and_marked_as_sample(self):
        for name, text in (("owner_overview", "Sample dashboard"), ("owner_store_details", "not saved yet")):
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


class OneStorePerOwnerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "one-store-owner", "one-store@example.com", "Queue-pass-2026",
            role=User.Role.OWNER,
        )
        self.client.force_login(self.owner)
        self.store_form = {
            "name": "Only Store", "category": "Restaurant", "price": "$$ · Mid-range",
            "address": "Bangkok", "hours": "10:00-20:00", "table_count": "2",
            "seats_per_table": "4",
        }

    def create_store(self, **overrides):
        return self.client.post(reverse("owner_store_create"), {**self.store_form, **overrides})

    def test_first_store_can_be_created(self):
        self.create_store()
        self.assertEqual(Restaurant.objects.filter(owner=self.owner).count(), 1)
        self.assertEqual(self.owner.restaurant.name, "Only Store")

    def test_second_store_is_refused_with_a_clear_message(self):
        self.create_store()
        response = self.client.post(
            reverse("owner_store_create"), {**self.store_form, "name": "Second Store"}, follow=True
        )
        self.assertEqual(Restaurant.objects.filter(owner=self.owner).count(), 1)
        self.assertFalse(Restaurant.objects.filter(name="Second Store").exists())
        self.assertContains(response, "สร้างร้านเพิ่มไม่ได้")

    def test_database_rejects_a_second_store_for_the_same_owner(self):
        Restaurant.objects.create(owner=self.owner, slug="first", name="First")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Restaurant.objects.create(owner=self.owner, slug="second", name="Second")

    def test_stores_without_an_owner_are_not_limited(self):
        Restaurant.objects.create(slug="orphan-1", name="Orphan 1")
        Restaurant.objects.create(slug="orphan-2", name="Orphan 2")
        self.assertEqual(Restaurant.objects.filter(owner__isnull=True, slug__startswith="orphan").count(), 2)

    def test_different_owners_can_each_have_a_store(self):
        other = User.objects.create_user(
            "other-owner", "other-owner@example.com", "Queue-pass-2026",
            role=User.Role.OWNER,
        )
        self.create_store()
        self.client.force_login(other)
        self.create_store(name="Other Store")
        self.assertEqual(Restaurant.objects.filter(owner__isnull=False, name__in=["Only Store", "Other Store"]).count(), 2)

    def test_add_a_store_is_hidden_once_the_owner_has_a_store(self):
        self.create_store()
        for name in ("owner_dashboard", "owner_overview", "owner_bookings", "owner_queue"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertNotContains(response, "data-open-store")
                self.assertNotContains(response, "add_store=1")
                if name != "owner_dashboard":  # หน้า dashboard ยังมี dialog ที่ใช้แก้ร้านด้วย
                    self.assertNotContains(response, "Add a store")
