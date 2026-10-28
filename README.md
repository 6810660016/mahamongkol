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

- หน้าแรก (welcome): http://127.0.0.1:8000/
- หน้า home: http://127.0.0.1:8000/home/
- หน้า login: http://127.0.0.1:8000/login/

## สร้าง superuser (เข้าหน้า admin)

```bash
python manage.py createsuperuser
```

จากนั้นเข้า http://127.0.0.1:8000/admin/

- ลูกค้า (role `user`) สมัครผ่านหน้า signup
- พนักงาน (role `admin`) สร้างผ่านหน้า Django admin เท่านั้น
  เมื่อตั้ง role เป็น admin ระบบจะตั้ง `is_staff = True` ให้อัตโนมัติ

## Customer และ Owner ในบัญชีเดียว

- ทุกบัญชีทั่วไปใช้ฝั่ง Customer ได้ สมาชิกสมัครขอสิทธิ์ Owner เพิ่มได้ที่ `/signup/owner/`
- ผู้สมัครใหม่สร้างบัญชีและใบสมัครในครั้งเดียว ใช้ข้อมูลบัญชี ชื่อผู้ติดต่อ และชื่อธุรกิจ
- ระหว่างรออนุมัติยังใช้ฝั่ง Customer ได้ ตรวจสถานะได้ที่ `/owner/application/`
- Admin (role `admin`) หรือ superuser ล็อกอินผ่าน `/login/` เพื่อเข้าหน้าตรวจใบสมัคร `/staff/owner-applications/`
- การอนุมัติบันทึกผู้อนุมัติและเวลา และเพิ่มสิทธิ์ Owner ให้บัญชีเดิมโดยคงสิทธิ์ Customer ไว้
- เมื่ออนุมัติแล้วใช้ปุ่ม `Owner Studio` ใน navbar ฝั่งลูกค้า และ `Switch to customer` ในฝั่งร้าน
- บัญชี Owner เดิมยังคงสิทธิ์ไว้ โดยไม่ต้องสมัครใหม่
- หน้าจัดการร้าน Owner Studio ยังเป็น **mockup**: ร้านตัวอย่างและการแก้ไขอยู่ในหน่วยความจำของหน้าเว็บ รีเฟรชแล้วรีเซ็ต ส่วนใบสมัครและการอนุมัติบันทึกลงฐานข้อมูลจริง

หลังดึงโค้ดให้รัน `python manage.py migrate` เพื่อสร้างตารางใบสมัคร

## รันเทส

```bash
python manage.py test
```
