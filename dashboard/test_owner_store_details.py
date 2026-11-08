"""The Store Details page: real store data, profile photo saved on Save, CSRF."""

import re
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from restaurants.models import Restaurant

from .store_test_utils import (
    NEW_URL,
    OLD_URL,
    UPLOAD_PATH,
    image_file,
    make_owner,
    valid_data,
)


class OwnerStoreDetailsPageTests(TestCase):
    def setUp(self):
        self.owner = make_owner("owner-a")
        self.url = reverse("owner_store_details")

    def test_page_shows_real_store_data_not_mockup_samples(self):
        Restaurant.objects.create(
            owner=self.owner, slug="baan-suan", name="Baan Suan", image=OLD_URL,
            description="Garden cafe", hours="Daily 9-18",
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Baan Suan")
        self.assertContains(response, "Garden cafe")
        self.assertContains(response, "Daily 9-18")
        self.assertContains(response, f'src="{OLD_URL}"')
        # รูปถูกส่งไปพร้อมฟอร์มตอนกด Save (ไม่ใช่ fetch ตอนเลือกไฟล์)
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="image_file"')
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertNotContains(response, "data-upload-url")
        self.assertNotContains(response, "SAMPLE STORE")
        self.assertNotContains(response, "Sample Bistro")

    def test_page_without_current_image_shows_empty_placeholder(self):
        Restaurant.objects.create(owner=self.owner, slug="s", name="No Photo")
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertNotContains(response, "src=\"http")
        self.assertContains(response, "Add profile photo")

    def test_owner_without_store_sees_guidance_and_no_upload_url(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No store yet")
        self.assertNotContains(response, "data-upload-url")
        self.assertContains(response, "disabled")

    def test_page_only_shows_the_owners_own_store(self):
        other = make_owner("owner-b")
        Restaurant.objects.create(owner=other, slug="other", name="Other Shop")
        Restaurant.objects.create(owner=self.owner, slug="mine", name="My Shop")
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, "My Shop")
        self.assertNotContains(response, "Other Shop")

    def test_anonymous_user_is_redirected(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)


    def test_page_shows_all_editable_fields_with_current_values(self):
        Restaurant.objects.create(
            owner=self.owner, slug="full", name="Full Shop", category="Café",
            price="$$ · Mid-range", service_mode="queue", address="9 River Rd",
            phone="02-123-4567", map_url="https://maps.example.com/full",
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        html = response.content.decode()
        for name in ("name", "category", "price", "service_mode", "address",
                     "phone", "hours", "map_url", "description"):
            with self.subTest(field=name):
                self.assertIn(f'name="{name}"', html)
        self.assertContains(response, "9 River Rd")
        self.assertContains(response, 'value="02-123-4567"')
        self.assertContains(response, 'value="https://maps.example.com/full"')
        # ตัวเลือกที่บันทึกไว้ต้องถูก select
        self.assertContains(response, '<option value="Café" selected>')
        self.assertContains(response, '<option value="$$ · Mid-range" selected>')
        self.assertContains(response, '<option value="queue" selected>')

    def test_page_exposes_error_slots_for_the_script(self):
        Restaurant.objects.create(owner=self.owner, slug="e", name="E")
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        for name in ("name", "category", "address", "phone", "map_url", "image_file"):
            with self.subTest(field=name):
                self.assertContains(response, f'data-error-for="{name}"')

    def test_save_button_is_disabled_without_a_store(self):
        self.client.force_login(self.owner)
        html = self.client.get(self.url).content.decode()
        self.assertRegex(html, r"<button type=\"submit\" data-save-button disabled>")


class StoreDetailsSaveContractTests(TestCase):
    """What the browser does on Save: POST the form (multipart) with its CSRF token."""

    def setUp(self):
        self.owner = make_owner("owner-a")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="s", name="Store", image=OLD_URL,
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.url = reverse("owner_store_details")

    def csrf_token_from_form(self):
        html = self.client.get(self.url).content.decode()
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
        self.assertIsNotNone(match, "the form must contain a CSRF token")
        return match.group(1)

    def post(self, **data):
        return self.client.post(self.url, {**valid_data(), "image_file": image_file(), **data})

    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_save_with_csrf_token_from_form_succeeds(self, _upload):
        response = self.post(csrfmiddlewaretoken=self.csrf_token_from_form())
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, NEW_URL)

    @patch(UPLOAD_PATH)
    def test_save_without_csrf_token_is_rejected(self, upload):
        response = self.post()
        self.assertEqual(response.status_code, 403)
        upload.assert_not_called()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, OLD_URL)
