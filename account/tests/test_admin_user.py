from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserAdminRoleTests(TestCase):
    """Staff-role accounts must be able to sign in to the Django admin."""

    def setUp(self):
        self.boss = User.objects.create_superuser(
            'boss', 'boss@example.com', 'Queue-pass-2026',
        )
        self.client.force_login(self.boss)

    def add_user(self, username, role):
        return self.client.post(
            reverse('admin:account_user_add'),
            {
                'username': username,
                'email': f'{username}@example.com',
                'role': role,
                'usable_password': 'true',
                'password1': 'Queue-pass-2026',
                'password2': 'Queue-pass-2026',
            },
        )

    def change_role(self, user, role):
        return self.client.post(
            reverse('admin:account_user_change', args=[user.pk]),
            {
                'username': user.username,
                'email': user.email,
                'role': role,
                'is_active': 'on',
                'date_joined_0': user.date_joined.strftime('%Y-%m-%d'),
                'date_joined_1': user.date_joined.strftime('%H:%M:%S'),
            },
        )

    def test_adding_admin_role_user_grants_staff_access(self):
        response = self.add_user('clerk', User.Role.ADMIN)
        self.assertEqual(response.status_code, 302)
        clerk = User.objects.get(username='clerk')
        self.assertEqual(clerk.role, User.Role.ADMIN)
        self.assertTrue(clerk.is_staff)
        self.assertFalse(clerk.is_superuser)

    def test_changing_a_user_to_admin_role_grants_staff_access(self):
        user = User.objects.create_user(
            'somchai', 'somchai@example.com', 'Queue-pass-2026',
        )
        self.assertFalse(user.is_staff)
        response = self.change_role(user, User.Role.ADMIN)
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)

    def test_customer_and_owner_roles_do_not_get_staff_access(self):
        for role in (User.Role.USER, User.Role.OWNER):
            with self.subTest(role=role):
                response = self.add_user(f'person-{role}', role)
                self.assertEqual(response.status_code, 302)
                person = User.objects.get(username=f'person-{role}')
                self.assertEqual(person.role, role)
                self.assertFalse(person.is_staff)

    def test_changing_to_a_non_admin_role_does_not_grant_staff_access(self):
        user = User.objects.create_user(
            'somchai', 'somchai@example.com', 'Queue-pass-2026',
        )
        response = self.change_role(user, User.Role.OWNER)
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.OWNER)
        self.assertFalse(user.is_staff)
