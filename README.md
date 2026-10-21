# mahamongkol

ระบบจองคิว (Django)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
```

## รันโปรเจกต์

```bash
python manage.py runserver
```

เปิด http://127.0.0.1:8000/

## สร้าง superuser (เข้าหน้า admin)

```bash
python manage.py createsuperuser
```

จากนั้นเข้า http://127.0.0.1:8000/admin/

- ลูกค้า (role `user`) สมัครผ่านหน้า signup
- พนักงาน (role `admin`) สร้างผ่านหน้า Django admin เท่านั้น
  เมื่อตั้ง role เป็น admin ระบบจะตั้ง `is_staff = True` ให้อัตโนมัติ

## รันเทส

```bash
python manage.py test
```
