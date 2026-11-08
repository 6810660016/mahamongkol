"""ส่วนช่วยของหน้าการจองของเจ้าของร้าน"""

from urllib.parse import urlencode

from django.urls import reverse

COMPLETE_ERRORS = {
    "This booking is already completed.": "การจองนี้เสร็จสิ้นไปแล้ว",
    "A cancelled booking cannot be completed.": "การจองที่ยกเลิกแล้วไม่สามารถเปลี่ยนเป็นเสร็จสิ้นได้",
    "This booking is not due yet.": "ยังไม่ถึงวันที่จอง จึงยังเปลี่ยนเป็นเสร็จสิ้นไม่ได้",
    "This no-show can no longer be changed to completed.": "เลยวันที่จองแล้ว ไม่สามารถเปลี่ยน No Show เป็นเสร็จสิ้นได้",
    "This booking can no longer be completed.": "ไม่สามารถเปลี่ยนสถานะการจองนี้ได้",
    "You are not allowed to complete this booking.": "คุณไม่มีสิทธิ์จัดการการจองนี้",
}


def booking_code(booking):
    return booking.code


def bookings_url(day):
    return f"{reverse('owner_bookings')}?{urlencode({'date': day.isoformat()})}"
