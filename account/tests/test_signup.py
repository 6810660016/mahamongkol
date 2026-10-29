from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

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

