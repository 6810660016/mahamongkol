"""The Store Details page: real store data, profile photo upload wiring, CSRF."""

import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from account.models import OwnerApplication
from restaurants.models import Restaurant

User = get_user_model()

PASSWORD = "Queue-pass-2026"
UPLOAD_PATH = "restaurants.services.cloudinary.uploader.upload"
NEW_URL = "https://res.cloudinary.com/demo/image/upload/v1/mahamongkol/new.jpg"
OLD_URL = "https://example.com/old.jpg"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def make_owner(username):
    owner = User.objects.create_user(
        username, f"{username}@example.com", PASSWORD, role=User.Role.OWNER,
    )
    OwnerApplication.objects.create(
        user=owner, contact_name=username, business_name=f"{username} business",
        status=OwnerApplication.Status.APPROVED,
    )
    return owner


class OwnerStoreDetailsPageTests(TestCase):
    def setUp(self):
        self.owner = make_owner("owner-a")
        self.url = reverse("owner_store_details")
        self.upload_url = reverse("owner_store_image_upload")

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
        self.assertContains(response, f'data-upload-url="{self.upload_url}"')
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


class StoreDetailsUploadContractTests(TestCase):
    """What the page's JavaScript does: read data-csrf, POST FormData with X-CSRFToken."""

    def setUp(self):
        self.owner = make_owner("owner-a")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="s", name="Store", image=OLD_URL,
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)

    def csrf_token_from_page(self):
        html = self.client.get(reverse("owner_store_details")).content.decode()
        match = re.search(r'data-csrf="([^"]+)"', html)
        self.assertIsNotNone(match, "page must expose the CSRF token to the script")
        return match.group(1)

    def post(self, **extra):
        file = SimpleUploadedFile("a.jpg", JPEG_BYTES, content_type="image/jpeg")
        return self.client.post(reverse("owner_store_image_upload"), {"image": file}, **extra)

    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_upload_with_csrf_header_from_page_succeeds(self, _upload):
        token = self.csrf_token_from_page()
        response = self.post(HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["image_url"], NEW_URL)
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, NEW_URL)

    @patch(UPLOAD_PATH)
    def test_upload_without_csrf_token_is_rejected(self, upload):
        response = self.post()
        self.assertEqual(response.status_code, 403)
        upload.assert_not_called()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, OLD_URL)
