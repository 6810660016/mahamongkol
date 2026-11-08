"""Saving the owner's profile image from Store Details (Django -> Cloudinary).

The image is uploaded only when the form is saved (POST /owner/store-details/),
together with the rest of the form. Cloudinary is always mocked: no network.
"""

from unittest.mock import patch

from cloudinary.exceptions import Error as CloudinaryError
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from restaurants.models import Restaurant
from restaurants.services import MAX_IMAGE_BYTES

from .store_test_utils import (
    JPEG_BYTES,
    NEW_URL,
    OLD_URL,
    PASSWORD,
    PNG_BYTES,
    UPLOAD_PATH,
    WEBP_BYTES,
    User,
    image_file,
    make_owner,
    valid_data,
)


class StoreImageSaveTests(TestCase):
    def setUp(self):
        self.owner = make_owner("owner-a")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="store-a", name="Store A", image=OLD_URL,
        )
        self.url = reverse("owner_store_details")

    def save(self, file=None, follow=True, **fields):
        data = valid_data(**fields)
        if file is not None:
            data["image_file"] = file
        return self.client.post(self.url, data, follow=follow)

    def assert_image_unchanged(self):
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, OLD_URL)

    # --- success -------------------------------------------------------------

    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_saving_with_new_image_uploads_and_stores_url(self, upload):
        self.client.force_login(self.owner)
        response = self.save(image_file())
        self.assertRedirects(response, self.url)
        self.assertContains(response, "บันทึกร้าน Store A แล้ว")
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
                self.save(image_file(content, name, ctype))
                self.store.refresh_from_db()
                self.assertEqual(self.store.image, NEW_URL)

    @patch(UPLOAD_PATH)
    def test_saving_without_a_new_image_keeps_the_current_one(self, upload):
        self.client.force_login(self.owner)
        response = self.save()
        self.assertContains(response, "บันทึกร้าน Store A แล้ว")
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_opening_the_page_never_uploads_or_changes_the_image(self, upload):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        upload.assert_not_called()
        self.assert_image_unchanged()

    # --- validation ----------------------------------------------------------

    @patch(UPLOAD_PATH)
    def test_non_image_file_is_rejected(self, upload):
        self.client.force_login(self.owner)
        response = self.save(image_file(b"hello", "note.txt", "text/plain"))
        self.assertContains(response, "รองรับเฉพาะไฟล์รูป")
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_fake_image_with_image_content_type_is_rejected(self, upload):
        # ไฟล์ข้อความที่ปลอมเป็น .jpg / image/jpeg ต้องไม่ผ่าน (ตรวจ magic bytes)
        self.client.force_login(self.owner)
        response = self.save(image_file(b"<script>alert(1)</script>"))
        self.assertContains(response, "รองรับเฉพาะไฟล์รูป")
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_oversized_image_is_rejected(self, upload):
        self.client.force_login(self.owner)
        big = JPEG_BYTES + b"\x00" * MAX_IMAGE_BYTES
        response = self.save(image_file(big))
        self.assertContains(response, "5 MB")
        upload.assert_not_called()
        self.assert_image_unchanged()

    # --- permissions ---------------------------------------------------------

    @patch(UPLOAD_PATH)
    def test_anonymous_user_cannot_save(self, upload):
        response = self.save(image_file(), follow=False)
        self.assertEqual(response.status_code, 302)
        upload.assert_not_called()
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH)
    def test_non_owner_account_cannot_save(self, upload):
        customer = User.objects.create_user("cust", "cust@example.com", PASSWORD)
        self.client.force_login(customer)
        response = self.save(image_file(), follow=False)
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
        self.save(image_file())
        other_store.refresh_from_db()
        self.assertEqual(other_store.image, NEW_URL)
        self.assert_image_unchanged()  # ร้านของ owner-a ไม่ถูกแตะ

    @patch(UPLOAD_PATH)
    def test_owner_without_store_gets_message_and_no_upload(self, upload):
        lonely = make_owner("lonely")
        self.client.force_login(lonely)
        response = self.save(image_file())
        self.assertContains(response, "ยังไม่มีร้าน")
        upload.assert_not_called()

    # --- Cloudinary failures -------------------------------------------------

    @patch(UPLOAD_PATH, side_effect=CloudinaryError("boom secret detail"))
    def test_cloudinary_failure_keeps_previous_image(self, _upload):
        self.client.force_login(self.owner)
        response = self.save(image_file())
        self.assertContains(response, "อัปโหลดรูปไม่สำเร็จ")
        self.assertNotContains(response, "boom")  # ไม่เปิดเผยรายละเอียดภายใน
        self.assert_image_unchanged()

    @patch(UPLOAD_PATH, return_value={})
    def test_unexpected_cloudinary_response_keeps_previous_image(self, _upload):
        self.client.force_login(self.owner)
        response = self.save(image_file())
        self.assertContains(response, "อัปโหลดรูปไม่สำเร็จ")
        self.assert_image_unchanged()

    # --- the old "upload immediately" endpoint is gone -----------------------

    def test_immediate_upload_endpoint_no_longer_exists(self):
        with self.assertRaises(NoReverseMatch):
            reverse("owner_store_image_upload")
