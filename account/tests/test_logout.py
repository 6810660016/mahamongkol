import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from account.ui import ACTIVE_UI_SESSION_KEY, OWNER_UI

User = get_user_model()
PASSWORD = "Queue-pass-2026"


class LogoutTests(TestCase):

    def setUp(self):
        self.logout_url = reverse("logout")
        self.welcome_url = reverse("welcome")
        self.login_url = reverse("login")
        self.settings_url = reverse("settings")

        self.user = User.objects.create_user(
            username="logout-user",
            email="logout@example.com",
            password=PASSWORD,
        )
        self.client.force_login(self.user)

    def test_settings_page_has_sign_out_form(self):
        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.logout_url)

    def test_logout_post_clears_session_and_redirects_to_welcome(self):
        response = self.client.post(self.logout_url)

        self.assertRedirects(response, self.welcome_url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_revokes_access_to_protected_pages(self):
        self.client.post(self.logout_url)

        response = self.client.get(self.settings_url)

        self.assertRedirects(
            response,
            f"{self.login_url}?next={self.settings_url}",
        )

    def test_logout_rejects_get_requests(self):
        response = self.client.get(self.logout_url)

        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_clears_active_ui(self):
        session = self.client.session
        session[ACTIVE_UI_SESSION_KEY] = OWNER_UI
        session.save()

        self.client.post(self.logout_url)

        self.assertNotIn(ACTIVE_UI_SESSION_KEY, self.client.session)

    def test_logout_requires_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post(self.logout_url)

        self.assertEqual(response.status_code, 403)
        self.assertIn("_auth_user_id", client.session)

    def test_logout_succeeds_with_valid_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)

        page = client.get(self.settings_url)
        token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            page.content.decode(),
        ).group(1)

        response = client.post(self.logout_url, {"csrfmiddlewaretoken": token})

        self.assertRedirects(response, self.welcome_url)
        self.assertNotIn("_auth_user_id", client.session)