from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from account.ui import (
    ACTIVE_UI_SESSION_KEY,
    CUSTOMER_UI,
    OWNER_UI,
    get_active_ui,
)

User = get_user_model()
PASSWORD = "Queue-pass-2026"


class LoginTests(TestCase):

    def setUp(self):
        self.login_url = reverse("login")
        self.home_url = reverse("home")
        self.owner_dashboard_url = reverse("owner_dashboard")
        self.owner_applications_admin_url = reverse("owner_applications_admin")

        self.customer = User.objects.create_user(
            username="customer-test",
            email="customer@example.com",
            password=PASSWORD,
        )

        self.owner = User.objects.create_user(
            username="owner-test",
            email="owner@example.com",
            password=PASSWORD,
            role=User.Role.OWNER,
        )

        self.admin = User.objects.create_user(
            username="admin-test",
            email="admin@example.com",
            password=PASSWORD,
            role=User.Role.ADMIN,
        )

    def login(self, email, password=PASSWORD, remember=True, next_url=None):
        data = {
            "email": email,
            "password": password,
        }

        if remember:
            data["remember"] = "on"

        if next_url is not None:
            data["next"] = next_url

        return self.client.post(self.login_url, data)

    # ---- Page rendering ----

    def test_login_page_renders(self):
        response = self.client.get(self.login_url)

        self.assertEqual(response.status_code, 200)

    # ---- Successful login by role ----

    def test_customer_login_redirects_to_home(self):
        response = self.login(self.customer.email)

        self.assertRedirects(response, self.home_url)
        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(self.customer.pk),
        )

    def test_owner_login_defaults_to_customer_ui(self):
        response = self.login(self.owner.email)

        self.assertRedirects(response, self.home_url)
        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(self.owner.pk),
        )

        # Customer UI is the default; it does not need to be stored in session.
        landing_request = self.client.get(self.home_url).wsgi_request
        self.assertEqual(get_active_ui(landing_request), CUSTOMER_UI)

    def test_owner_login_redirects_to_owner_dashboard_when_owner_ui_selected(self):
        # Preserve the selected UI across login, as expected by the current design.
        session = self.client.session
        session[ACTIVE_UI_SESSION_KEY] = OWNER_UI
        session.save()

        response = self.login(self.owner.email)

        self.assertRedirects(response, self.owner_dashboard_url)

    def test_admin_login_redirects_to_owner_applications_admin(self):
        response = self.login(self.admin.email)

        self.assertRedirects(response, self.owner_applications_admin_url)
        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(self.admin.pk),
        )

    # ---- Rejected credentials ----

    def test_login_rejects_wrong_password(self):
        response = self.login(
            self.customer.email,
            password="Wrong-password",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email or password is incorrect.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_unknown_email(self):
        response = self.login("unknown@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email or password is incorrect.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_missing_credentials(self):
        response = self.client.post(self.login_url, {
            "email": "",
            "password": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email or password is incorrect.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_inactive_user(self):
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])

        response = self.login(self.customer.email)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email or password is incorrect.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_accepts_email_with_different_letter_case(self):
        response = self.login("Customer@Example.com")

        self.assertRedirects(response, self.home_url)
        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(self.customer.pk),
        )

    # ---- Already logged in ----

    def test_logged_in_customer_is_redirected_from_login_page(self):
        self.client.force_login(self.customer)

        response = self.client.get(self.login_url)

        self.assertRedirects(response, self.home_url)

    def test_logged_in_owner_is_redirected_to_home_by_default(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.login_url)

        self.assertRedirects(response, self.home_url)

    def test_logged_in_owner_is_redirected_to_owner_dashboard_when_owner_ui_selected(self):
        self.client.force_login(self.owner)

        session = self.client.session
        session[ACTIVE_UI_SESSION_KEY] = OWNER_UI
        session.save()

        response = self.client.get(self.login_url)

        self.assertRedirects(response, self.owner_dashboard_url)

    def test_logged_in_user_with_safe_next_is_redirected_to_next(self):
        self.client.force_login(self.customer)

        response = self.client.get(f"{self.login_url}?next=/queue/")

        self.assertRedirects(
            response,
            "/queue/",
            fetch_redirect_response=False,
        )

    def test_logged_in_user_with_external_next_is_redirected_to_home(self):
        self.client.force_login(self.customer)

        response = self.client.get(
            f"{self.login_url}?next=https://evil.example.com"
        )

        self.assertRedirects(response, self.home_url)

    # ---- `next` handling on login ----

    def test_login_redirects_to_safe_next_url(self):
        response = self.login(
            self.customer.email,
            next_url="/queue/",
        )

        self.assertRedirects(
            response,
            "/queue/",
            fetch_redirect_response=False,
        )
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_rejects_external_next_url(self):
        response = self.login(
            self.customer.email,
            next_url="https://evil.example.com",
        )

        self.assertRedirects(response, self.home_url)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_rejects_protocol_relative_next_url(self):
        response = self.login(
            self.customer.email,
            next_url="//evil.example.com",
        )

        self.assertRedirects(response, self.home_url)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_page_preserves_safe_next_url(self):
        response = self.client.get(
            f"{self.login_url}?next=/queue/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["next_url"], "/queue/")

    # ---- Remember me ----

    def test_remember_me_keeps_session_after_browser_close(self):
        self.login(self.customer.email, remember=True)

        self.assertFalse(
            self.client.session.get_expire_at_browser_close()
        )

    def test_unchecked_remember_me_expires_session_at_browser_close(self):
        self.login(self.customer.email, remember=False)

        self.assertTrue(
            self.client.session.get_expire_at_browser_close()
        )