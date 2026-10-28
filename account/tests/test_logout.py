from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

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