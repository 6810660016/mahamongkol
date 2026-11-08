"""Phase 7: รูปในส่วน Pictures (4 ช่อง) บันทึกพร้อมกดปุ่ม Save ของหน้า Store Details

Cloudinary ถูก mock ทั้งหมด การลบรูปเก่าใช้ on_commit จึงใช้ captureOnCommitCallbacks(execute=True)
"""

import itertools
from unittest.mock import patch

from cloudinary.exceptions import Error as CloudinaryError
from django.db import DatabaseError
from django.urls import reverse

from restaurants import services
from restaurants.models import MAX_GALLERY_IMAGES, Restaurant, RestaurantImage

from .store_test_utils import OLD_URL, UPLOAD_PATH, image_file, make_owner, valid_data
from .test_store_details_save import StoreDetailsSaveBase

DESTROY_PATH = "restaurants.services.cloudinary.uploader.destroy"
FOLDER = services.CLOUDINARY_FOLDER


def fake_uploader():
    """mock ของ cloudinary.uploader.upload: ทุกครั้งที่เรียกได้รูปใหม่ที่ไม่ซ้ำกัน"""
    counter = itertools.count(1)

    def upload(_file, **_kwargs):
        n = next(counter)
        return {
            "secure_url": f"https://res.cloudinary.com/demo/image/upload/v1/{FOLDER}/1/img{n}.jpg",
            "public_id": f"{FOLDER}/1/img{n}",
        }

    return upload


def gallery_id(n):
    return f"{FOLDER}/1/img{n}"


def gallery_url(n):
    return f"https://res.cloudinary.com/demo/image/upload/v1/{FOLDER}/1/img{n}.jpg"


class GalleryBase(StoreDetailsSaveBase):
    def add_saved(self, slot, public_id="", url=None, store=None):
        return RestaurantImage.objects.create(
            restaurant=store or self.store, slot=slot,
            image=url or f"https://example.com/saved{slot}.jpg", public_id=public_id,
        )

    def post_gallery(self, files=None, remove=(), ajax=True, **fields):
        data = valid_data(**fields)
        for slot, file in (files or {}).items():
            data[f"gallery_file_{slot}"] = file
        if remove:
            data["gallery_remove"] = [str(r) for r in remove]
        extra = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"} if ajax else {}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data, **extra)

    def slots(self):
        return {g.slot: g for g in RestaurantImage.objects.filter(restaurant=self.store)}


class RenderTests(GalleryBase):
    def test_page_has_four_empty_slots(self):
        response = self.client.get(self.url)
        self.assertEqual(MAX_GALLERY_IMAGES, 4)
        for n in range(1, 5):
            self.assertContains(response, f'name="gallery_file_{n}"')
        self.assertEqual(len(response.context["gallery_slots"]), 4)
        # ช่องที่ยังไม่มีรูป: ช่องติ๊ก Remove ถูกซ่อนไว้ทุกช่อง
        self.assertContains(response, "data-gallery-remove-label hidden", count=4)

    def test_saved_picture_is_shown_with_a_remove_checkbox(self):
        self.add_saved(2, url="https://example.com/p2.jpg")
        response = self.client.get(self.url)
        self.assertContains(response, 'src="https://example.com/p2.jpg"')
        self.assertContains(response, "data-gallery-remove-label hidden", count=3)  # ช่อง 2 โชว์ Remove
        slots = {s["slot"]: s["url"] for s in response.context["gallery_slots"]}
        self.assertEqual(slots, {1: "", 2: "https://example.com/p2.jpg", 3: "", 4: ""})

    def test_gallery_inputs_are_disabled_without_a_store(self):
        other = make_owner("no-store-owner")
        self.client.force_login(other)
        response = self.client.get(self.url)
        self.assertContains(response, 'name="gallery_file_1"')
        html = response.content.decode()
        for n in range(1, 5):
            tag = html[html.index(f'name="gallery_file_{n}"'):].split(">", 1)[0]
            self.assertIn("disabled", tag)

    def test_page_no_longer_says_pictures_are_preview_only(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "Pictures and Time are preview only")
        self.assertNotContains(response, "Pictures and Time below are still a preview")


