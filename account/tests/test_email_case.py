from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class EmailCaseTests(TestCase):
    def test_email_is_stored_lowercase_outside_signup(self):
        user = User.objects.create_user(
            'somchai', 'Somchai@Example.COM', 'Queue-pass-2026',
        )
        admin = User.objects.create_superuser(
            'boss', 'Boss@Example.com', 'Queue-pass-2026',
        )
        self.assertEqual(user.email, 'somchai@example.com')
        self.assertEqual(admin.email, 'boss@example.com')

    def test_email_differing_only_in_case_cannot_be_saved(self):
        User.objects.create_user(
            'somchai', 'somchai@example.com', 'Queue-pass-2026',
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([
                User(username='other', email='SOMCHAI@example.com'),
            ])

    def test_admin_add_user_rejects_email_differing_only_in_case(self):
        User.objects.create_user(
            'somchai', 'somchai@example.com', 'Queue-pass-2026',
        )
        admin = User.objects.create_superuser(
            'boss', 'boss@example.com', 'Queue-pass-2026',
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse('admin:account_user_add'),
            {
                'username': 'other',
                'email': 'Somchai@example.com',
                'role': User.Role.USER,
                'usable_password': 'true',
                'password1': 'Queue-pass-2026',
                'password2': 'Queue-pass-2026',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A user with that email already exists.')
        self.assertFalse(User.objects.filter(username='other').exists())

    def test_login_with_differently_cased_email(self):
        user = User.objects.create_user(
            'somchai', 'somchai@example.com', 'Queue-pass-2026',
        )

        response = self.client.post(
            reverse('login'),
            {'email': 'SomChai@Example.com', 'password': 'Queue-pass-2026'},
        )

        self.assertRedirects(response, reverse('home'))
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))
