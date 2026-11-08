from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from account.decorators import customer_ui_required, owner_ui_required
from account.ui import get_landing_url_name
from bookings import services as booking_services
from bookings.models import Booking
from dashboard import stats
from restaurants import services
from restaurants.forms import MAX_EXTRAS, PRICE_CHOICES, RestaurantForm
from restaurants.models import MAX_GALLERY_IMAGES, Restaurant


@customer_ui_required
def home_view(request):
    categories = [
        ("restaurant", "Restaurants", "Discover handpicked menus"),
        ("coffee", "Cafés", "Slow down and enjoy the moment"),
        ("spa", "Wellness", "Relax and recharge with ease"),
        ("service", "More services", "Book everything in one place"),
    ]

    favourites = [
        {
            "slug": r.slug,
            "name": r.name,
            "type": f"{r.category} · {r.type}" if r.type else r.category,
            "image": r.image,
            "rating": r.rating,
            "reviews": r.reviews,
        }
        for r in Restaurant.objects.published().order_by("-rating", "id")[:3]
    ]

    return render(
        request,
        "dashboard/home.html",
        {
            "categories": categories,
            "favourites": favourites,
        },
    )


def welcome_view(request):
    if request.user.is_authenticated:
        return redirect(get_landing_url_name(request))

    return render(request, "dashboard/welcome.html")


@owner_ui_required
def owner_dashboard_view(request):
    stores_data = [
        {
            "id": store.slug,
            "slug": store.slug,
            "name": store.name,
            "category": store.category,
            "price": store.price,
            "address": store.address,
            "hours": store.hours,
            "noShowGraceMinutes": store.no_show_grace_minutes,
            "image": store.image,
            "description": store.description,
            "status": store.status,
            "isOpen": store.is_open,
            "serviceMode": store.service_mode,
            "extras": store.extra_details,
            "urls": {
                # 1 บัญชี = 1 ร้าน หน้า Store Details จึงไม่ต้องใช้ slug
                "details": reverse("owner_store_details"),
                "status": reverse(
                    "owner_store_status",
                    args=[store.slug],
                ),
                "delete": reverse(
                    "owner_store_delete",
                    args=[store.slug],
                ),
            },
        }
        for store in Restaurant.objects.filter(owner=request.user)
    ]

    return render(
        request,
        "dashboard/owner_dashboard.html",
        {"stores_data": stores_data},
    )


@owner_ui_required
def owner_overview_view(request):
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    days = stats.parse_range(request.GET.get("range"))
    context = {
        "restaurant": restaurant,
        "stats": stats.owner_overview_stats(restaurant, days),
    }
    return render(request, "dashboard/owner_overview.html", context)


# ช่องข้อความ/ตัวเลือกบนหน้า Store Details (ชื่อ = name ของ input และชื่อ field ของ RestaurantForm)
STORE_DETAIL_FIELDS = (
    "name", "category", "price", "service_mode", "address",
    "phone", "hours", "map_url", "description", "no_show_grace_minutes",
)


def _wants_json(request):
    """fetch จาก owner_store_details.js ส่ง header นี้มา ฟอร์มปกติ (ไม่มี JS) จะไม่มี"""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _store_values(restaurant):
    if restaurant is None:
        return {}
    return {field: getattr(restaurant, field) for field in STORE_DETAIL_FIELDS}


def _store_extras(restaurant):
    """Extra details ที่บันทึกไว้ (list ของ {key, value}) สำหรับวาดแถวในหน้า"""
    if restaurant is None:
        return []
    return list(restaurant.extra_details or [])


def _posted_extras(request):
    """แถว Extra details ตามที่ผู้ใช้พิมพ์ (ใช้วาดหน้าใหม่ตอนบันทึกไม่ผ่าน จึงเก็บแถวที่กรอกไม่ครบไว้ด้วย)"""
    keys = request.POST.getlist("extra_key")
    values = request.POST.getlist("extra_value")
    return [
        {"key": k, "value": v}
        for k, v in zip(keys, values)
        if k.strip() or v.strip()
    ][:MAX_EXTRAS]


def _gallery_slots(restaurant, errors=None):
    """ช่อง Pictures ทั้งหมด (1..MAX_GALLERY_IMAGES) พร้อมรูปที่บันทึกไว้ (ว่าง = "")
    และข้อความ error ของช่อง (ถ้ามี) ใช้วาดหน้าและตอบ JSON หลังบันทึก"""
    saved = {}
    if restaurant is not None:
        saved = {image.slot: image.image for image in restaurant.gallery_images.all()}
    errors = errors or {}
    return [
        {
            "slot": slot,
            "url": saved.get(slot, ""),
            "error": " ".join(errors.get(f"gallery_file_{slot}", [])),
        }
        for slot in range(1, MAX_GALLERY_IMAGES + 1)
    ]


