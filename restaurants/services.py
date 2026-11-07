from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils.text import slugify

from .models import Restaurant, Table

DEFAULT_TABLE_COUNT = 6
DEFAULT_SEATS = 4
RESERVED_SLUGS = {"new"}  # ชนกับ route owner/stores/new/
MAX_SLUG_ATTEMPTS = 20

# field ที่เจ้าของแก้ได้ผ่านฟอร์ม (ไม่รวม owner, slug, status, is_open, rating, reviews)
EDITABLE_FIELDS = (
    "name", "category", "price", "address", "hours", "image", "description",
    "no_show_grace_minutes",
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
    """แก้ข้อมูลร้าน ไม่เปลี่ยน slug เพื่อไม่ให้ลิงก์เดิมของลูกค้าเสีย"""
    _require_manage(by_user, restaurant)
    for field, value in _field_values(data).items():
        setattr(restaurant, field, value)
    if extra_details is not None:
        restaurant.extra_details = list(extra_details)
    restaurant.save()
    return restaurant


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