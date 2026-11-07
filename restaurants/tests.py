from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import OwnerApplication
from bookings.models import Booking

from . import services
from .forms import MAX_EXTRAS, RestaurantForm
from .models import Restaurant, Table

User = get_user_model()

PASSWORD = 'Queue-pass-2026'


def make_owner(username):
    owner = User.objects.create_user(
        username, f'{username}@example.com', PASSWORD, role=User.Role.OWNER,
    )
    OwnerApplication.objects.create(
        user=owner, contact_name=username, business_name=f'{username} business',
        status=OwnerApplication.Status.APPROVED,
    )
    return owner


def form_data(**overrides):
    """Build POST-like data (a QueryDict, since the form reads getlist())."""
    data = QueryDict(mutable=True)
    values = {'name': 'Test Store', 'category': 'Restaurant', **overrides}
    for key, value in values.items():
        if isinstance(value, list):
            data.setlist(key, value)
        else:
            data[key] = value
    return data


class RestaurantDetailTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user(
            'customer-test', 'customer@example.com', 'Queue-pass-2026',
        ))

    def test_breadcrumb_shows_restaurant_name(self):
        response = self.client.get(reverse('restaurant_detail', args=['salvia']))
        self.assertContains(response, '<span>/</span><span>Salvia</span>', html=False)
        self.assertNotContains(response, '{{')


