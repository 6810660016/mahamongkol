import re
import time

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from django.core import mail



User = get_user_model()


class BookingFlowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            "customer-test", "customer@example.com", "Queue-pass-2026"
        )
        self.client.force_login(self.customer)

    def test_discovery_and_booking_pages_render(self):
        for url in (
            reverse('restaurants'),
            reverse('restaurant_detail', args=['salvia']),
            reverse('booking', args=['salvia']),
            reverse('my_queues'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_search_filters_restaurants(self):
        response = self.client.get(reverse('restaurants'), {'q': 'mellow'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mellow Coffee')
        self.assertNotContains(response, 'The Garden Table')

    def test_booking_appears_in_my_queue_and_can_be_cancelled(self):
        response = self.client.post(
            reverse('booking', args=['salvia']),
            {
                'date': (date.today() + timedelta(days=1)).isoformat(),
                'time': '19:00',
                'guests': '2',
            },
        )
        self.assertRedirects(response, reverse('my_queues'))
        self.assertContains(self.client.get(reverse('my_queues')), 'Salvia')

        response = self.client.post(
            reverse('cancel_booking', args=[1])
        )
        self.assertRedirects(response, reverse('my_queues'))
        self.assertContains(
            self.client.get(reverse('my_queues')),
            'Your next favourite moment',
        )

    def test_booking_rejects_invalid_time(self):
        response = self.client.post(
            reverse('booking', args=['salvia']),
            {
                'date': (date.today() + timedelta(days=1)).isoformat(),
                'time': '03:00',
                'guests': '2',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please choose a valid date')

    def test_settings_can_be_saved_in_session(self):
        response = self.client.get(reverse('settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Personal details')
        self.assertContains(response, 'aria-label="My Q"')

        response = self.client.post(
            reverse('settings'),
            {
                'name': 'Taylor Guest',
                'email': 'taylor@example.com',
                'language': 'Thai',
                'currency': 'USD',
                'time_format': '24-hour',
                'reservation_updates': 'on',
            },
        )
        self.assertContains(response, 'Your settings have been saved')
        self.assertEqual(
            self.client.session['site_settings']['name'],
            'Taylor Guest',
        )
        self.assertEqual(
            self.client.session['site_settings']['currency'],
            'USD',
        )
        self.assertFalse(
            self.client.session['site_settings']['reminders']
        )

    def test_search_bar_filters_restaurants_from_shared_navigation(self):
        response = self.client.get(
            reverse('restaurants'),
            {'q': 'mellow'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="mellow"')
        self.assertContains(response, 'Mellow Coffee')

    def test_home_navigation_shows_my_q_link(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="My Q"')
        self.assertContains(response, reverse('my_queues'))


class SignupTests(TestCase):
    url = reverse('signup')

    def valid_data(self, **overrides):
        data = {
            'username': 'somchai',
            'email': 'somchai@example.com',
            'password1': 'Queue-pass-2026',
            'password2': 'Queue-pass-2026',
            'account_type': 'customer',
        }
        data.update(overrides)
        return data

    def post_invalid(self, **overrides):
        """POST invalid data and return the bound form; no user may be created."""
        users_before = User.objects.count()
        response = self.client.post(self.url, self.valid_data(**overrides))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), users_before)
        return response.context['form']

    def test_signup_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/signup.html')
        self.assertContains(response, 'name="account_type" value="customer"')
        self.assertContains(response, 'name="account_type" value="owner"')

    def test_signup_creates_user_logs_in_and_redirects_home(self):
        response = self.client.post(
            self.url,
            self.valid_data(email='Somchai@Example.COM'),
        )

        self.assertRedirects(response, reverse('home'))
        user = User.objects.get(username='somchai')
        self.assertEqual(user.role, User.Role.USER)
        self.assertEqual(user.email, 'somchai@example.com')
        self.assertEqual(
            self.client.session['_auth_user_id'],
            str(user.pk),
        )

    def test_owner_signup_creates_owner_and_redirects_to_owner_workspace(self):
        response = self.client.post(
            self.url,
            self.valid_data(username='owner-one', account_type='owner'),
        )

        self.assertRedirects(response, reverse('owner_dashboard'))
        owner = User.objects.get(username='owner-one')
        self.assertEqual(owner.role, User.Role.OWNER)
        self.assertEqual(self.client.session['_auth_user_id'], str(owner.pk))

    def test_signup_ignores_role_admin_in_post(self):
        self.client.post(
            self.url,
            self.valid_data(role='admin', is_staff='on'),
        )

        user = User.objects.get(username='somchai')
        self.assertEqual(user.role, User.Role.USER)
        self.assertFalse(user.is_staff)

    def test_invalid_account_type_is_rejected(self):
        self.post_invalid(account_type='admin')

    def test_logged_in_user_is_redirected_home(self):
        user = User.objects.create_user(
            'existing',
            'existing@example.com',
            'Queue-pass-2026',
        )
        self.client.force_login(user)

        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('home'))

    def test_logged_in_owner_is_redirected_to_owner_workspace_from_signup(self):
        owner = User.objects.create_user(
            'existing-owner', 'existing-owner@example.com', 'Queue-pass-2026',
            role=User.Role.OWNER,
        )
        self.client.force_login(owner)

        self.assertRedirects(self.client.get(self.url), reverse('owner_dashboard'))

    def test_login_routes_each_account_type_to_its_own_ui(self):
        owner = User.objects.create_user(
            'login-owner', 'login-owner@example.com', 'Queue-pass-2026',
            role=User.Role.OWNER,
        )
        response = self.client.post(reverse('login'), {
            'email': owner.email, 'password': 'Queue-pass-2026', 'remember': 'on',
        })
        self.assertRedirects(response, reverse('owner_dashboard'))

        self.client.logout()
        customer = User.objects.create_user(
            'login-customer', 'login-customer@example.com', 'Queue-pass-2026',
        )
        response = self.client.post(reverse('login'), {
            'email': customer.email, 'password': 'Queue-pass-2026', 'remember': 'on',
        })
        self.assertRedirects(response, reverse('home'))

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(
            'somchai',
            'other@example.com',
            'Queue-pass-2026',
        )

        for username in ('somchai', 'Somchai'):
            with self.subTest(username=username):
                form = self.post_invalid(username=username)
                self.assertEqual(
                    form.errors['username'],
                    ['ชื่อผู้ใช้นี้ถูกใช้แล้ว'],
                )

    def test_duplicate_email_is_rejected_case_insensitive(self):
        User.objects.create_user(
            'other',
            'somchai@example.com',
            'Queue-pass-2026',
        )

        for email in ('somchai@example.com', 'SomChai@Example.com'):
            with self.subTest(email=email):
                form = self.post_invalid(email=email)
                self.assertEqual(
                    form.errors['email'],
                    ['อีเมลนี้ถูกใช้สมัครแล้ว'],
                )

    def test_invalid_email_is_rejected(self):
        form = self.post_invalid(email='not-an-email')
        self.assertEqual(
            form.errors['email'],
            ['รูปแบบอีเมลไม่ถูกต้อง'],
        )

    def test_password_mismatch_is_rejected(self):
        form = self.post_invalid(password2='Other-pass-2026')
        self.assertEqual(
            form.errors['password2'],
            ['รหัสผ่านทั้งสองช่องไม่ตรงกัน'],
        )

    def test_weak_password_is_rejected(self):
        form = self.post_invalid(
            password1='1234',
            password2='1234',
        )
        self.assertIn(
            'รหัสผ่านสั้นเกินไป ต้องมีอย่างน้อย 8 ตัวอักษร',
            form.errors['password2'],
        )

    def test_missing_email_is_rejected(self):
        form = self.post_invalid(email='')
        self.assertEqual(
            form.errors['email'],
            ['กรุณากรอกอีเมล'],
        )


class LogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='logout-user',
            email='logout@example.com',
            password='Queue-pass-2026',
        )
        self.client.force_login(self.user)

    def test_settings_displays_sign_out_action(self):
        response = self.client.get(reverse('settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'End your current session on this device.')
        self.assertContains(response, reverse('logout'))

    def test_logout_post_clears_session_and_redirects_to_welcome(self):
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('welcome'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_rejects_get_requests(self):
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)


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