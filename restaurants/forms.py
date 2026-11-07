from django import forms

from .models import MAX_NO_SHOW_GRACE_MINUTES, Restaurant

PRICE_CHOICES = [
    ("", "Not specified"),
    ("$ · Casual", "$ · Casual"),
    ("$$ · Mid-range", "$$ · Mid-range"),
    ("$$$ · Premium", "$$$ · Premium"),
]

MAX_EXTRAS = 10


class RestaurantForm(forms.ModelForm):
    # ช่องนี้ไม่ใช่ field ของ model ใช้ตอนสร้างโต๊ะเริ่มต้น (service อ่านไปใช้)
    table_count = forms.IntegerField(min_value=1, max_value=50, required=False)
    seats_per_table = forms.IntegerField(min_value=1, max_value=12, required=False)

    # เว้นว่างได้: ตอนแก้ร้านจะคงค่าเดิม ตอนสร้างร้านใช้ค่าเริ่มต้น (30 นาที)
    no_show_grace_minutes = forms.IntegerField(
        min_value=0, max_value=MAX_NO_SHOW_GRACE_MINUTES, required=False
    )

    # ใช้ ChoiceField เพื่อกันค่าที่ไม่ได้อยู่ใน dropdown (model เป็น CharField อิสระ)
    price = forms.ChoiceField(choices=PRICE_CHOICES, required=False)

    class Meta:
        model = Restaurant
        fields = (
            "name",
            "category",
            "price",
            "address",
            "hours",
            "image",
            "description",
        )
        # ไม่ใส่ owner, slug, status, is_open, rating, reviews:
        # เจ้าของตั้งเองจากฟอร์มไม่ได้ ระบบกำหนดเอง

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("กรุณากรอกชื่อร้าน")
        return name

    def clean_image(self):
        url = self.cleaned_data.get("image", "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            raise forms.ValidationError("ลิงก์รูปต้องขึ้นต้นด้วย http:// หรือ https://")
        return url

    def clean(self):
        cleaned = super().clean()
        keys = self.data.getlist("extra_key")
        values = self.data.getlist("extra_value")
        cleaned["extras"] = [
            {"key": k.strip()[:60], "value": v.strip()[:200]}
            for k, v in zip(keys, values)
            if k.strip() and v.strip()
        ][:MAX_EXTRAS]
        return cleaned