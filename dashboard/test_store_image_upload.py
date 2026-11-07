"""Backend tests for the owner's store image upload (Django -> Cloudinary).

Cloudinary is always mocked: these tests never touch the network.
"""

from unittest.mock import patch

from cloudinary.exceptions import Error as CloudinaryError
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from account.models import OwnerApplication
from restaurants.models import Restaurant
from restaurants.services import MAX_IMAGE_BYTES

User = get_user_model()

PASSWORD = "Queue-pass-2026"
UPLOAD_PATH = "restaurants.services.cloudinary.uploader.upload"
NEW_URL = "https://res.cloudinary.com/demo/image/upload/v1/mahamongkol/new.jpg"
OLD_URL = "https://example.com/old.jpg"

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64


def make_owner(username):
    owner = User.objects.create_user(
        username, f"{username}@example.com", PASSWORD, role=User.Role.OWNER,
    )
    OwnerApplication.objects.create(
        user=owner, contact_name=username, business_name=f"{username} business",
        status=OwnerApplication.Status.APPROVED,
    )
    return owner


def image_file(content=JPEG_BYTES, name="shop.jpg", content_type="image/jpeg"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class StoreImageUploadTests(TestCase):
    def setUp(self):
        self.owner = make_owner("owner-a")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="store-a", name="Store A", image=OLD_URL,
        )
        self.url = reverse("owner_store_image_upload")

    def post(self, file=None):
        data = {} if file is None else {"image": file}
        return self.client.post(self.url, data)

    def assert_image_unchanged(self):
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, OLD_URL)

    # --- success -------------------------------------------------------------

    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_owner_can_upload_valid_image(self, upload):
        self.client.force_login(self.owner)
        response = self.post(image_file())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "image_url": NEW_URL})
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, NEW_URL)
        upload.assert_called_once()
        self.assertIn(str(self.store.pk), upload.call_args.kwargs["folder"])

    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_png_and_webp_are_accepted(self, _upload):
        self.client.force_login(self.owner)
        for name, content, ctype in (
            ("a.png", PNG_BYTES, "image/png"),
            ("a.webp", WEBP_BYTES, "image/webp"),
        ):
            with self.subTest(name):
                self.assertEqual(self.post(image_file(content, name, ctype)).status_code, 200)

    # --- validation ----------------------------------------------------------

    @patch(UPLOAD_PATH)
    def test_missing_file_returns_error(self, upload):
        self.client.force_login(self.owner)
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_non_image_file_returns_error(self, upload):
        self.client.force_login(self.owner)
        response = self.post(image_file(b"hello", "note.txt", "text/plain"))
        self.assertEqual(response.status_code, 400)
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_fake_image_with_image_content_type_is_rejected(self, upload):
        # ไฟล์ข้อความที่ปลอมเป็น .jpg / image/jpeg ต้องไม่ผ่าน (ตรวจ magic bytes)
        self.client.force_login(self.owner)
        response = self.post(image_file(b"<script>alert(1)</script>"))
        self.assertEqual(response.status_code, 400)
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_oversized_image_returns_error(self, upload):
        self.client.force_login(self.owner)
        big = JPEG_BYTES + b"\x00" * MAX_IMAGE_BYTES
        response = self.post(image_file(big))
        self.assertEqual(response.status_code, 400)
        self.assertIn("5 MB", response.json()["error"])
        upload.assert_not_called()
        self.assert_image_unchanged()

    # --- permissions ---------------------------------------------------------

    @patch(UPLOAD_PATH)
    def test_anonymous_user_cannot_upload(self, upload):
        response = self.post(image_file())
        self.assertEqual(response.status_code, 302)
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_non_owner_account_cannot_upload(self, upload):
        customer = User.objects.create_user("cust", "cust@example.com", PASSWORD)
        self.client.force_login(customer)
        response = self.post(image_file())
        self.assertEqual(response.status_code, 302)
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_owner_only_changes_their_own_store(self, _upload):
        other = make_owner("owner-b")
        other_store = Restaurant.objects.create(
            owner=other, slug="store-b", name="Store B", image=OLD_URL,
        )
        self.client.force_login(other)
        self.assertEqual(self.post(image_file()).status_code, 200)
        other_store.refresh_from_db()
        self.assertEqual(other_store.image, NEW_URL)
        self.assert_image_unchanged()  # ร้านของ owner-a ไม่ถูกแตะ

    def test_owner_without_store_gets_404(self):
        lonely = make_owner("lonely")
        self.client.force_login(lonely)
        self.assertEqual(self.post(image_file()).status_code, 404)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    # --- Cloudinary failures -------------------------------------------------

    @patch(UPLOAD_PATH, side_effect=CloudinaryError("boom secret detail"))
    def test_cloudinary_failure_keeps_previous_image(self, _upload):
        self.client.force_login(self.owner)
        response = self.post(image_file())
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("boom", response.json()["error"])  # ไม่เปิดเผยรายละเอียดภายใน
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH, return_value={})
    def test_unexpected_cloudinary_response_keeps_previous_image(self, _upload):
        self.client.force_login(self.owner)
        self.assertEqual(self.post(image_file()).status_code, 400)
        self.assert_image_unchanged()
