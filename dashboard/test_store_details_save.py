"""Saving the whole Store Details form (fields + photo) in one request.

Two entry points share one view:
- fetch() from owner_store_details.js (X-Requested-With) -> JSON, page does not reload
- a plain form post (no JS)                              -> redirect / re-render
Cloudinary is always mocked: these tests never touch the network.
"""

from unittest.mock import patch

from cloudinary.exceptions import Error as CloudinaryError
from django.test import TestCase
from django.urls import reverse

from restaurants.models import Restaurant

from .store_test_utils import (
    AJAX,
    NEW_URL,
    OLD_URL,
    UPLOAD_PATH,
    image_file,
    make_owner,
    valid_data,
)


class StoreDetailsSaveBase(TestCase):
    def setUp(self):
        self.owner = make_owner("owner-a")
        self.store = Restaurant.objects.create(
            owner=self.owner, slug="baan-suan", name="Baan Suan", category="Café",
            price="$ · Casual", service_mode="both", address="1 Old Rd", hours="Daily 9-18",
            description="Garden cafe", phone="02-000-0000", map_url="https://maps.example.com/old",
            image=OLD_URL, extra_details=[{"key": "Parking", "value": "Yes"}],
            no_show_grace_minutes=45,
        )
        self.url = reverse("owner_store_details")
        self.client.force_login(self.owner)

    def post(self, file=None, ajax=False, follow=False, **fields):
        data = valid_data(**fields)
        if file is not None:
            data["image_file"] = file
        extra = AJAX if ajax else {}
        return self.client.post(self.url, data, follow=follow, **extra)

    def assert_store_untouched(self):
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Baan Suan")
        self.assertEqual(self.store.category, "Café")
        self.assertEqual(self.store.address, "1 Old Rd")
        self.assertEqual(self.store.phone, "02-000-0000")
        self.assertEqual(self.store.image, OLD_URL)


class SaveFieldsTests(StoreDetailsSaveBase):
    NEW_FIELDS = {
        "name": "Baan Suan Riverside",
        "category": "Wellness",
        "price": "$$$ · Premium",
        "service_mode": "booking",
        "address": "99 New Rd, Bangkok",
        "phone": "+66 2 123 4567",
        "hours": "Mon-Fri 10-20",
        "map_url": "https://maps.example.com/new",
        "description": "Now by the river",
    }

    def test_all_fields_are_saved(self):
        self.post(**self.NEW_FIELDS)
        self.store.refresh_from_db()
        for field, value in self.NEW_FIELDS.items():
            with self.subTest(field=field):
                self.assertEqual(getattr(self.store, field), value)

    def test_fields_and_photo_are_saved_together(self):
        with patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL}) as upload:
            self.post(file=image_file(), **self.NEW_FIELDS)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Baan Suan Riverside")
        self.assertEqual(self.store.image, NEW_URL)
        upload.assert_called_once()

    def test_fields_not_on_this_page_are_left_alone(self):
        self.store.status = Restaurant.Status.PUBLISHED
        self.store.is_open = False
        self.store.save()
        self.post(**self.NEW_FIELDS)
        self.store.refresh_from_db()
        self.assertEqual(self.store.slug, "baan-suan")  # ลิงก์เดิมของลูกค้าไม่เสีย
        self.assertEqual(self.store.status, Restaurant.Status.PUBLISHED)
        self.assertFalse(self.store.is_open)
        self.assertEqual(self.store.extra_details, [{"key": "Parking", "value": "Yes"}])
        self.assertEqual(self.store.no_show_grace_minutes, 45)

    def test_saving_without_a_new_photo_keeps_the_current_one(self):
        with patch(UPLOAD_PATH) as upload:
            self.post(**self.NEW_FIELDS)
        upload.assert_not_called()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, OLD_URL)

    def test_phone_and_map_can_be_cleared(self):
        self.post(phone="", map_url="")
        self.store.refresh_from_db()
        self.assertEqual(self.store.phone, "")
        self.assertEqual(self.store.map_url, "")

    def test_plain_form_post_redirects_with_success_message(self):
        response = self.post(follow=True, **self.NEW_FIELDS)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "บันทึกร้าน Baan Suan Riverside แล้ว")