class SaveGalleryTests(GalleryBase):
    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_upload_into_one_slot_is_saved(self, upload, _destroy):
        response = self.post_gallery({2: image_file()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.slots()), {2})
        self.assertEqual(self.slots()[2].image, gallery_url(1))
        self.assertEqual(self.slots()[2].public_id, gallery_id(1))
        upload.assert_called_once()
        self.assertIn(str(self.store.pk), upload.call_args.kwargs["folder"])

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_json_reports_every_slot_as_the_server_stored_it(self, _upload, _destroy):
        self.add_saved(4, url="https://example.com/p4.jpg")
        payload = self.post_gallery({1: image_file()}).json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["gallery"],
            [
                {"slot": 1, "url": gallery_url(1)},
                {"slot": 2, "url": ""},
                {"slot": 3, "url": ""},
                {"slot": 4, "url": "https://example.com/p4.jpg"},
            ],
        )

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_several_slots_and_the_profile_photo_in_one_save(self, upload, _destroy):
        data = valid_data()
        data["image_file"] = image_file()
        for n in (1, 3, 4):
            data[f"gallery_file_{n}"] = image_file()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data, follow=False)
        self.assertEqual(response.status_code, 302)  # ฟอร์มปกติ (ไม่มี JS) redirect
        self.assertEqual(upload.call_count, 4)
        self.assertEqual(set(self.slots()), {1, 3, 4})
        self.assertEqual(len({g.image for g in self.slots().values()}), 3)  # ไม่ซ้ำกัน
        self.store.refresh_from_db()
        self.assertNotIn(self.store.image, {g.image for g in self.slots().values()})

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_gallery_is_separate_from_the_main_image(self, _upload, _destroy):
        self.store.image_public_id = f"{FOLDER}/1/main"
        self.store.save()
        self.post_gallery({1: image_file()})
        self.store.refresh_from_db()
        self.assertEqual(self.store.image, OLD_URL)
        self.assertEqual(self.store.image_public_id, f"{FOLDER}/1/main")

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH)
    def test_saving_without_gallery_fields_keeps_saved_pictures(self, upload, destroy):
        self.add_saved(1, public_id=gallery_id(7))
        self.add_saved(3, public_id=gallery_id(8))
        response = self.post_gallery(name="Renamed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.slots()), {1, 3})
        upload.assert_not_called()
        destroy.assert_not_called()

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_a_fifth_slot_is_ignored(self, upload, _destroy):
        response = self.post_gallery({5: image_file()})
        self.assertEqual(response.status_code, 200)
        upload.assert_not_called()
        self.assertEqual(self.slots(), {})


class ReplaceAndRemoveTests(GalleryBase):
    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_replacing_a_slot_keeps_one_row_and_deletes_the_old_image(self, _upload, destroy):
        self.add_saved(1, public_id=gallery_id(90))
        self.post_gallery({1: image_file()})
        self.assertEqual(RestaurantImage.objects.filter(restaurant=self.store).count(), 1)
        self.assertEqual(self.slots()[1].public_id, gallery_id(1))
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0], gallery_id(90))

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_old_picture_is_not_deleted_before_commit(self, _upload, destroy):
        self.add_saved(1, public_id=gallery_id(90))
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(self.url, {**valid_data(), "gallery_file_1": image_file()})
        destroy.assert_not_called()
        self.assertEqual(len(callbacks), 1)

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH)
    def test_remove_deletes_the_row_and_the_cloudinary_image(self, upload, destroy):
        self.add_saved(2, public_id=gallery_id(90))
        self.add_saved(3, public_id=gallery_id(91))
        payload = self.post_gallery(remove=[2]).json()
        self.assertEqual(set(self.slots()), {3})
        upload.assert_not_called()
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0], gallery_id(90))
        self.assertEqual(payload["gallery"][1], {"slot": 2, "url": ""})

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH)
    def test_removing_a_picture_without_public_id_leaves_cloudinary_alone(self, _upload, destroy):
        self.add_saved(1, public_id="")
        self.post_gallery(remove=[1])
        self.assertEqual(self.slots(), {})
        destroy.assert_not_called()

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH)
    def test_bad_or_empty_remove_values_are_ignored(self, _upload, destroy):
        self.add_saved(1, public_id=gallery_id(90))
        response = self.post_gallery(remove=["0", "5", "abc", "-1", "", 3])  # 3 = ช่องว่าง
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.slots()), {1})
        destroy.assert_not_called()

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_new_file_and_remove_on_the_same_slot_means_replace(self, _upload, _destroy):
        self.add_saved(1, public_id=gallery_id(90))
        self.post_gallery({1: image_file()}, remove=[1])
        self.assertEqual(self.slots()[1].public_id, gallery_id(1))

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH)
    def test_another_owner_cannot_touch_this_stores_pictures(self, _upload, destroy):
        self.add_saved(1, public_id=gallery_id(90))
        intruder = make_owner("owner-b")
        Restaurant.objects.create(owner=intruder, slug="other", name="Other")
        self.client.force_login(intruder)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {**valid_data(), "gallery_remove": ["1"]}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(set(self.slots()), {1})
        destroy.assert_not_called()

    @patch(DESTROY_PATH)
    def test_image_shared_with_another_store_is_never_deleted(self, destroy):
        other = Restaurant.objects.create(owner=make_owner("owner-b"), slug="other", name="Other")
        self.add_saved(1, public_id=gallery_id(90), store=other)
        self.assertFalse(services.delete_cloudinary_image(gallery_id(90)))
        destroy.assert_not_called()


