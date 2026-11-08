import logging
from functools import partial

import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils.text import slugify

from .models import Restaurant, Table

logger = logging.getLogger(__name__)

DEFAULT_TABLE_COUNT = 6
DEFAULT_SEATS = 4
RESERVED_SLUGS = {"new"}  # ชนกับ route owner/stores/new/
MAX_SLUG_ATTEMPTS = 20

# รูปหลักของร้านที่อัปโหลดขึ้น Cloudinary
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CLOUDINARY_FOLDER = "mahamongkol/restaurants"

# field ที่เจ้าของแก้ได้ผ่านฟอร์ม (ไม่รวม owner, slug, status, is_open, rating, reviews)
EDITABLE_FIELDS = (
    "name", "category", "price", "address", "hours", "phone", "map_url", "image", "description",
    "no_show_grace_minutes",
    "service_mode",
)


def _field_values(data):
    """ค่าจากฟอร์มที่จะบันทึก ช่องตัวเลขที่เว้นว่าง (None) ให้ข้ามเพื่อคงค่าเดิม/ค่าเริ่มต้น"""
    return {
        f: data[f]
        for f in EDITABLE_FIELDS
        if f in data and not (f == "no_show_grace_minutes" and data[f] is None)
    }


class RestaurantError(Exception):
    """การสร้าง/แก้ร้านไม่สำเร็จ ข้อความปลอดภัยที่จะแสดงให้ผู้ใช้เห็น"""


def can_manage(user, restaurant):
    """admin จัดการได้ทุกร้าน เจ้าของจัดการได้เฉพาะร้านของตัวเอง"""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_admin_role:
        return True
    return user.is_owner_role and restaurant.owner_id == user.id


def _require_manage(user, restaurant):
    if not can_manage(user, restaurant):
        raise RestaurantError("คุณไม่มีสิทธิ์จัดการร้านนี้")


def _slug_candidates(name):
    base = slugify(name, allow_unicode=True) or "store"
    if base in RESERVED_SLUGS:
        base = f"{base}-store"
    yield base
    for n in range(2, MAX_SLUG_ATTEMPTS + 2):
        yield f"{base}-{n}"


def create_restaurant(owner, data, *, extra_details=(), table_count=None, seats=None):
    """สร้างร้านเป็น draft ให้ owner พร้อมโต๊ะเริ่มต้น (1 บัญชีมีได้ 1 ร้าน)"""
    if Restaurant.objects.filter(owner=owner).exists():
        raise RestaurantError("บัญชีนี้มีร้านอยู่แล้ว 1 ร้าน สร้างร้านเพิ่มไม่ได้")

    table_count = table_count or DEFAULT_TABLE_COUNT
    seats = seats or DEFAULT_SEATS

    for slug in _slug_candidates(data["name"]):
        try:
            with transaction.atomic():
                restaurant = Restaurant.objects.create(
                    owner=owner,
                    slug=slug,
                    status=Restaurant.Status.DRAFT,
                    extra_details=list(extra_details),
                    **_field_values(data),
                )
                Table.objects.bulk_create(
                    Table(restaurant=restaurant, name=f"T{i}", capacity=seats)
                    for i in range(1, table_count + 1)
                )
            return restaurant
        except IntegrityError:
            if Restaurant.objects.filter(owner=owner).exists():
                # สร้างพร้อมกันสองคำขอ อีกคำขอสร้างร้านให้บัญชีนี้ไปก่อนแล้ว
                raise RestaurantError("บัญชีนี้มีร้านอยู่แล้ว 1 ร้าน สร้างร้านเพิ่มไม่ได้") from None
            continue  # slug ชน (รวมกรณีสร้างพร้อมกัน) ลอง slug ถัดไป
    raise RestaurantError("สร้างร้านไม่สำเร็จ กรุณาลองเปลี่ยนชื่อร้าน")

def managed_restaurants(user):
    restaurants = Restaurant.objects.all()
    if user.is_superuser or user.is_admin_role:
        return restaurants
    return restaurants.filter(owner=user)

def update_restaurant(restaurant, by_user, data, *, extra_details=None):
    """แก้ข้อมูลร้าน ไม่เปลี่ยน slug เพื่อไม่ให้ลิงก์เดิมของลูกค้าเสีย

    ถ้ารูป (image) เปลี่ยน จะเก็บ data["image_public_id"] (ถ้ามี) คู่กับรูปใหม่ แล้วลบรูปเก่า
    บน Cloudinary หลัง DB commit เท่านั้น (ถ้าลบไม่สำเร็จแค่ log ไม่ทำให้การบันทึกล้ม)
    """
    _require_manage(by_user, restaurant)
    values = _field_values(data)
    old_public_id = restaurant.image_public_id
    image_changed = "image" in values and values["image"] != restaurant.image

    with transaction.atomic():
        for field, value in values.items():
            setattr(restaurant, field, value)
        if image_changed:
            # URL ที่วางเองไม่มี public_id จึงต้องเคลียร์ค่าเดิม ไม่ให้ชี้ไปรูปที่เลิกใช้แล้ว
            restaurant.image_public_id = data.get("image_public_id", "")
        if extra_details is not None:
            restaurant.extra_details = list(extra_details)
        restaurant.save()
        if image_changed and old_public_id and old_public_id != restaurant.image_public_id:
            transaction.on_commit(partial(delete_cloudinary_image, old_public_id))
    return restaurant