def _gallery_removals(request):
    """ช่องที่เจ้าของติ๊ก Remove (ค่าที่ไม่ใช่เลขช่องที่ถูกต้องจะถูกข้าม)"""
    slots = set()
    for raw in request.POST.getlist("gallery_remove"):
        if raw.isdigit() and 1 <= int(raw) <= MAX_GALLERY_IMAGES:
            slots.add(int(raw))
    return slots


def _render_store_details(request, restaurant, *, values=None, errors=None, extras=None):
    return render(
        request,
        "dashboard/owner_store_details.html",
        {
            "restaurant": restaurant,
            "values": _store_values(restaurant) if values is None else values,
            "errors": {f: " ".join(msgs) for f, msgs in (errors or {}).items()},
            "extras": _store_extras(restaurant) if extras is None else extras,
            "max_extras": MAX_EXTRAS,
            "gallery_slots": _gallery_slots(restaurant, errors),
            "category_choices": Restaurant.Category.choices,
            "price_choices": PRICE_CHOICES,
            "service_mode_choices": Restaurant.ServiceMode.choices,
        },
    )


@owner_ui_required
def owner_store_details_view(request):
    restaurant = Restaurant.objects.filter(owner=request.user).first()

    if request.method == "POST":
        return _save_store_details(request, restaurant)

    return _render_store_details(request, restaurant)


def _save_store_details(request, restaurant):
    """บันทึกหน้า Store Details ตอนกด Save (ข้อมูลร้าน + รูปโปรไฟล์ใน request เดียว)

    ลำดับ: ตรวจฟอร์มและไฟล์รูปให้ครบก่อน -> อัปโหลดรูปขึ้น Cloudinary (ถ้ามีไฟล์ใหม่)
    -> update_restaurant ถ้าขั้นไหนไม่ผ่านจะไม่บันทึกอะไรเลย รูปเดิมและข้อมูลเดิมจึงไม่หาย
    ตอบ JSON เมื่อเรียกจาก fetch (หน้าไม่ reload ไฟล์ที่เลือกไว้จึงอยู่ครบ)
    ส่วนฟอร์มปกติ (ไม่มี JS) จะ redirect เมื่อสำเร็จ หรือ render หน้าเดิมพร้อมค่าที่กรอกเมื่อไม่ผ่าน
    """
    wants_json = _wants_json(request)
    # มีเฉพาะ request จากหน้านี้ (ส่วน Extra details อยู่ในฟอร์ม) ถ้าไม่มีตัวนี้ extras ที่ไม่ได้ส่งมา
    # จะถูกตีความว่า "ลบทั้งหมด" จึงต้องไม่แตะ extra_details
    extras_present = "extras_present" in request.POST

    if restaurant is None:
        message = "บัญชีนี้ยังไม่มีร้าน กรุณาสร้างร้านจากแดชบอร์ดก่อน"
        if wants_json:
            return JsonResponse({"ok": False, "error": message, "errors": {}}, status=404)
        messages.error(request, message)
        return redirect("owner_store_details")

    form = RestaurantForm(request.POST)
    form_valid = form.is_valid()
    errors = {field: list(msgs) for field, msgs in form.errors.items()}

    image_file = request.FILES.get("image_file")
    if image_file:
        try:
            services.validate_image_upload(image_file)
        except services.RestaurantError as exc:
            errors["image_file"] = [str(exc)]

    # รูปในช่อง Pictures: gallery_file_1..N (ตรวจทุกไฟล์ก่อนอัปโหลดอะไรขึ้น Cloudinary)
    gallery_files = {}
    for slot in range(1, MAX_GALLERY_IMAGES + 1):
        file = request.FILES.get(f"gallery_file_{slot}")
        if not file:
            continue
        try:
            services.validate_image_upload(file)
        except services.RestaurantError as exc:
            errors[f"gallery_file_{slot}"] = [str(exc)]
        else:
            gallery_files[slot] = file

    if not form_valid or errors:
        message = "ยังไม่ได้บันทึก กรุณาตรวจสอบช่องที่มีข้อความแจ้งเตือน"
        if wants_json:
            return JsonResponse({"ok": False, "error": message, "errors": errors}, status=400)
        messages.error(request, message)
        values = {**_store_values(restaurant), **{
            field: request.POST[field] for field in STORE_DETAIL_FIELDS if field in request.POST
        }}
        # ฟอร์มที่ไม่มีส่วน Extra details (ไม่มี extras_present) ให้วาดแถวเดิมจาก DB
        extras = _posted_extras(request) if extras_present else None
        return _render_store_details(
            request, restaurant, values=values, errors=errors, extras=extras
        )

    data = dict(form.cleaned_data)
    # รูปเปลี่ยนได้ทางเดียวคืออัปโหลดไฟล์ใหม่ (ฟิลด์ image ของฟอร์มไม่ได้อยู่บนหน้านี้)
    data.pop("image", None)

    try:
        # รูปใหม่ (ถ้ามี) อัปโหลดก่อนแล้วค่อยบันทึก DB; รูปเก่าถูกลบหลัง commit (ดู services)
        # extra_details: บันทึกเฉพาะเมื่อ request มาจากหน้าที่มีส่วน Extra details (extras_present)
        # no_show_grace_minutes: เว้นว่างหรือไม่ส่งมา = คงค่าเดิม (service ข้ามค่า None)
        services.update_restaurant_with_image(
            restaurant,
            request.user,
            data,
            image_file,
            extra_details=data["extras"] if extras_present else None,
            gallery_files=gallery_files,
            gallery_removals=_gallery_removals(request),
        )
    except services.RestaurantError as exc:
        if wants_json:
            # ชี้ช่องรูปหลักเฉพาะเมื่ออัปโหลดแค่รูปเดียว (ถ้าอัปโหลดหลายรูปจะบอกไม่ได้ว่ารูปไหนพัง)
            upload_errors = (
                {"image_file": [str(exc)]} if image_file and not gallery_files else {}
            )
            return JsonResponse(
                {"ok": False, "error": str(exc), "errors": upload_errors}, status=400
            )
        messages.error(request, str(exc))
        return redirect("owner_store_details")

    message = f"บันทึกร้าน {restaurant.name} แล้ว"
    if wants_json:
        return JsonResponse(
            {
                "ok": True,
                "message": message,
                "name": restaurant.name,
                "image_url": restaurant.image,
                "extras": _store_extras(restaurant),
                "no_show_grace_minutes": restaurant.no_show_grace_minutes,
                "gallery": [
                    {"slot": g["slot"], "url": g["url"]} for g in _gallery_slots(restaurant)
                ],
            }
        )
    messages.success(request, message)
    return redirect("owner_store_details")


