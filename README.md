# mahamongkol

ระบบจองคิว (Django)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
```

## ตั้งค่าอีเมล (.env)

ระบบลืมรหัสผ่านส่ง OTP ทางอีเมลผ่าน Gmail SMTP รหัสผ่านอีเมลเก็บในไฟล์ `.env` ห้ามใส่ในโค้ด

| ไฟล์ | มีอะไร | ขึ้น git |
|---|---|---|
| `.env.example` | แม่แบบ มีแค่ชื่อตัวแปร ไม่มีรหัส | ✅ |
| `.env` | ค่าจริงของแต่ละคน สร้างเองในเครื่อง Django อ่านไฟล์นี้ตอนเริ่ม server | ❌ (อยู่ใน `.gitignore`) |

1. สร้าง `.env` จากแม่แบบ

   ```bash
   cp .env.example .env
   ```

2. ใส่ App Password ของ Gmail หลัง `EMAIL_HOST_PASSWORD=` (ไม่ต้องใส่เครื่องหมายคำพูด)
3. รัน `python manage.py runserver` ใหม่

### App Password มาจากไหน

- **บัญชีทีม `mongkolq.official@gmail.com`**: ขอจากเจ้าของบัญชีทาง DM เจ้าของบัญชีสร้าง App Password แยกให้แต่ละคนได้ (https://myaccount.google.com/apppasswords) ถ้ารหัสของใครหลุด ยกเลิกแค่อันนั้น
- **Gmail ของตัวเอง**: เปิด 2-Step Verification แล้วสร้าง App Password เอง จากนั้นแก้ `EMAIL_HOST_USER` ใน `.env` เป็นอีเมลตัวเอง

### ยังไม่มีรหัส

ลบ `#` หน้าบรรทัด `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` ใน `.env` อีเมล (รวมถึง OTP) จะแสดงใน terminal ที่รัน `runserver` แทนการส่งจริง ถ้าไม่ใส่ทั้งรหัสและบรรทัดนี้ หน้าลืมรหัสผ่านจะขึ้นว่า "ส่งอีเมลไม่สำเร็จ"

### ข้อควรระวัง

- ห้ามใส่รหัสจริงใน `.env.example`, `settings.py`, PR, issue หรือแชตกลุ่ม
- ห้าม `git add -f .env`
- `python manage.py test` ไม่ส่งอีเมลจริง ไม่ต้องตั้งค่าอะไร

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