def update_restaurant_with_image(
    restaurant, by_user, data, uploaded_file=None, *, extra_details=None
):
    """แก้ข้อมูลร้านพร้อมรูปใหม่ (ถ้ามี) ลำดับ: อัปโหลดรูปใหม่ -> บันทึก DB -> ลบรูปเก่า

    ถ้าบันทึก DB ไม่สำเร็จ (error อะไรก็ตาม) จะลบรูปใหม่ที่เพิ่งอัปโหลดทิ้ง แล้ว raise ต่อ
    รูปเดิมและข้อมูลเดิมจึงไม่เปลี่ยน และไม่มีรูปใหม่ค้างบน Cloudinary
    """
    data = dict(data)
    new_public_id = ""
    if uploaded_file is not None:
        data["image"], new_public_id = upload_store_image(restaurant, by_user, uploaded_file)
        data["image_public_id"] = new_public_id
    try:
        return update_restaurant(restaurant, by_user, data, extra_details=extra_details)
    except Exception:
        if new_public_id:
            delete_cloudinary_image(new_public_id)
        raise


def set_status(restaurant, by_user, *, status=None, is_open=None):
    """เปลี่ยนสถานะ draft/published หรือเปิด-ปิดร้าน"""
    _require_manage(by_user, restaurant)
    if status is not None:
        if status not in Restaurant.Status.values:
            raise RestaurantError("สถานะไม่ถูกต้อง")
        restaurant.status = status
    if is_open is not None:
        restaurant.is_open = bool(is_open)
    restaurant.save(update_fields=["status", "is_open"])
    return restaurant


def delete_restaurant(restaurant, by_user):
    """ลบร้าน ถ้ามีประวัติการจองจะลบไม่ได้ (Booking.table เป็น PROTECT)"""
    _require_manage(by_user, restaurant)
    try:
        restaurant.delete()
    except ProtectedError:
        raise RestaurantError(
            "ร้านนี้มีประวัติการจองอยู่ จึงลบไม่ได้ ให้ปิดร้านแทน"
        ) from None


def _looks_like_image(uploaded_file):
    """ตรวจ magic bytes จริงของไฟล์ (JPEG/PNG/WebP) ไม่เชื่อแค่นามสกุลหรือ Content-Type"""
    uploaded_file.seek(0)
    head = uploaded_file.read(12)
    uploaded_file.seek(0)
    return (
        head.startswith(b"\xff\xd8\xff")  # JPEG
        or head.startswith(b"\x89PNG\r\n\x1a\n")  # PNG
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")  # WebP
    )


def validate_image_upload(uploaded_file):
    """ตรวจไฟล์รูปที่อัปโหลด ถ้าไม่ผ่านจะ raise RestaurantError"""
    if uploaded_file is None:
        raise RestaurantError("กรุณาเลือกไฟล์รูปภาพ")
    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise RestaurantError("ไฟล์รูปต้องมีขนาดไม่เกิน 5 MB")
    if uploaded_file.content_type not in ALLOWED_IMAGE_TYPES or not _looks_like_image(uploaded_file):
        raise RestaurantError("รองรับเฉพาะไฟล์รูป JPG, PNG หรือ WebP เท่านั้น")


def upload_store_image(restaurant, by_user, uploaded_file):
    """ตรวจไฟล์รูปแล้วอัปโหลดขึ้น Cloudinary คืนค่า (secure_url, public_id)

    ฟังก์ชันนี้ **ไม่บันทึก** อะไรลง DB ผู้เรียกต้องบันทึกเองผ่าน update_restaurant
    (ใช้ update_restaurant_with_image ที่ดูแลการลบรูปเก่า/รูปใหม่ที่บันทึกไม่สำเร็จให้)
    ถ้าตรวจไฟล์หรืออัปโหลดไม่ผ่านจะ raise RestaurantError (ไม่แตะรูปเดิม)
    """
    _require_manage(by_user, restaurant)
    validate_image_upload(uploaded_file)

    try:
        result = cloudinary.uploader.upload(
            uploaded_file,
            folder=f"{CLOUDINARY_FOLDER}/{restaurant.pk}",
            resource_type="image",
        )
        return result["secure_url"], result.get("public_id", "")
    except (CloudinaryError, KeyError, OSError):
        raise RestaurantError("อัปโหลดรูปไม่สำเร็จ กรุณาลองใหม่อีกครั้ง") from None


def delete_cloudinary_image(public_id):
    """ลบรูปบน Cloudinary แบบ best effort คืน True ถ้าลบแล้ว ไม่เคย raise

    ลบเฉพาะรูปใน folder ของเรา และไม่ลบถ้ายังมีร้านอ้างถึง public_id นี้อยู่
    (ใช้กับ on_commit และการเก็บกวาดหลัง error จึงห้ามทำให้การบันทึกของผู้ใช้ล้ม)
    """
    if not public_id or not public_id.startswith(f"{CLOUDINARY_FOLDER}/"):
        return False
    try:
        if Restaurant.objects.filter(image_public_id=public_id).exists():
            return False
        result = cloudinary.uploader.destroy(
            public_id, resource_type="image", invalidate=True
        )
    except Exception:  # noqa: BLE001 - ลบไม่สำเร็จต้องไม่ทำให้ผู้ใช้เห็น error
        logger.exception("Could not delete Cloudinary image %s", public_id)
        return False
    if result.get("result") not in ("ok", "not found"):
        logger.warning("Cloudinary did not delete %s: %s", public_id, result)
        return False
    return True