class SaveIsAllOrNothingTests(StoreDetailsSaveBase):
    """A failure anywhere means nothing is saved and Cloudinary is not called early."""

    def test_invalid_field_saves_nothing_and_skips_cloudinary(self):
        with patch(UPLOAD_PATH) as upload:
            response = self.post(file=image_file(), ajax=True, name="", address="Changed")
        self.assertEqual(response.status_code, 400)
        upload.assert_not_called()
        self.assert_store_untouched()

    def test_invalid_category_is_rejected(self):
        response = self.post(ajax=True, category="Casino")
        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.json()["errors"])
        self.assert_store_untouched()

    def test_bad_phone_and_map_are_rejected(self):
        for field, value in (
            ("phone", "call me maybe"),
            ("map_url", "javascript:alert(1)"),
            ("map_url", "ftp://maps.example.com/x"),
            ("map_url", "not a url"),
        ):
            with self.subTest(field=field, value=value):
                response = self.post(ajax=True, **{field: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["errors"])
        self.assert_store_untouched()

    def test_bad_photo_with_valid_fields_saves_nothing(self):
        with patch(UPLOAD_PATH) as upload:
            response = self.post(
                file=image_file(b"hello", "note.txt", "text/plain"), ajax=True, name="Changed",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("image_file", response.json()["errors"])
        upload.assert_not_called()
        self.assert_store_untouched()

    def test_form_and_photo_errors_are_reported_together(self):
        response = self.post(
            file=image_file(b"hello", "note.txt", "text/plain"), ajax=True, name="",
        )
        errors = response.json()["errors"]
        self.assertIn("name", errors)
        self.assertIn("image_file", errors)

    @patch(UPLOAD_PATH, side_effect=CloudinaryError("boom secret detail"))
    def test_cloudinary_failure_saves_no_field_at_all(self, _upload):
        response = self.post(file=image_file(), ajax=True, name="Changed", address="Changed")
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("image_file", payload["errors"])
        self.assertNotIn("boom", response.content.decode())
        self.assert_store_untouched()


class JsonResponseTests(StoreDetailsSaveBase):
    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_success_returns_json_the_script_uses(self, _upload):
        response = self.post(file=image_file(), ajax=True, name="Renamed")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["image_url"], NEW_URL)
        self.assertEqual(payload["name"], "Renamed")
        self.assertIn("Renamed", payload["message"])

    def test_success_without_photo_returns_the_current_image_url(self):
        payload = self.post(ajax=True).json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["image_url"], OLD_URL)

    def test_errors_are_a_dict_of_field_to_messages(self):
        payload = self.post(ajax=True, name="", phone="x y z").json()
        self.assertFalse(payload["ok"])
        self.assertIsInstance(payload["errors"]["name"], list)
        self.assertIn("phone", payload["errors"])
        self.assertTrue(payload["error"])

    def test_json_requests_leave_no_flash_message_for_the_next_page(self):
        self.post(ajax=True, name="Renamed")
        self.post(ajax=True, name="")
        page = self.client.get(self.url)
        self.assertNotContains(page, "บันทึกร้าน")
        self.assertNotContains(page, "ยังไม่ได้บันทึก")

    def test_owner_without_store_gets_404_json(self):
        lonely = make_owner("lonely")
        self.client.force_login(lonely)
        response = self.post(ajax=True)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["ok"])


class PlainFormFallbackTests(StoreDetailsSaveBase):
    """No JavaScript: an invalid post re-renders the page with what the user typed."""

    def test_invalid_post_rerenders_with_typed_values_and_errors(self):
        response = self.post(name="", address="Typed address", phone="bad phone!")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/owner_store_details.html")
        self.assertContains(response, "Typed address")  # ค่าที่กรอกไม่หาย
        self.assertContains(response, "bad phone!")
        self.assertContains(response, "ยังไม่ได้บันทึก")
        self.assertContains(response, "เบอร์โทรใส่ได้เฉพาะ")  # error ใต้ช่อง phone
        self.assert_store_untouched()

    def test_invalid_post_keeps_showing_the_saved_photo(self):
        response = self.post(file=image_file(), name="")
        self.assertContains(response, f'src="{OLD_URL}"')

    def test_cloudinary_failure_redirects_with_error_and_saves_nothing(self):
        with patch(UPLOAD_PATH, side_effect=CloudinaryError("boom")):
            response = self.post(file=image_file(), follow=True, name="Changed")
        self.assertContains(response, "อัปโหลดรูปไม่สำเร็จ")
        self.assert_store_untouched()


class PermissionTests(StoreDetailsSaveBase):
    def test_owner_cannot_change_another_owners_store(self):
        other = make_owner("owner-b")
        other_store = Restaurant.objects.create(owner=other, slug="b", name="Store B")
        self.client.force_login(other)
        self.post(name="B renamed")
        other_store.refresh_from_db()
        self.assertEqual(other_store.name, "B renamed")
        self.assert_store_untouched()  # ร้านของ owner-a ไม่ถูกแตะ

    def test_anonymous_user_is_redirected_and_nothing_changes(self):
        self.client.logout()
        with patch(UPLOAD_PATH) as upload:
            response = self.post(file=image_file(), name="Changed")
        self.assertEqual(response.status_code, 302)
        upload.assert_not_called()
        self.assert_store_untouched()


class ExistingEditButtonStillWorksTests(StoreDetailsSaveBase):
    """The modal on /owner/ does not send phone/map_url: it must not wipe them."""

    def modal_post(self, **overrides):
        data = {
            "name": "Baan Suan", "category": "Café", "price": "$ · Casual",
            "service_mode": "both", "address": "1 Old Rd", "hours": "Daily 9-18",
            "no_show_grace_minutes": "45", "image": OLD_URL, "description": "Garden cafe",
        }
        data.update(overrides)
        return self.client.post(reverse("owner_store_update", args=[self.store.slug]), data)

    def test_modal_edit_keeps_phone_and_map(self):
        response = self.modal_post(name="Renamed by modal")
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Renamed by modal")
        self.assertEqual(self.store.phone, "02-000-0000")
        self.assertEqual(self.store.map_url, "https://maps.example.com/old")

    def test_modal_edit_still_updates_extras(self):
        self.client.post(
            reverse("owner_store_update", args=[self.store.slug]),
            {
                "name": "Baan Suan", "category": "Café", "address": "1 Old Rd",
                "image": OLD_URL, "extra_key": ["Wifi"], "extra_value": ["Free"],
            },
        )
        self.store.refresh_from_db()
        self.assertEqual(self.store.extra_details, [{"key": "Wifi", "value": "Free"}])

    def test_modal_create_still_works_without_phone_and_map(self):
        lonely = make_owner("lonely")
        self.client.force_login(lonely)
        response = self.client.post(
            reverse("owner_store_create"),
            {"name": "Brand New", "category": "Restaurant", "address": "5 New St"},
        )
        self.assertEqual(response.status_code, 302)
        created = Restaurant.objects.get(owner=lonely)
        self.assertEqual((created.phone, created.map_url), ("", ""))
