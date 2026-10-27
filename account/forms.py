from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import User

# ข้อความ error ของ password validator เป็นภาษาไทย (Django ยังไม่มีคำแปลไทยให้)
PASSWORD_ERROR_MESSAGES = {
    "password_too_short": "รหัสผ่านสั้นเกินไป ต้องมีอย่างน้อย %(min_length)d ตัวอักษร",
    "password_too_common": "รหัสผ่านนี้ง่ายเกินไป กรุณาตั้งรหัสผ่านที่เดายากกว่านี้",
    "password_entirely_numeric": "รหัสผ่านต้องไม่เป็นตัวเลขทั้งหมด",
    "password_too_similar": "รหัสผ่านคล้ายกับ%(verbose_name)sมากเกินไป",
}


class SignupForm(UserCreationForm):
    error_messages = {
        "password_mismatch": "รหัสผ่านทั้งสองช่องไม่ตรงกัน",
    }

    email = forms.EmailField(
        label="อีเมล",
        error_messages={
            "required": "กรุณากรอกอีเมล",
            "invalid": "รูปแบบอีเมลไม่ถูกต้อง",
        },
    )
    account_type = forms.ChoiceField(
        choices=(("customer", "Customer"), ("owner", "Store owner")),
        error_messages={"required": "กรุณาเลือกประเภทบัญชี"},
    )

    class Meta:
        model = User
        # รับเฉพาะประเภทบัญชีสำหรับสมัครสาธารณะ ไม่รับ role/admin privilege จาก client
        fields = ("username", "email")
        labels = {
            "username": "ชื่อผู้ใช้",
        }
        error_messages = {
            "username": {
                "required": "กรุณากรอกชื่อผู้ใช้",
                "unique": "ชื่อผู้ใช้นี้ถูกใช้แล้ว",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "รหัสผ่าน"
        self.fields["password2"].label = "ยืนยันรหัสผ่าน"
        self.fields["password1"].error_messages["required"] = "กรุณากรอกรหัสผ่าน"
        self.fields["password2"].error_messages["required"] = "กรุณายืนยันรหัสผ่าน"

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username and User.objects.filter(username__iexact=username).exists():
            raise ValidationError("ชื่อผู้ใช้นี้ถูกใช้แล้ว", code="unique")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("อีเมลนี้ถูกใช้สมัครแล้ว", code="unique")
        return email

    def validate_password_for_user(self, user, password_field_name="password2"):
        password = self.cleaned_data.get(password_field_name)
        if not password:
            return
        try:
            password_validation.validate_password(password, user)
        except ValidationError as error:
            self.add_error(
                password_field_name,
                [self._to_thai_password_error(e) for e in error.error_list],
            )

    @staticmethod
    def _to_thai_password_error(error):
        message = PASSWORD_ERROR_MESSAGES.get(error.code)
        if message is None:
            return error
        return ValidationError(message, code=error.code, params=error.params)

    def save(self, commit=True):
        user = super().save(commit=False)
        # สมัครผ่านหน้าเว็บได้เฉพาะลูกค้าเท่านั้น
        user.role = (
            User.Role.OWNER
            if self.cleaned_data.get("account_type") == "owner"
            else User.Role.USER
        )
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user
