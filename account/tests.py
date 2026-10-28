from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
        self.assertContains(response, reverse('owner_signup'))
        self.assertContains(response, 'Apply for owner access')

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

    def test_old_signup_payload_cannot_grant_owner_access(self):
        response = self.client.post(
            self.url,
            self.valid_data(username='owner-one', account_type='owner'),
        )

        self.assertRedirects(response, reverse('home'))
        owner = User.objects.get(username='owner-one')
        self.assertEqual(owner.role, User.Role.USER)
        self.assertEqual(self.client.session['_auth_user_id'], str(owner.pk))

    def test_signup_ignores_role_admin_in_post(self):
        self.client.post(
            self.url,
            self.valid_data(role='admin', is_staff='on'),
        )

        user = User.objects.get(username='somchai')
        self.assertEqual(user.role, User.Role.USER)
        self.assertFalse(user.is_staff)

    def test_signup_payload_cannot_grant_approved_owner_or_superuser_access(self):
        self.client.post(self.url, self.valid_data(
            account_type='owner', role='owner', status='approved', is_superuser='on',
        ))
        user = User.objects.get(username='somchai')
        self.assertEqual(user.role, User.Role.USER)
        self.assertFalse(user.is_superuser)

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

        session = self.client.session
        session['active_ui'] = 'owner'
        session.save()

        self.assertRedirects(self.client.get(self.url), reverse('owner_dashboard'))

    def test_login_starts_accounts_in_customer_ui_unless_an_owner_ui_is_selected(self):
        owner = User.objects.create_user(
            'login-owner', 'login-owner@example.com', 'Queue-pass-2026',
            role=User.Role.OWNER,
        )
        response = self.client.post(reverse('login'), {
            'email': owner.email, 'password': 'Queue-pass-2026', 'remember': 'on',
        })
        self.assertRedirects(response, reverse('home'))

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
