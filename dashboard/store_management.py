"""ส่วนช่วยของการสร้าง/แก้/ลบร้านจากแดชบอร์ดเจ้าของร้าน"""

from django.shortcuts import get_object_or_404

from restaurants import services


def form_error_message(form):
    """รวมข้อความ error ของ form เป็นบรรทัดเดียวสำหรับ messages"""
    parts = []

    for field, errors in form.errors.items():
        if field == "__all__":
            label = "ข้อมูล"
        else:
            label = form.fields[field].label or field

        parts.append(f"{label}: {' '.join(errors)}")

    return "กรอกข้อมูลไม่ถูกต้อง · " + " · ".join(parts)


def get_store(request, slug):
    return get_object_or_404(
        services.managed_restaurants(request.user),
        slug=slug,
    )
