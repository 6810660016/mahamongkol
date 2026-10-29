import re
import time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from django.core import mail

User = get_user_model()

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-user",
            email="reset@example.com",
            password="Queue-pass-2026",
        )
        self.request_url = reverse("password_reset")
        self.verify_url = reverse("password_reset_verify")
        self.new_password_url = reverse("password_reset_new")

    def request_otp(self, email=None):
        return self.client.post(
            self.request_url,
            {"email": email or self.user.email},
        )

    def get_otp_from_email(self):
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group()

    def test_password_reset_page_renders(self):
        response = self.client.get(self.request_url)
        self.assertEqual(response.status_code, 200)

    def test_valid_email_sends_otp_and_redirects_to_verify(self):
        response = self.request_otp()

        self.assertRedirects(response, self.verify_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

        session = self.client.session
        self.assertTrue(session["password_reset_otp_hash"])
        self.assertNotIn(
            self.get_otp_from_email(),
            session["password_reset_otp_hash"],
        )

    def test_unknown_email_does_not_send_email(self):
        response = self.request_otp("unknown@example.com")

        self.assertRedirects(response, self.verify_url)
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_otp_increments_attempts(self):
        self.request_otp()

        response = self.client.post(
            self.verify_url,
            {"otp": "000000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session["password_reset_otp_attempts"],
            1,
        )

    def test_correct_otp_grants_temporary_reset_access(self):
        self.request_otp()
        otp = self.get_otp_from_email()

        response = self.client.post(
            self.verify_url,
            {"otp": otp},
        )

        self.assertRedirects(response, self.new_password_url)
        self.assertGreater(
            self.client.session["password_reset_verified_until"],
            int(time.time()),
        )

    def test_expired_otp_is_rejected(self):
        self.request_otp()

        session = self.client.session
        session["password_reset_otp_expires"] = int(time.time()) - 1
        session.save()

        response = self.client.post(
            self.verify_url,
            {"otp": self.get_otp_from_email()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "หมดอายุ")

    def test_five_wrong_attempts_prevent_further_attempts(self):
        self.request_otp()

        session = self.client.session
        session["password_reset_otp_attempts"] = 5
        session.save()

        response = self.client.post(
            self.verify_url,
            {"otp": "000000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "หลายครั้ง")
        self.assertEqual(
            self.client.session["password_reset_otp_attempts"],
            5,
        )

    def test_new_password_page_requires_otp_verification(self):
        response = self.client.get(self.new_password_url)

        self.assertRedirects(response, self.request_url)

    def test_reset_access_expires(self):
        self.request_otp()

        session = self.client.session
        session["password_reset_verified_until"] = int(time.time()) - 1
        session.save()

        response = self.client.get(self.new_password_url)

        self.assertRedirects(response, self.request_url)
        self.assertNotIn(
            "password_reset_email",
            self.client.session,
        )

    def test_resend_is_rate_limited(self):
        self.request_otp()

        response = self.client.post(
            self.verify_url,
            {"action": "resend"},
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(response, "รอสักครู่")

    def test_user_can_reset_password_after_otp_verification(self):
        self.request_otp()
        otp = self.get_otp_from_email()

        self.client.post(
            self.verify_url,
            {"otp": otp},
        )

        response = self.client.post(
            self.new_password_url,
            {
                "new_password1": "New-Queue-pass-2026",
                "new_password2": "New-Queue-pass-2026",
            },
        )

        self.assertRedirects(response, reverse("login"))

        self.user.refresh_from_db()
        self.assertTrue(
            self.user.check_password("New-Queue-pass-2026")
        )