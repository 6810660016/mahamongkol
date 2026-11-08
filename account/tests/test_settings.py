from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class SettingsPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'somchai', 'somchai@example.com', 'Queue-pass-2026',
        )
        self.url = reverse('settings')
        self.client.force_login(self.user)

    def post(self, data):
        return self.client.post(self.url, data)

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}",
        )

    def test_page_shows_account_details_and_nav(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Personal details')
        self.assertContains(response, 'aria-label="My Q"')
        self.assertContains(response, 'somchai@example.com')
        # No name saved yet: the username is shown instead of "Guest Member".
        self.assertContains(response, 'placeholder="somchai"')
        self.assertNotContains(response, 'Guest Member')

    def test_email_is_read_only_and_not_a_form_field(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="settings-email"')
        self.assertContains(response, 'readonly')
        self.assertNotContains(response, 'name="email"')

    def test_unavailable_settings_are_disabled_and_marked_coming_soon(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Coming soon', count=2)
        for field in (
            'language', 'currency', 'time_format',
            'reservation_updates', 'reminders', 'offers',
        ):
            with self.subTest(field=field):
                self.assertNotContains(response, f'name="{field}"')

    def test_page_has_save_confirmation_dialog(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="settings-confirm"')
        self.assertContains(response, 'id="settings-form"')
        self.assertContains(response, 'settings_confirm.js')

    def test_name_is_saved_to_the_user(self):
        response = self.post({'name': 'Somchai Jaidee'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your settings have been saved')
        self.assertContains(response, 'Somchai Jaidee')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Somchai Jaidee')

    def test_saved_name_is_shown_on_next_visit(self):
        self.post({'name': 'Somchai Jaidee'})
        response = self.client.get(self.url)
        self.assertContains(response, 'value="Somchai Jaidee"')
        self.assertNotContains(response, 'Your settings have been saved')

    def test_extra_spaces_are_collapsed(self):
        self.post({'name': '   Somchai    Jaidee  '})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Somchai Jaidee')

    def test_long_name_is_cut_to_80_characters(self):
        self.post({'name': 'ก' * 200})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'ก' * 80)

    def test_empty_name_falls_back_to_username(self):
        self.user.first_name = 'Somchai'
        self.user.save()
        response = self.post({'name': '   '})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')
        self.assertContains(response, 'somchai')

    def test_name_is_html_escaped(self):
        response = self.post({'name': '<script>alert(1)</script>'})
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_posted_email_is_ignored(self):
        self.post({'name': 'Somchai', 'email': 'attacker@example.com'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'somchai@example.com')

    def test_posted_preferences_are_not_stored(self):
        self.post({
            'name': 'Somchai',
            'language': 'Thai',
            'currency': 'USD',
            'time_format': '24-hour',
            'reminders': 'on',
        })
        self.assertNotIn('site_settings', self.client.session)

    def test_saving_only_changes_the_signed_in_user(self):
        other = User.objects.create_user(
            'malee', 'malee@example.com', 'Queue-pass-2026',
        )
        self.post({'name': 'Somchai Jaidee'})
        other.refresh_from_db()
        self.assertEqual(other.first_name, '')
