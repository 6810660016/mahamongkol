"""Shared helpers for the Store Details tests (not a test module itself)."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from account.models import OwnerApplication

User = get_user_model()

PASSWORD = "Queue-pass-2026"
UPLOAD_PATH = "restaurants.services.cloudinary.uploader.upload"
NEW_URL = "https://res.cloudinary.com/demo/image/upload/v1/mahamongkol/new.jpg"
OLD_URL = "https://example.com/old.jpg"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}  # what fetch() in owner_store_details.js sends

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


def image_file(content=JPEG_BYTES, name="shop.jpg", content_type="image/jpeg", field_name=None):
    return SimpleUploadedFile(name, content, content_type=content_type)


def valid_data(**overrides):
    """All the text fields the Store Details form posts."""
    data = {
        "name": "Store A",
        "category": "Restaurant",
        "price": "",
        "service_mode": "both",
        "address": "1 Main St",
        "phone": "",
        "hours": "",
        "map_url": "",
        "description": "",
    }
    data.update(overrides)
    return data
