from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class RestaurantDetailTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user(
            'customer-test', 'customer@example.com', 'Queue-pass-2026',
        ))

    def test_breadcrumb_shows_restaurant_name(self):
        response = self.client.get(reverse('restaurant_detail', args=['salvia']))
        self.assertContains(response, '<span>/</span><span>Salvia</span>', html=False)
        self.assertNotContains(response, '{{')
