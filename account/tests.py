from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse


class BookingFlowTests(TestCase):
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
        response = self.client.post(reverse('booking', args=['salvia']), {
            'date': (date.today() + timedelta(days=1)).isoformat(),
            'time': '19:00',
            'guests': '2',
        })
        self.assertRedirects(response, reverse('my_queues'))
        self.assertContains(self.client.get(reverse('my_queues')), 'Salvia')

        response = self.client.post(reverse('cancel_booking', args=[1]))
        self.assertRedirects(response, reverse('my_queues'))
        self.assertContains(self.client.get(reverse('my_queues')), 'Your next favourite moment')

    def test_booking_rejects_invalid_time(self):
        response = self.client.post(reverse('booking', args=['salvia']), {
            'date': (date.today() + timedelta(days=1)).isoformat(),
            'time': '03:00',
            'guests': '2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please choose a valid date')
