from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from ..models import OwnerApplication

User = get_user_model()


class OwnerApplicationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user("applicant", "applicant@example.com", "Queue-pass-2026")
        cls.admin = User.objects.create_user("reviewer", "reviewer@example.com", "Queue-pass-2026", role=User.Role.ADMIN, is_staff=True)
        cls.legacy_owner = User.objects.create_user("legacy", "legacy@example.com", "Queue-pass-2026", role=User.Role.OWNER)

    def application_data(self):
        return {"contact_name": "Alex Member", "business_name": "Garden Kitchen"}

    def create_pending(self, user=None):
        return OwnerApplication.objects.create(user=user or self.customer, **self.application_data())

    def test_anonymous_owner_signup_creates_one_customer_account_pending_review(self):
        before = User.objects.count()
        response = self.client.post(reverse("owner_signup"), {
            "username": "new-owner", "email": "New-Owner@Example.com",
            "password1": "Queue-pass-2026", "password2": "Queue-pass-2026",
            **self.application_data(), "role": "owner", "status": "approved",
            "is_staff": "on", "reviewed_by": self.admin.pk,
        })
        self.assertRedirects(response, reverse("owner_application_status"))
        self.assertEqual(User.objects.count(), before + 1)
        user = User.objects.get(username="new-owner")
        self.assertEqual(user.email, "new-owner@example.com")
        self.assertEqual(user.role, User.Role.USER)
        self.assertFalse(user.is_owner_role)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.owner_application.status, OwnerApplication.Status.PENDING)
        self.assertIsNone(user.owner_application.reviewed_by)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertContains(self.client.get(reverse("home")), "Application pending")

    def test_existing_customer_applies_without_creating_a_second_account(self):
        self.client.force_login(self.customer)
        before = User.objects.count()
        response = self.client.post(reverse("owner_signup"), {
            **self.application_data(), "user": self.admin.pk,
        })
        self.assertRedirects(response, reverse("owner_application_status"))
        self.assertEqual(User.objects.count(), before)
        self.assertEqual(OwnerApplication.objects.get().user_id, self.customer.pk)
        self.client.post(reverse("owner_signup"), self.application_data())
        self.assertEqual(OwnerApplication.objects.count(), 1)

    def test_missing_business_details_does_not_create_an_account(self):
        response = self.client.post(reverse("owner_signup"), {
            "username": "incomplete", "email": "incomplete@example.com",
            "password1": "Queue-pass-2026", "password2": "Queue-pass-2026",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="incomplete").exists())
        self.assertEqual(OwnerApplication.objects.count(), 0)

    def test_pending_applicant_cannot_enter_or_switch_to_owner_or_approve(self):
        application = self.create_pending()
        self.client.force_login(self.customer)
        session = self.client.session
        session["active_ui"] = "owner"
        session.save()
        self.assertRedirects(self.client.get(reverse("welcome")), reverse("home"))
        self.assertRedirects(self.client.get(reverse("owner_dashboard")), reverse("owner_application_status"))
        self.assertEqual(self.client.post(reverse("switch_ui"), {"interface": "owner"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("owner_applications_admin")).status_code, 403)
        self.assertEqual(self.client.post(reverse("approve_owner_application", args=[application.pk])).status_code, 403)
        application.refresh_from_db()
        self.assertEqual(application.status, OwnerApplication.Status.PENDING)

    def test_admin_approval_grants_owner_in_addition_to_customer_and_is_audited(self):
        application = self.create_pending()
        self.client.force_login(self.admin)
        url = reverse("approve_owner_application", args=[application.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse("owner_applications_admin"))
        application.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(application.status, OwnerApplication.Status.APPROVED)
        self.assertEqual(application.reviewed_by_id, self.admin.pk)
        self.assertIsNotNone(application.reviewed_at)
        self.assertTrue(self.customer.is_owner_role)
        self.assertTrue(self.customer.is_user_role)
        self.assertFalse(self.customer.is_staff)
        reviewed_at = application.reviewed_at
        self.client.post(url)
        application.refresh_from_db()
        self.assertEqual(application.reviewed_at, reviewed_at)

    def test_approved_owner_switches_both_ways_without_losing_customer_bookings(self):
        OwnerApplication.objects.create(user=self.legacy_owner, status="approved", **self.application_data())
        self.client.force_login(self.legacy_owner)
        session = self.client.session
        session["bookings"] = [{"id": 4, "restaurant": "Existing booking"}]
        session.save()
        self.assertRedirects(self.client.post(reverse("switch_ui"), {"interface": "owner"}), reverse("owner_dashboard"))
        self.assertEqual(self.client.session["active_ui"], "owner")
        self.assertRedirects(self.client.get(reverse("welcome")), reverse("owner_dashboard"))
        self.assertRedirects(self.client.post(reverse("switch_ui"), {"interface": "customer"}), reverse("home"))
        self.assertEqual(self.client.session["active_ui"], "customer")
        self.assertEqual(self.client.session["bookings"][0]["id"], 4)
        self.assertContains(self.client.get(reverse("home")), "Switch to Owner Studio")
        self.assertContains(self.client.get(reverse("owner_dashboard")), "Switch to customer")

    def test_legacy_owners_keep_access_without_a_new_application(self):
        self.assertTrue(self.legacy_owner.is_owner_role)
        self.assertTrue(self.legacy_owner.is_user_role)
        self.assertFalse(OwnerApplication.objects.filter(user=self.legacy_owner).exists())
        self.client.force_login(self.legacy_owner)
        self.assertEqual(self.client.get(reverse("owner_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_role_flag_alone_cannot_bypass_pending_application(self):
        self.create_pending(self.legacy_owner)
        self.legacy_owner.refresh_from_db()
        self.assertFalse(self.legacy_owner.is_owner_role)
        self.client.force_login(self.legacy_owner)
        self.assertRedirects(self.client.get(reverse("owner_dashboard")), reverse("owner_application_status"))

    def test_staff_without_admin_role_cannot_review(self):
        self.customer.is_staff = True
        self.customer.save()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("owner_applications_admin")).status_code, 403)

    def test_admin_list_filters_and_searches_applications(self):
        self.create_pending()
        OwnerApplication.objects.create(user=self.legacy_owner, status="approved", contact_name="Approved Person", business_name="Approved Business")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("owner_applications_admin"))
        self.assertContains(response, "Garden Kitchen")
        self.assertNotContains(response, "Approved Business")
        self.assertContains(self.client.get(reverse("owner_applications_admin"), {"status": "approved"}), "Approved Business")
        self.assertNotContains(self.client.get(reverse("owner_applications_admin"), {"q": "not-a-match"}), "Garden Kitchen")

    def test_approval_requires_csrf_and_switch_endpoint_rejects_invalid_targets(self):
        application = self.create_pending()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse("approve_owner_application", args=[application.pk])).status_code, 403)
        self.client.force_login(self.legacy_owner)
        self.assertEqual(self.client.get(reverse("switch_ui")).status_code, 405)
        self.assertEqual(self.client.post(reverse("switch_ui"), {"interface": "https://other.example"}).status_code, 400)

    def test_application_status_is_scoped_to_signed_in_account(self):
        self.create_pending()
        self.client.force_login(self.legacy_owner)
        response = self.client.get(reverse("owner_application_status"))
        self.assertContains(response, "Approved")
        self.assertNotContains(response, "Garden Kitchen")

    def test_existing_member_can_sign_in_then_apply_and_next_cannot_redirect_offsite(self):
        response = self.client.post(reverse("login"), {
            "email": self.customer.email, "password": "Queue-pass-2026",
            "next": reverse("owner_signup"),
        })
        self.assertRedirects(response, reverse("owner_signup"))
        self.client.logout()
        response = self.client.post(reverse("login"), {
            "email": self.customer.email, "password": "Queue-pass-2026",
            "next": "https://untrusted.example/",
        })
        self.assertRedirects(response, reverse("home"))
