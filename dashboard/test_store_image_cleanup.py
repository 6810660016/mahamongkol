"""Phase 6: เก็บ public_id ของรูป และลบรูปเก่าบน Cloudinary หลัง DB commit

Cloudinary ถูก mock ทั้งหมด (ไม่แตะเครือข่าย) การลบใช้ transaction.on_commit
จึงต้องใช้ captureOnCommitCallbacks(execute=True) เพื่อให้ callback ทำงานใน TestCase
"""

from unittest.mock import patch

from cloudinary.exceptions import Error as CloudinaryError
from django.db import DatabaseError

from restaurants import services
from restaurants.models import Restaurant

from .store_test_utils import (
    NEW_URL,
    OLD_URL,
    UPLOAD_PATH,
    image_file,
    make_owner,
    valid_data,
)
from .test_store_details_save import StoreDetailsSaveBase

DESTROY_PATH = "restaurants.services.cloudinary.uploader.destroy"
FOLDER = services.CLOUDINARY_FOLDER
OLD_ID = f"{FOLDER}/1/old-shop"
NEW_ID = f"{FOLDER}/1/new-shop"
UPLOADED = {"secure_url": NEW_URL, "public_id": NEW_ID}


class CleanupBase(StoreDetailsSaveBase):
    def setUp(self):
        super().setUp()
        # ร้านที่เคยอัปโหลดรูปผ่านหน้า Store Details (มี public_id)
        self.store.image_public_id = OLD_ID
        self.store.save()

    def save_with_new_image(self, **fields):
        with self.captureOnCommitCallbacks(execute=True):
            return self.post(image_file(), **fields)


class PublicIdStoredTests(CleanupBase):
    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_new_upload_stores_url_and_public_id(self, _upload, _destroy):
        self.save_with_new_image()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, NEW_URL)
        self.assertEqual(self.store.image_public_id, NEW_ID)

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, return_value={"secure_url": NEW_URL})
    def test_response_without_public_id_stores_empty_value(self, _upload, _destroy):
        self.save_with_new_image()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, NEW_URL)
        self.assertEqual(self.store.image_public_id, "")

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH)
    def test_saving_without_new_image_keeps_public_id_and_deletes_nothing(self, upload, destroy):
        with self.captureOnCommitCallbacks(execute=True):
            self.post(name="Renamed")
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Renamed")
        self.assertEqual(self.store.image_public_id, OLD_ID)
        upload.assert_not_called()
        destroy.assert_not_called()


class OldImageDeletedTests(CleanupBase):
    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_old_image_is_deleted_after_commit(self, _upload, destroy):
        self.save_with_new_image()
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0], OLD_ID)

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_old_image_is_not_deleted_before_commit(self, _upload, destroy):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.post(image_file())
        destroy.assert_not_called()
        self.assertEqual(len(callbacks), 1)

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_legacy_image_without_public_id_is_left_alone(self, _upload, destroy):
        self.store.image_public_id = ""
        self.store.save()
        self.save_with_new_image()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, NEW_URL)
        destroy.assert_not_called()

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_image_outside_our_folder_is_never_deleted(self, _upload, destroy):
        self.store.image_public_id = "someone-else/photo"
        self.store.save()
        self.save_with_new_image()
        destroy.assert_not_called()

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_image_still_used_by_another_store_is_not_deleted(self, _upload, destroy):
        Restaurant.objects.create(
            owner=make_owner("owner-b"), slug="other", name="Other", image_public_id=OLD_ID,
        )
        self.save_with_new_image()
        destroy.assert_not_called()

    @patch(DESTROY_PATH, side_effect=CloudinaryError("boom secret detail"))
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_delete_failure_does_not_break_the_save(self, _upload, destroy):
        with self.assertLogs("restaurants.services", level="ERROR"):
            response = self.save_with_new_image(ajax=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        destroy.assert_called_once()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, NEW_URL)
        self.assertEqual(self.store.image_public_id, NEW_ID)

    @patch(DESTROY_PATH, return_value={"result": "error"})
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_unexpected_delete_result_is_logged_not_raised(self, _upload, _destroy):
        with self.assertLogs("restaurants.services", level="WARNING"):
            response = self.save_with_new_image(ajax=True)
        self.assertEqual(response.status_code, 200)


class NothingDeletedOnFailureTests(CleanupBase):
    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH)
    def test_invalid_form_uploads_and_deletes_nothing(self, upload, destroy):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(image_file(), ajax=True, name="")
        self.assertEqual(response.status_code, 400)
        upload.assert_not_called()
        destroy.assert_not_called()
        self.assert_store_untouched()

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH, side_effect=CloudinaryError("boom"))
    def test_failed_upload_keeps_and_does_not_delete_old_image(self, _upload, destroy):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(image_file(), ajax=True)
        self.assertEqual(response.status_code, 400)
        destroy.assert_not_called()
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, OLD_URL)
        self.assertEqual(self.store.image_public_id, OLD_ID)

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_db_failure_deletes_new_upload_and_keeps_old_image(self, _upload, destroy):
        with (
            patch.object(Restaurant, "save", side_effect=DatabaseError("db down")),
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaises(DatabaseError),
        ):
            services.update_restaurant_with_image(
                self.store, self.owner, valid_data(), image_file()
            )
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0], NEW_ID)  # รูปใหม่ถูกลบ ไม่ใช่รูปเก่า
        fresh = Restaurant.objects.get(pk=self.store.pk)
        self.assertEqual(fresh.image, OLD_URL)
        self.assertEqual(fresh.image_public_id, OLD_ID)

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH, return_value=UPLOADED)
    def test_user_without_permission_uploads_and_deletes_nothing(self, upload, destroy):
        stranger = make_owner("owner-c")
        with self.assertRaises(services.RestaurantError):
            services.update_restaurant_with_image(
                self.store, stranger, valid_data(), image_file()
            )
        upload.assert_not_called()
        destroy.assert_not_called()


class UrlReplacedByHandTests(CleanupBase):
    """endpoint store_update ยังอยู่: ถ้าเปลี่ยน image เป็น URL ที่วางเอง ต้องไม่เหลือ public_id เก่า"""

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    def test_pasting_a_url_clears_public_id_and_deletes_old_upload(self, destroy):
        with self.captureOnCommitCallbacks(execute=True):
            services.update_restaurant(
                self.store, self.owner, {"image": "https://example.com/pasted.jpg"}
            )
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, "https://example.com/pasted.jpg")
        self.assertEqual(self.store.image_public_id, "")
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0], OLD_ID)

    @patch(DESTROY_PATH)
    def test_same_url_again_changes_nothing(self, destroy):
        with self.captureOnCommitCallbacks(execute=True):
            services.update_restaurant(self.store, self.owner, {"image": OLD_URL})
        self.store.refresh_from_db()
        self.assertEqual(self.store.image_public_id, OLD_ID)
        destroy.assert_not_called()
