from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from ..models import OwnerApplication

User = get_user_model()


class OwnerRejectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.applicant = User.objects.create_user("applicant", "applicant@example.com", "Queue-pass-2026")
        cls.admin = User.objects.create_user(
            "reviewer", "reviewer@example.com", "Queue-pass-2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        cls.other = User.objects.create_user("bystander", "bystander@example.com", "Queue-pass-2026")

    def setUp(self):
        self.application = OwnerApplication.objects.create(
            user=self.applicant, contact_name="Alex Member", business_name="Garden Kitchen",
        )
        self.reject_url = reverse("reject_owner_application", args=[self.application.pk])

    def reject(self, reason=""):
        self.client.force_login(self.admin)
        return self.client.post(self.reject_url, {"reason": reason})

    # ----- admin side

    def test_admin_rejects_a_pending_application_and_it_is_audited(self):
        response = self.reject("Please add a business address.")
        self.assertRedirects(response, reverse("owner_applications_admin"))
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, OwnerApplication.Status.REJECTED)
        self.assertEqual(self.application.rejection_reason, "Please add a business address.")
        self.assertEqual(self.application.reviewed_by, self.admin)
        self.assertIsNotNone(self.application.reviewed_at)

    def test_rejection_does_not_grant_owner_access(self):
        self.reject()
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.role, User.Role.USER)
        self.assertFalse(self.applicant.is_owner_role)
        self.client.force_login(self.applicant)
        self.assertRedirects(
            self.client.get(reverse("owner_dashboard")), reverse("owner_application_status")
        )
        response = self.client.post(reverse("switch_ui"), {"interface": "owner"})
        self.assertEqual(response.status_code, 403)

    def test_reason_is_optional_and_trimmed_to_the_column_size(self):
        self.reject("   ")
        self.application.refresh_from_db()
        self.assertEqual(self.application.rejection_reason, "")

        other_app = OwnerApplication.objects.create(
            user=self.other, contact_name="B", business_name="Bistro",
        )
        self.client.post(
            reverse("reject_owner_application", args=[other_app.pk]), {"reason": "x" * 500},
        )
        other_app.refresh_from_db()
        self.assertEqual(len(other_app.rejection_reason), 300)

    def test_an_approved_application_cannot_be_rejected(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("approve_owner_application", args=[self.application.pk]))
        response = self.client.post(self.reject_url, {"reason": "too late"}, follow=True)
        self.assertContains(response, "already approved")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, OwnerApplication.Status.APPROVED)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_owner_role)

    def test_rejecting_twice_changes_nothing(self):
        self.reject("first")
        self.application.refresh_from_db()
        reviewed_at = self.application.reviewed_at
        response = self.client.post(self.reject_url, {"reason": "second"}, follow=True)
        self.assertContains(response, "already been rejected")
        self.application.refresh_from_db()
        self.assertEqual(self.application.rejection_reason, "first")
        self.assertEqual(self.application.reviewed_at, reviewed_at)

    def test_only_admins_can_reject_and_it_must_be_a_post(self):
        for user in (self.applicant, self.other):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.reject_url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.reject_url).status_code, 302)

        staff_only = User.objects.create_user(
            "staffer", "staffer@example.com", "Queue-pass-2026", is_staff=True,
        )
        self.client.force_login(staff_only)
        self.assertEqual(self.client.post(self.reject_url).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.reject_url).status_code, 405)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, OwnerApplication.Status.PENDING)

    def test_reject_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.reject_url).status_code, 403)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, OwnerApplication.Status.PENDING)

    def test_unknown_application_is_404(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("reject_owner_application", args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_admin_page_shows_buttons_counts_and_rejected_tab(self):
        self.client.force_login(self.admin)
        pending_page = self.client.get(reverse("owner_applications_admin"))
        self.assertContains(pending_page, "Garden Kitchen")
        self.assertContains(pending_page, self.reject_url)
        self.assertContains(pending_page, reverse("approve_owner_application", args=[self.application.pk]))

        self.reject("Not enough detail")
        pending_page = self.client.get(reverse("owner_applications_admin"))
        self.assertEqual(list(pending_page.context["applications"]), [])
        self.assertEqual(pending_page.context["pending_count"], 0)
        self.assertEqual(pending_page.context["rejected_count"], 1)

        rejected_page = self.client.get(reverse("owner_applications_admin"), {"status": "rejected"})
        self.assertContains(rejected_page, "Garden Kitchen")
        self.assertContains(rejected_page, "Not enough detail")
        self.assertNotContains(rejected_page, self.reject_url)

        all_page = self.client.get(reverse("owner_applications_admin"), {"status": "all"})
        self.assertContains(all_page, "Garden Kitchen")

    def test_reason_is_escaped_in_the_admin_page(self):
        self.reject("<script>alert(1)</script>")
        page = self.client.get(reverse("owner_applications_admin"), {"status": "rejected"})
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;")

    # ----- applicant side

    def test_applicant_sees_the_rejection_and_the_reason(self):
        self.reject("Please add a business address.")
        self.client.force_login(self.applicant)
        response = self.client.get(reverse("owner_application_status"))
        self.assertContains(response, "Not approved")
        self.assertContains(response, "Please add a business address.")
        self.assertContains(response, reverse("owner_signup"))
        self.assertNotContains(response, "Awaiting admin approval")

    def test_navigation_points_a_rejected_applicant_to_the_update(self):
        self.reject()
        self.client.force_login(self.applicant)
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Application update")
        self.assertNotContains(home, "Application pending")

    def test_rejected_applicant_can_apply_again_and_goes_back_to_pending(self):
        self.reject("Please add a business address.")
        self.client.force_login(self.applicant)

        form_page = self.client.get(reverse("owner_signup"))
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, "previous application wasn")
        self.assertContains(form_page, "Please add a business address.")
        self.assertContains(form_page, "Garden Kitchen")  # prefilled

        response = self.client.post(reverse("owner_signup"), {
            "contact_name": "Alex Member", "business_name": "Garden Kitchen Bangkok",
        })
        self.assertRedirects(response, reverse("owner_application_status"))
        self.assertEqual(OwnerApplication.objects.filter(user=self.applicant).count(), 1)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, OwnerApplication.Status.PENDING)
        self.assertEqual(self.application.business_name, "Garden Kitchen Bangkok")
        self.assertEqual(self.application.rejection_reason, "")
        self.assertIsNone(self.application.reviewed_by)
        self.assertIsNone(self.application.reviewed_at)
        self.assertContains(self.client.get(reverse("home")), "Application pending")

        # The reopened request shows up for review again and can be approved.
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("owner_applications_admin")), "Garden Kitchen Bangkok")
        self.client.post(reverse("approve_owner_application", args=[self.application.pk]))
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_owner_role)

    def test_invalid_reapplication_keeps_the_rejection(self):
        self.reject("Please add a business address.")
        self.client.force_login(self.applicant)
        response = self.client.post(reverse("owner_signup"), {"contact_name": "", "business_name": ""})
        self.assertEqual(response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, OwnerApplication.Status.REJECTED)
        self.assertEqual(self.application.business_name, "Garden Kitchen")

    def test_pending_applicant_is_still_sent_to_the_status_page(self):
        self.client.force_login(self.applicant)
        self.assertRedirects(
            self.client.get(reverse("owner_signup")), reverse("owner_application_status")
        )

    def test_application_status_stays_scoped_to_the_signed_in_account(self):
        self.reject("private note")
        self.client.force_login(self.other)
        response = self.client.get(reverse("owner_application_status"), follow=True)
        self.assertNotContains(response, "private note")
        self.assertNotContains(response, "Garden Kitchen")