_COMPLETE_ERRORS = {
    "This booking is already completed.": "การจองนี้เสร็จสิ้นไปแล้ว",
    "A cancelled booking cannot be completed.": "การจองที่ยกเลิกแล้วไม่สามารถเปลี่ยนเป็นเสร็จสิ้นได้",
    "This booking is not due yet.": "ยังไม่ถึงวันที่จอง จึงยังเปลี่ยนเป็นเสร็จสิ้นไม่ได้",
    "This no-show can no longer be changed to completed.": "เลยวันที่จองแล้ว ไม่สามารถเปลี่ยน No Show เป็นเสร็จสิ้นได้",
    "This booking can no longer be completed.": "ไม่สามารถเปลี่ยนสถานะการจองนี้ได้",
    "You are not allowed to complete this booking.": "คุณไม่มีสิทธิ์จัดการการจองนี้",
}


def _booking_code(booking):
    return booking.code


def _bookings_url(day):
    return f"{reverse('owner_bookings')}?{urlencode({'date': day.isoformat()})}"


@owner_ui_required
def owner_bookings_view(request):
    """Real bookings of the owner's store for one day (?date=YYYY-MM-DD)."""
    restaurant = Restaurant.objects.filter(owner=request.user).first()

    try:
        day = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        day = timezone.localdate()

    bookings_data = []
    if restaurant is not None:
        # ไม่มี background worker: อัปเดต No Show ของร้านนี้ทุกครั้งที่เปิดหน้า
        booking_services.mark_no_shows(restaurant=restaurant)
        now = timezone.now()
        for booking in booking_services.bookings_for_day(restaurant, day):
            bookings_data.append(
                {
                    "id": _booking_code(booking),
                    "time": f"{booking.time:%H:%M}",
                    "name": booking.user.get_full_name() or booking.user.username,
                    "party": booking.guests,
                    "table": booking.table.name,
                    "status": booking.status,
                    "canCancel": booking.status == Booking.Status.CONFIRMED,
                    "canComplete": booking_services.can_complete(booking, now),
                    "cancelUrl": reverse("owner_booking_cancel", args=[booking.id]),
                    "completeUrl": reverse("owner_booking_complete", args=[booking.id]),
                }
            )

    return render(
        request,
        "dashboard/owner_bookings.html",
        {
            "restaurant": restaurant,
            "selected_date": day.isoformat(),
            "bookings_data": bookings_data,
        },
    )