class CustomerRestaurantPagesTests(TestCase):
    """Customers only ever see published stores."""

    def setUp(self):
        self.client.force_login(User.objects.create_user(
            'customer', 'customer@example.com', PASSWORD,
        ))
        self.published = Restaurant.objects.create(
            slug='open-kitchen', name='Open Kitchen', type='Thai street food',
            address='Sukhumvit 24', status=Restaurant.Status.PUBLISHED,
        )
        self.draft = Restaurant.objects.create(
            slug='secret-draft', name='Secret Draft Kitchen', status=Restaurant.Status.DRAFT,
        )

    def test_list_shows_published_and_hides_draft_stores(self):
        response = self.client.get(reverse('restaurants'))
        self.assertContains(response, 'Open Kitchen')
        self.assertNotContains(response, 'Secret Draft Kitchen')

    def test_detail_of_published_store_loads(self):
        response = self.client.get(reverse('restaurant_detail', args=['open-kitchen']))
        self.assertContains(response, 'Open Kitchen')

    def test_detail_of_draft_store_is_404(self):
        response = self.client.get(reverse('restaurant_detail', args=['secret-draft']))
        self.assertEqual(response.status_code, 404)

    def test_detail_of_unknown_store_is_404(self):
        response = self.client.get(reverse('restaurant_detail', args=['does-not-exist']))
        self.assertEqual(response.status_code, 404)

    def test_search_matches_name_type_and_address_ignoring_case(self):
        for query in ('open kitchen', 'STREET FOOD', 'sukhumvit'):
            with self.subTest(query=query):
                response = self.client.get(reverse('restaurants'), {'q': query})
                self.assertContains(response, 'Open Kitchen')

    def test_search_never_returns_draft_stores(self):
        response = self.client.get(reverse('restaurants'), {'q': 'Secret Draft'})
        self.assertNotContains(response, 'Secret Draft Kitchen')

    def test_search_with_no_match_hides_other_stores(self):
        response = self.client.get(reverse('restaurants'), {'q': 'zzz-no-such-store'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Open Kitchen')

    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        for url in (reverse('restaurants'), reverse('restaurant_detail', args=['open-kitchen'])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response['Location'].startswith(reverse('login')))


class RestaurantFormTests(TestCase):
    def test_minimal_valid_form(self):
        form = RestaurantForm(form_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['extras'], [])

    def test_name_is_trimmed(self):
        form = RestaurantForm(form_data(name='  Padded Name  '))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['name'], 'Padded Name')

    def test_blank_name_is_rejected(self):
        for name in ('', '   '):
            with self.subTest(name=repr(name)):
                form = RestaurantForm(form_data(name=name))
                self.assertFalse(form.is_valid())
                self.assertIn('name', form.errors)

    def test_image_must_be_http_or_https(self):
        for url in ('javascript:alert(1)', 'ftp://example.com/a.png'):
            with self.subTest(url=url):
                form = RestaurantForm(form_data(image=url))
                self.assertFalse(form.is_valid())
                self.assertIn('image', form.errors)

    def test_https_image_is_accepted(self):
        form = RestaurantForm(form_data(image='https://example.com/store.jpg'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_price_must_be_one_of_the_choices(self):
        form = RestaurantForm(form_data(price='$$$$ · Made up'))
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_unknown_category_is_rejected(self):
        form = RestaurantForm(form_data(category='Casino'))
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)

    def test_table_and_seat_limits(self):
        cases = {
            'table_count': (('0', False), ('1', True), ('50', True), ('51', False)),
            'seats_per_table': (('0', False), ('1', True), ('12', True), ('13', False)),
        }
        for field, values in cases.items():
            for value, valid in values:
                with self.subTest(field=field, value=value):
                    form = RestaurantForm(form_data(**{field: value}))
                    self.assertEqual(form.is_valid(), valid, form.errors)

    def test_extras_are_paired_trimmed_and_empty_rows_dropped(self):
        form = RestaurantForm(form_data(
            extra_key=[' Parking ', '', 'Wi-Fi', 'Pets'],
            extra_value=[' Free ', 'orphan value', 'Yes', '   '],
        ))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['extras'],
            [{'key': 'Parking', 'value': 'Free'}, {'key': 'Wi-Fi', 'value': 'Yes'}],
        )

    def test_extras_are_cut_to_length_and_count_limits(self):
        count = MAX_EXTRAS + 3
        form = RestaurantForm(form_data(
            extra_key=['k' * 100] * count,
            extra_value=['v' * 300] * count,
        ))
        self.assertTrue(form.is_valid(), form.errors)
        extras = form.cleaned_data['extras']
        self.assertEqual(len(extras), MAX_EXTRAS)
        self.assertEqual(len(extras[0]['key']), 60)
        self.assertEqual(len(extras[0]['value']), 200)

    def test_form_cannot_set_owner_status_or_rating(self):
        form = RestaurantForm(form_data(status='published', rating='5.0', owner='1', slug='x'))
        self.assertTrue(form.is_valid(), form.errors)
        for field in ('status', 'rating', 'owner', 'slug'):
            self.assertNotIn(field, form.cleaned_data)


class CreateRestaurantServiceTests(TestCase):
    def setUp(self):
        self.owner = make_owner('creator')

    def create(self, owner=None, **data):
        return services.create_restaurant(owner or self.owner, {'name': 'New Place', **data})

    def test_new_store_is_a_draft_owned_by_the_owner(self):
        store = self.create()
        self.assertEqual(store.owner, self.owner)
        self.assertEqual(store.status, Restaurant.Status.DRAFT)

    def test_default_tables_are_created(self):
        store = self.create()
        self.assertEqual(store.tables.count(), services.DEFAULT_TABLE_COUNT)
        self.assertEqual(
            set(store.tables.values_list('capacity', flat=True)), {services.DEFAULT_SEATS},
        )

    def test_custom_table_count_and_seats(self):
        store = services.create_restaurant(
            self.owner, {'name': 'Small Place'}, table_count=2, seats=8,
        )
        self.assertEqual(list(store.tables.values_list('name', 'capacity')), [('T1', 8), ('T2', 8)])

    def test_slug_comes_from_the_name(self):
        self.assertEqual(self.create(name='Blue Moon Cafe').slug, 'blue-moon-cafe')

    def test_same_name_gets_a_numbered_slug(self):
        first = self.create(name='Twin Diner')
        second = self.create(owner=make_owner('second'), name='Twin Diner')
        self.assertEqual(first.slug, 'twin-diner')
        self.assertEqual(second.slug, 'twin-diner-2')

    def test_reserved_slug_is_avoided(self):
        # "new" would clash with the /owner/stores/new/ route.
        self.assertEqual(self.create(name='New').slug, 'new-store')

    def test_name_without_slug_characters_falls_back_to_store(self):
        self.assertEqual(self.create(name='!!!').slug, 'store')

    def test_second_store_for_the_same_owner_is_refused(self):
        self.create()
        with self.assertRaises(services.RestaurantError):
            self.create(name='Another Place')
        self.assertEqual(Restaurant.objects.filter(owner=self.owner).count(), 1)


class ManageRestaurantServiceTests(TestCase):
    def setUp(self):
        self.owner = make_owner('manager')
        self.store = services.create_restaurant(self.owner, {'name': 'Managed Place'})

    def test_update_keeps_the_slug(self):
        services.update_restaurant(self.store, self.owner, {'name': 'Brand New Name'})
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, 'Brand New Name')
        self.assertEqual(self.store.slug, 'managed-place')

    def test_update_ignores_fields_owners_may_not_edit(self):
        services.update_restaurant(
            self.store, self.owner, {'status': 'published', 'rating': 5, 'slug': 'hijack'},
        )
        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Restaurant.Status.DRAFT)
        self.assertEqual(self.store.rating, 0)
        self.assertEqual(self.store.slug, 'managed-place')

    def test_set_status_publishes_and_closes(self):
        services.set_status(self.store, self.owner, status='published', is_open=False)
        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Restaurant.Status.PUBLISHED)
        self.assertFalse(self.store.is_open)

    def test_set_status_rejects_unknown_status(self):
        with self.assertRaises(services.RestaurantError):
            services.set_status(self.store, self.owner, status='deleted')
        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Restaurant.Status.DRAFT)

    def test_delete_without_bookings_removes_store_and_tables(self):
        services.delete_restaurant(self.store, self.owner)
        self.assertFalse(Restaurant.objects.filter(pk=self.store.pk).exists())
        self.assertFalse(Table.objects.filter(restaurant_id=self.store.pk).exists())

    def test_delete_with_booking_history_is_refused(self):
        customer = User.objects.create_user('guest', 'guest@example.com', PASSWORD)
        Booking.objects.create(
            user=customer, table=self.store.tables.first(),
            date=timezone.localdate() + timedelta(days=1), time=time(12, 0), guests=2,
        )
        with self.assertRaises(services.RestaurantError):
            services.delete_restaurant(self.store, self.owner)
        self.assertTrue(Restaurant.objects.filter(pk=self.store.pk).exists())

    def test_managed_restaurants_for_owner_and_admin(self):
        other = services.create_restaurant(make_owner('other'), {'name': 'Other Place'})
        admin = User.objects.create_user(
            'admin-user', 'admin-user@example.com', PASSWORD, role=User.Role.ADMIN,
        )
        self.assertEqual(list(services.managed_restaurants(self.owner)), [self.store])
        self.assertIn(other, services.managed_restaurants(admin))
        self.assertIn(self.store, services.managed_restaurants(admin))


class TableModelTests(TestCase):
    def test_table_name_is_unique_within_a_store(self):
        store = Restaurant.objects.create(slug='tables', name='Tables')
        Table.objects.create(restaurant=store, name='A1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Table.objects.create(restaurant=store, name='A1')

    def test_same_table_name_is_fine_in_another_store(self):
        first = Restaurant.objects.create(slug='first', name='First')
        second = Restaurant.objects.create(slug='second', name='Second')
        Table.objects.create(restaurant=first, name='A1')
        Table.objects.create(restaurant=second, name='A1')
        self.assertEqual(Table.objects.filter(name='A1').count(), 2)
