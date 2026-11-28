"""Tests for the JSON API (chunk B8).

The permission matrix for the API URLs lives with the rest of the audit in
``config/tests_security.py``; what is here is the behaviour of the endpoints
themselves: the shape of the payloads, the filters, the business rules, and
the two ways of authenticating.
"""

from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token

from products.models import Category, Listing, ListingImage
from products.tests import an_image

User = get_user_model()


def response_text(payload):
    """A payload flattened to one string, for "this must not appear" checks."""
    return str(payload)


class ApiTestBase(TestCase):
    """Two students and three listings, one of each listing type."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='wanjiku',
            email='wanjiku@strathmore.edu',
            password='SwapItQuick42',
            first_name='Wanjiku',
            last_name='Mwangi',
        )
        cls.other = User.objects.create_user(
            username='brian',
            email='brian@strathmore.edu',
            password='SwapItQuick42',
        )
        cls.books, _ = Category.objects.get_or_create(
            slug='textbooks', defaults={'name': 'Textbooks', 'ordering': 1}
        )
        cls.gadgets, _ = Category.objects.get_or_create(
            slug='electronics', defaults={'name': 'Electronics', 'ordering': 2}
        )

        cls.calculus = Listing.objects.create(
            seller=cls.owner,
            title='Calculus 8th ed',
            description='Used for one semester.',
            category=cls.books,
            condition=Listing.Condition.GOOD,
            listing_type=Listing.ListingType.SELL,
            price=1800,
            meetup_spot='Library entrance',
        )
        ListingImage.objects.create(
            listing=cls.calculus, image=an_image('cover.jpg'), order=0
        )
        cls.kettle = Listing.objects.create(
            seller=cls.other,
            title='Electric kettle',
            description='Boils fast.',
            category=cls.gadgets,
            condition=Listing.Condition.FAIR,
            listing_type=Listing.ListingType.FREE,
            meetup_spot='Phase 2 gate',
        )
        cls.sold_lamp = Listing.objects.create(
            seller=cls.other,
            title='Desk lamp',
            description='Already gone.',
            category=cls.gadgets,
            condition=Listing.Condition.GOOD,
            listing_type=Listing.ListingType.SELL,
            price=600,
            status=Listing.Status.SOLD,
            meetup_spot='Student centre',
        )

    def listings_url(self, **query):
        url = reverse('api:listing-list')
        if query:
            url = f'{url}?{urlencode(query)}'
        return url

    def detail_url(self, listing):
        return reverse('api:listing-detail', kwargs={'slug': listing.slug})

    def titles(self, response):
        return [row['title'] for row in response.json()['results']]

    def valid_payload(self, **overrides):
        payload = {
            'title': 'Scientific calculator',
            'description': 'Casio fx-991ES, all keys work.',
            'category_id': self.books.pk,
            'condition': Listing.Condition.LIKE_NEW,
            'listing_type': Listing.ListingType.SELL,
            'price': '1200.00',
            'meetup_spot': 'Library entrance',
        }
        payload.update(overrides)
        return payload


class CategoryEndpointTests(ApiTestBase):
    def test_the_list_is_public_and_counts_available_listings(self):
        response = self.client.get(reverse('api:category-list'))
        self.assertEqual(response.status_code, 200)

        by_slug = {row['slug']: row for row in response.json()}
        # One available book, and one available gadget: the sold lamp is not
        # counted even though it is in the category.
        self.assertEqual(by_slug['textbooks']['listing_count'], 1)
        self.assertEqual(by_slug['electronics']['listing_count'], 1)

    def test_a_category_is_fetched_by_slug(self):
        response = self.client.get(
            reverse('api:category-detail', kwargs={'slug': 'textbooks'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['name'], 'Textbooks')

    def test_categories_are_read_only(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('api:category-list'), {'name': 'Bikes', 'slug': 'bikes'}
        )
        self.assertEqual(response.status_code, 405)


class ListingReadTests(ApiTestBase):
    def test_the_list_is_public_paginated_and_hides_sold_items(self):
        response = self.client.get(self.listings_url())
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body['count'], 2)
        self.assertEqual(set(self.titles(response)), {'Calculus 8th ed', 'Electric kettle'})
        self.assertIsNone(body['next'])

    def test_show_sold_brings_the_sold_listing_back(self):
        response = self.client.get(self.listings_url(show_sold='true'))
        self.assertIn('Desk lamp', self.titles(response))

    def test_a_listing_carries_its_photo_urls_the_seller_and_the_web_url(self):
        response = self.client.get(self.detail_url(self.calculus))
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body['seller']['username'], 'wanjiku')
        self.assertEqual(body['seller']['display_name'], 'Wanjiku Mwangi')
        self.assertEqual(body['category']['slug'], 'textbooks')
        self.assertEqual(body['display_price'], 'KSh 1,800')
        self.assertEqual(len(body['images']), 1)
        self.assertTrue(body['images'][0]['image'].startswith('http'))
        self.assertIn(self.calculus.get_absolute_url(), body['web_url'])

    def test_a_seller_s_contact_details_are_not_in_the_payload(self):
        """The API is public, so it must not hand out phone numbers."""
        self.owner.phone = '+254712345678'
        self.owner.save(update_fields=['phone'])

        body = self.client.get(self.detail_url(self.calculus)).json()
        self.assertNotIn('phone', body['seller'])
        self.assertNotIn('email', body['seller'])
        self.assertNotIn('+254712345678', response_text(body))

    def test_filters_narrow_the_list(self):
        cases = {
            'category=slug': ({'category': 'electronics'}, ['Electric kettle']),
            'category=id': ({'category': str(self.books.pk)}, ['Calculus 8th ed']),
            'type': ({'listing_type': 'FREE'}, ['Electric kettle']),
            'condition': ({'condition': 'GOOD'}, ['Calculus 8th ed']),
            'search': ({'q': 'calculus'}, ['Calculus 8th ed']),
            'search in description': ({'q': 'boils'}, ['Electric kettle']),
            'min price': ({'min_price': '1000'}, ['Calculus 8th ed']),
            'max price': ({'max_price': '1000'}, []),
        }
        for label, (query, expected) in cases.items():
            with self.subTest(filter=label):
                response = self.client.get(self.listings_url(**query))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.titles(response), expected)

    def test_a_contradictory_filter_is_a_400_with_the_reason(self):
        """The browse page can show errors next to the inputs; a client can't."""
        response = self.client.get(
            self.listings_url(min_price='900', max_price='100')
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('min_price', response.json())

    def test_the_price_sort_puts_free_and_trade_items_last(self):
        response = self.client.get(self.listings_url(sort='price_asc'))
        self.assertEqual(self.titles(response), ['Calculus 8th ed', 'Electric kettle'])

    def test_the_page_size_can_be_asked_for_but_is_capped(self):
        response = self.client.get(self.listings_url(page_size='1'))
        self.assertEqual(len(response.json()['results']), 1)
        self.assertIsNotNone(response.json()['next'])

        response = self.client.get(self.listings_url(page_size='500'))
        self.assertEqual(len(response.json()['results']), 2)

    def test_the_list_takes_a_handful_of_queries_whatever_the_page_holds(self):
        """select_related/prefetch_related, same as the browse grid."""
        for index in range(8):
            listing = Listing.objects.create(
                seller=self.other,
                title=f'Notebook {index}',
                description='Barely used.',
                category=self.books,
                condition=Listing.Condition.GOOD,
                listing_type=Listing.ListingType.SELL,
                price=100 + index,
                meetup_spot='Gate B',
            )
            ListingImage.objects.create(
                listing=listing, image=an_image(f'n{index}.jpg'), order=0
            )

        # One count for the pagination, one for the page (joined to the seller
        # and the category), one for all of the photos.
        with self.assertNumQueries(3):
            self.client.get(self.listings_url())


class ListingWriteTests(ApiTestBase):
    def test_an_anonymous_client_cannot_post_a_listing(self):
        response = self.client.post(
            reverse('api:listing-list'), self.valid_payload(), 'application/json'
        )
        # 401, not 403: nobody has authenticated yet, and the response carries
        # a WWW-Authenticate header saying how to.
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['WWW-Authenticate'], 'Token')
        self.assertFalse(Listing.objects.filter(title='Scientific calculator').exists())

    def test_a_logged_in_student_posts_a_listing_and_becomes_its_seller(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('api:listing-list'), self.valid_payload(), 'application/json'
        )
        self.assertEqual(response.status_code, 201, response.content)

        listing = Listing.objects.get(title='Scientific calculator')
        self.assertEqual(listing.seller, self.other)
        self.assertTrue(listing.slug)

    def test_a_posted_seller_is_ignored(self):
        """Same rule as the web form: the seller is the caller, full stop."""
        self.client.force_login(self.other)
        self.client.post(
            reverse('api:listing-list'),
            self.valid_payload(seller=self.owner.pk),
            'application/json',
        )
        self.assertEqual(
            Listing.objects.get(title='Scientific calculator').seller, self.other
        )

    def test_the_owner_edits_and_deletes_their_own_listing(self):
        self.client.force_login(self.owner)
        url = self.detail_url(self.calculus)

        response = self.client.patch(url, {'price': '1500.00'}, 'application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.calculus.refresh_from_db()
        self.assertEqual(str(self.calculus.price), '1500.00')

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Listing.objects.filter(pk=self.calculus.pk).exists())

    def test_another_student_cannot_edit_or_delete_someone_else_s_listing(self):
        self.client.force_login(self.other)
        url = self.detail_url(self.calculus)

        patch = self.client.patch(url, {'title': 'Stolen'}, 'application/json')
        self.assertEqual(patch.status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)

        self.calculus.refresh_from_db()
        self.assertEqual(self.calculus.title, 'Calculus 8th ed')

    def test_the_serializer_enforces_the_model_s_listing_type_rules(self):
        """Listing.clean() is the single copy of these; the API runs it too."""
        self.client.force_login(self.other)
        cases = {
            'selling for nothing': (
                {'listing_type': 'SELL', 'price': None}, 'price',
            ),
            'a priced trade': (
                {'listing_type': 'TRADE', 'price': '500.00', 'trade_for': 'A kettle'},
                'price',
            ),
            'a trade with nothing wanted': (
                {'listing_type': 'TRADE', 'price': None, 'trade_for': ''},
                'trade_for',
            ),
        }
        for label, (overrides, expected_field) in cases.items():
            with self.subTest(case=label):
                response = self.client.post(
                    reverse('api:listing-list'),
                    self.valid_payload(**overrides),
                    'application/json',
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(expected_field, response.json())

    def test_a_free_listing_is_saved_without_a_price_even_if_one_is_sent(self):
        """Listing.clean() blanks it; the serializer must not put it back."""
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('api:listing-list'),
            self.valid_payload(listing_type='FREE', price='900.00'),
            'application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(Listing.objects.get(title='Scientific calculator').price)

    def test_a_patch_is_validated_against_the_row_it_would_produce(self):
        """Switching a sale to a trade has to clear the price in the same call."""
        self.client.force_login(self.owner)
        url = self.detail_url(self.calculus)

        refused = self.client.patch(
            url, {'listing_type': 'TRADE', 'trade_for': 'A kettle'}, 'application/json'
        )
        self.assertEqual(refused.status_code, 400)
        self.assertIn('price', refused.json())

        accepted = self.client.patch(
            url,
            {'listing_type': 'TRADE', 'trade_for': 'A kettle', 'price': None},
            'application/json',
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)

    def test_photos_cannot_be_set_through_the_api(self):
        """images is read-only: uploads stay in the web form, which checks them."""
        self.client.force_login(self.owner)
        response = self.client.patch(
            self.detail_url(self.calculus),
            {'images': [{'image': 'http://evil.example/x.jpg', 'order': 0}]},
            'application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calculus.images.count(), 1)
        self.assertIn('listings/', self.calculus.images.get().image.name)


class ApiAuthenticationTests(ApiTestBase):
    def test_a_token_is_issued_for_the_right_password_and_used_as_a_header(self):
        response = self.client.post(
            reverse('api:token'),
            {'username': 'wanjiku', 'password': 'SwapItQuick42'},
            'application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        key = response.json()['token']
        self.assertEqual(Token.objects.get(user=self.owner).key, key)

        # No session anywhere: the header alone is enough to write.
        created = self.client.post(
            reverse('api:listing-list'),
            self.valid_payload(),
            'application/json',
            headers={'authorization': f'Token {key}'},
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(
            Listing.objects.get(title='Scientific calculator').seller, self.owner
        )

    def test_the_wrong_password_gets_no_token(self):
        response = self.client.post(
            reverse('api:token'),
            {'username': 'wanjiku', 'password': 'not-it'},
            'application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.owner).exists())

    def test_a_made_up_token_is_rejected(self):
        response = self.client.post(
            reverse('api:listing-list'),
            self.valid_payload(),
            'application/json',
            headers={'authorization': 'Token 0123456789abcdef'},
        )
        self.assertEqual(response.status_code, 401)


class ApiDocsTests(ApiTestBase):
    def test_the_schema_is_served_and_describes_the_endpoints(self):
        response = self.client.get(reverse('api:schema'))
        self.assertEqual(response.status_code, 200)

        schema = response.content.decode()
        self.assertIn('/api/v1/listings/', schema)
        self.assertIn('/api/v1/categories/', schema)
        self.assertIn('tokenAuth', schema)

    def test_the_docs_page_renders(self):
        response = self.client.get(reverse('api:docs'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="swagger-ui"')

    def test_the_docs_page_loads_swagger_from_our_own_static_files(self):
        """Sidecar, not a CDN: 'self' in the CSP has to be enough."""
        html = self.client.get(reverse('api:docs')).content.decode()
        self.assertIn('drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css', html)
        self.assertNotIn('cdn.jsdelivr.net', html)
        self.assertNotIn('unpkg.com', html)

    def test_the_docs_page_has_no_inline_script_or_style(self):
        """What makes the strict CSP work, so it is worth asserting.

        The init script comes back from a second request instead
        (SpectacularSwaggerSplitView), and the stylesheet is a static file.
        """
        html = self.client.get(reverse('api:docs')).content.decode()
        self.assertNotIn('<style', html)
        self.assertNotIn('style="', html)
        self.assertIn('<script src=', html)
        self.assertNotIn('<script>', html)

    def test_the_init_script_is_served_as_javascript(self):
        response = self.client.get(reverse('api:docs'), {'script': ''})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/javascript'))
        self.assertIn('SwaggerUIBundle', response.content.decode())