@owner_ui_required
@require_POST
def owner_booking_cancel_view(request, booking_id):
    # การจองของร้านอื่น (หรือเจ้าของที่ไม่มีร้าน) จะได้ 404
    booking = get_object_or_404(
        Booking.objects.select_related("table__restaurant", "user"),
        pk=booking_id,
        table__restaurant__owner=request.user,
    )

    try:
        booking_services.cancel_booking(booking, request.user)
    except booking_services.BookingError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"ยกเลิกการจอง {_booking_code(booking)} แล้ว")

    return redirect(_bookings_url(booking.date))


@owner_ui_required
@require_POST
def owner_booking_complete_view(request, booking_id):
    # การจองของร้านอื่น (หรือเจ้าของที่ไม่มีร้าน) จะได้ 404
    booking = get_object_or_404(
        Booking.objects.select_related("table__restaurant", "user"),
        pk=booking_id,
        table__restaurant__owner=request.user,
    )

    # อัปเดต No Show ก่อน เพื่อให้ตรวจสถานะจากข้อมูลล่าสุด
    booking_services.mark_no_shows(restaurant=booking.table.restaurant)
    booking.refresh_from_db()

    try:
        booking_services.complete_booking(booking, request.user)
    except booking_services.BookingError as exc:
        messages.error(request, _COMPLETE_ERRORS.get(str(exc), str(exc)))
    else:
        messages.success(request, f"บันทึกการจอง {_booking_code(booking)} เป็นเสร็จสิ้นแล้ว")

    return redirect(_bookings_url(booking.date))


@owner_ui_required
def owner_queue_view(request):
    """Queue management page; the live data comes from the queues JSON endpoints."""
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    return render(request, "dashboard/owner_queue.html", {"restaurant": restaurant})


def _form_error_message(form):
    """รวมข้อความ error ของ form เป็นบรรทัดเดียวสำหรับ messages"""
    parts = []

    for field, errors in form.errors.items():
        if field == "__all__":
            label = "ข้อมูล"
        else:
            label = form.fields[field].label or field

        parts.append(f"{label}: {' '.join(errors)}")

    return "กรอกข้อมูลไม่ถูกต้อง · " + " · ".join(parts)


def _get_store(request, slug):
    return get_object_or_404(
        services.managed_restaurants(request.user),
        slug=slug,
    )


@owner_ui_required
@require_POST
def store_create(request):
    form = RestaurantForm(request.POST)

    if not form.is_valid():
        messages.error(request, _form_error_message(form))
        return redirect("owner_dashboard")

    cd = form.cleaned_data

    try:
        restaurant = services.create_restaurant(
            request.user,
            cd,
            extra_details=cd["extras"],
            table_count=cd["table_count"],
            seats=cd["seats_per_table"],
        )
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"สร้างร้าน {restaurant.name} เป็นฉบับร่างแล้ว",
        )

    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_update(request, slug):
    restaurant = _get_store(request, slug)
    form = RestaurantForm(request.POST)

    if not form.is_valid():
        messages.error(request, _form_error_message(form))
        return redirect("owner_dashboard")

    cd = form.cleaned_data

    try:
        services.update_restaurant(
            restaurant,
            request.user,
            cd,
            extra_details=cd["extras"],
        )
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"บันทึกร้าน {restaurant.name} แล้ว")

    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_status(request, slug):
    restaurant = _get_store(request, slug)
    is_open = request.POST.get("is_open")

    try:
        services.set_status(
            restaurant,
            request.user,
            status=request.POST.get("status") or None,
            is_open=None if is_open is None else is_open == "1",
        )
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"อัปเดตสถานะร้าน {restaurant.name} แล้ว",
        )

    return redirect("owner_dashboard")


@owner_ui_required
@require_POST
def store_delete(request, slug):
    restaurant = _get_store(request, slug)

    try:
        services.delete_restaurant(restaurant, request.user)
    except services.RestaurantError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "ลบร้านแล้ว")

    return redirect("owner_dashboard")