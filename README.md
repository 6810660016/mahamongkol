# mahamongkol

ระบบจองโต๊ะและคิวร้านอาหาร (Django) ลูกค้าค้นหาร้าน จองโต๊ะ หรือเข้าคิวเองและดูตำแหน่งคิวสด เจ้าของร้านจัดการร้าน การจอง และคิววันนี้ แอดมินตรวจใบสมัครเจ้าของร้าน

## เอกสาร

- [Architecture (C4 Context/Container/Component) และ ERD](docs/architecture.md)
- [CI และ test coverage](docs/ci-and-coverage.md)

## โครงสร้างแอป

| แอป | หน้าที่ |
|---|---|
| `account` | ผู้ใช้ บทบาท (user/owner/admin) ล็อกอิน รีเซ็ตรหัสผ่านด้วย OTP ใบสมัครเจ้าของร้าน |
| `restaurants` | ร้านและโต๊ะ ค้นหาร้าน โหมดบริการของร้าน (จอง/คิว/ทั้งสอง) |
| `bookings` | จองโต๊ะ ยกเลิก จองเสร็จสิ้น no-show อัตโนมัติ ประวัติการจอง |
| `queues` | คิว walk-in และคิวออนไลน์ เรียกคิว ข้าม เรียกคืน ตำแหน่งคิวสด |
| `dashboard` | หน้าฝั่ง Owner: ร้าน การจอง คิว |


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
- Owner Studio บันทึกร้าน การจอง และคิวลงฐานข้อมูลจริง (ส่วนรีวิวร้านยังเป็น mockup)
- เจ้าของร้านเลือกโหมดบริการของร้านได้ 3 แบบ: รับจองอย่างเดียว รับคิวอย่างเดียว หรือทั้งสองแบบ (ตั้งตอนเพิ่มหรือแก้ร้าน)

หลังดึงโค้ดให้รัน `python manage.py migrate` เพื่อสร้างตารางใบสมัคร

## รันเทส

CI และการวัด coverage (ต้องผ่านอย่างน้อย 80%):
ดู [CI and test coverage](docs/ci-and-coverage.md) สำหรับ Python 3.13,
คำสั่งตรวจ Ruff/coverage และวิธีตั้ง required status check บน `main` โดย admin

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m coverage run manage.py test --noinput --settings=MongkolQ.test_settings
python -m coverage report --fail-under=80
```

```bash
python manage.py test
```

บน Windows ภาษาไทย ถ้าเจอ `UnicodeDecodeError` ตอนรันเทส ให้ตั้ง `$env:PYTHONUTF8 = "1"` (PowerShell) ก่อนรัน

ลำดับ `python manage.py migrate` ต้องรันหลังดึงโค้ดทุกครั้ง เพราะมี migration ใหม่ของ `restaurants`, `bookings` และ `queues`

## Mark no-show (งานตามเวลา)

```bash
python manage.py mark_no_shows
```

ตั้งให้รันเป็นระยะ (เช่น cron) เพื่อเปลี่ยนการจองที่เลยเวลาเกินช่วงผ่อนผันเป็น no-show
