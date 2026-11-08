"""หน้ารีวิวต้องแสดง Display name ที่ตั้งไว้ในหน้า Settings (ไม่ใช่ username ของบัญชี)"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from restaurants.models import Restaurant

User = get_user_model()
PASSWORD = "Review-name-2026"


class ReviewDisplayNameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("old-username", "old@example.com", PASSWORD)
        self.store = Restaurant.objects.create(slug="name-store", name="Name Store")
        self.client.force_login(self.user)
        self.detail_url = reverse("restaurant_detail", args=[self.store.slug])

    def rename_in_settings(self, name):
        response = self.client.post(reverse("settings"), {"name": name})
        self.assertEqual(response.status_code, 200)

    def test_review_page_shows_the_display_name_saved_in_settings(self):
        self.rename_in_settings("Somchai")
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Signed in as Somchai")
        self.assertNotContains(response, "Signed in as old-username")
        self.assertNotContains(response, "<strong>old-username</strong>")

    def test_the_change_shows_on_the_next_visit_not_only_after_relogin(self):
        self.assertContains(self.client.get(self.detail_url), "Signed in as old-username")
        self.rename_in_settings("Somchai")
        self.assertContains(self.client.get(self.detail_url), "Signed in as Somchai")

    def test_falls_back_to_username_when_no_display_name_is_set(self):
        self.rename_in_settings("Somchai")
        self.rename_in_settings("")
        self.assertContains(self.client.get(self.detail_url), "Signed in as old-username")

    def test_display_name_is_escaped(self):
        self.rename_in_settings("<b>x</b>")
        response = self.client.get(self.detail_url)
        self.assertNotContains(response, "Signed in as <b>x</b>")
        self.assertContains(response, "Signed in as &lt;b&gt;x&lt;/b&gt;")
