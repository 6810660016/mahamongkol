from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

from django.urls import reverse
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

    def test_cancel_page_shows_booking_date(self):
        booking_date = (date.today() + timedelta(days=1)).isoformat()
        self.client.post(
            reverse('booking', args=['salvia']),
            {'date': booking_date, 'time': '19:00', 'guests': '2'},
        )

        response = self.client.get(reverse('cancel_booking', args=[1]))
        self.assertContains(response, f'<strong>{booking_date}</strong>')
        self.assertNotContains(response, '{{')