class NothingChangesOnFailureTests(GalleryBase):
    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH)
    def test_one_bad_file_uploads_nothing_and_saves_nothing(self, upload, destroy):
        self.add_saved(1, public_id=gallery_id(90))
        response = self.post_gallery(
            {1: image_file(), 2: image_file(b"not really an image", "x.jpg")},
            name="Should not save",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("gallery_file_2", response.json()["errors"])
        self.assertNotIn("gallery_file_1", response.json()["errors"])
        upload.assert_not_called()
        destroy.assert_not_called()
        self.assert_store_untouched()
        self.assertEqual(self.slots()[1].public_id, gallery_id(90))

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH)
    def test_wrong_type_is_rejected_for_a_slot(self, upload, _destroy):
        response = self.post_gallery({3: image_file(b"GIF89a" + b"\0" * 40, "a.gif", "image/gif")})
        self.assertEqual(response.status_code, 400)
        self.assertIn("gallery_file_3", response.json()["errors"])
        upload.assert_not_called()

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH)
    def test_cloudinary_failure_on_a_later_file_removes_the_earlier_upload(self, upload, destroy):
        self.add_saved(1, public_id=gallery_id(90))
        first = {"secure_url": gallery_url(1), "public_id": gallery_id(1)}
        upload.side_effect = [first, CloudinaryError("boom secret detail")]
        response = self.post_gallery({2: image_file(), 3: image_file()}, name="Should not save")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("secret", response.content.decode())
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0], gallery_id(1))  # รูปที่เพิ่งอัปโหลดถูกลบ
        self.assertEqual(set(self.slots()), {1})
        self.assert_store_untouched()

    @patch(DESTROY_PATH, return_value={"result": "ok"})
    @patch(UPLOAD_PATH, side_effect=fake_uploader())
    def test_db_failure_rolls_back_everything_and_deletes_all_new_uploads(self, _upload, destroy):
        self.add_saved(1, public_id=gallery_id(90))
        with patch.object(RestaurantImage, "save", side_effect=DatabaseError("db down")):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(DatabaseError):
                    services.update_restaurant_with_image(
                        self.store, self.owner, valid_data(name="Should not save"), image_file(),
                        gallery_files={1: image_file(), 2: image_file()},
                    )
        deleted = {call.args[0] for call in destroy.call_args_list}
        self.assertEqual(deleted, {gallery_id(1), gallery_id(2), gallery_id(3)})  # ไม่รวมรูปเดิม
        self.assert_store_untouched()  # ชื่อร้านที่แก้ก่อนหน้านี้ใน transaction ถูก rollback ด้วย
        self.assertEqual(self.slots()[1].public_id, gallery_id(90))
        self.assertEqual(set(self.slots()), {1})

    @patch(DESTROY_PATH)
    @patch(UPLOAD_PATH)
    def test_slot_outside_range_is_refused_by_the_service(self, upload, destroy):
        with self.assertRaises(services.RestaurantError):
            services.update_restaurant_with_image(
                self.store, self.owner, valid_data(), None, gallery_files={9: image_file()},
            )
        upload.assert_not_called()


class ModelTests(GalleryBase):
    def test_slot_is_unique_per_store(self):
        from django.db import IntegrityError, transaction
        self.add_saved(1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_saved(1)

    def test_same_slot_number_in_different_stores_is_fine(self):
        other = Restaurant.objects.create(owner=make_owner("owner-b"), slug="other", name="Other")
        self.add_saved(1)
        self.add_saved(1, store=other)
        self.assertEqual(RestaurantImage.objects.count(), 2)

    def test_deleting_the_store_deletes_its_gallery_rows(self):
        self.add_saved(1)
        self.store.delete()
        self.assertEqual(RestaurantImage.objects.count(), 0)
