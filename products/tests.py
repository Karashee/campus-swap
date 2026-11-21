from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from products.models import Category, Listing

User = get_user_model()


def an_image(name='photo.jpg'):
    buffer = BytesIO()
    Image.new('RGB', (600, 450), (200, 180, 160)).save(buffer, format='JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


class ListingTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='wanjiku',
            email='wanjiku@strathmore.edu',
            password='SwapItQuick42',
            phone='+254712345678',
        )
        cls.other = User.objects.create_user(
            username='brian', email='brian@strathmore.edu', password='SwapItQuick42'
        )
        # The data migration already seeds the categories into the test
        # database, so reuse that row rather than creating a duplicate slug.
        cls.category, _ = Category.objects.get_or_create(
            slug='textbooks', defaults={'name': 'Textbooks', 'ordering': 1}
        )

    def make_listing(self, **kwargs):
        defaults = {
            'seller': self.owner,
            'title': 'Calculus 8th ed',
            'description': 'Used for one semester.',
            'category': self.category,
            'condition': Listing.Condition.GOOD,
            'listing_type': Listing.ListingType.SELL,
            'price': 1800,
            'meetup_spot': 'Library entrance',
            'image': an_image(),
        }
        return Listing.objects.create(**{**defaults, **kwargs})


class CreateViewTests(ListingTestBase):
    def test_anonymous_user_is_redirected_to_login(self):
        url = reverse('products:create')
        response = self.client.get(url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={url}')

    def test_sell_without_a_price_shows_an_error_on_price(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('products:create'), {
            'title': 'Casio fx-991ES',
            'category': self.category.pk,
            'listing_type': 'SELL',
            'condition': 'GOOD',
            'price': '',
            'trade_for': '',
            'description': 'Barely used.',
            'meetup_spot': 'Student Centre',
            'image': an_image(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'price',
            'Give a price above 0 for an item you are selling.',
        )
        self.assertFalse(Listing.objects.filter(title='Casio fx-991ES').exists())

    def test_trade_without_trade_for_shows_an_error(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('products:create'), {
            'title': 'Study desk',
            'category': self.category.pk,
            'listing_type': 'TRADE',
            'condition': 'FAIR',
            'price': '',
            'trade_for': '',
            'description': 'Solid desk.',
            'meetup_spot': 'Phase 2',
            'image': an_image(),
        })
        self.assertFormError(
            response.context['form'], 'trade_for', 'Say what you want in exchange.'
        )

    def test_seller_is_the_logged_in_user_not_a_posted_field(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('products:create'), {
            'title': 'Desk lamp',
            'category': self.category.pk,
            'listing_type': 'FREE',
            'condition': 'GOOD',
            'price': '',
            'trade_for': '',
            'description': 'Works fine.',
            'meetup_spot': 'Main gate',
            'image': an_image(),
            'seller': self.other.pk,  # ignored
        })
        listing = Listing.objects.get(title='Desk lamp')
        self.assertEqual(listing.seller, self.owner)
        self.assertIsNone(listing.price)


class OwnershipTests(ListingTestBase):
    def setUp(self):
        self.listing = self.make_listing()

    def test_non_owner_gets_404_on_edit(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('products:edit', args=[self.listing.slug]))
        self.assertEqual(response.status_code, 404)

    def test_non_owner_gets_404_on_delete(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('products:delete', args=[self.listing.slug]))
        self.assertEqual(response.status_code, 404)

    def test_non_owner_cannot_delete_by_posting(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('products:delete', args=[self.listing.slug])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())

    def test_owner_can_edit(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('products:edit', args=[self.listing.slug]))
        self.assertEqual(response.status_code, 200)

    def test_owner_can_delete(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:delete', args=[self.listing.slug])
        )
        self.assertRedirects(response, reverse('products:my_listings'))
        self.assertFalse(Listing.objects.filter(pk=self.listing.pk).exists())


class MarkStatusTests(ListingTestBase):
    def setUp(self):
        self.listing = self.make_listing()

    def test_owner_can_mark_sold_via_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:mark_status', args=[self.listing.slug, 'SOLD'])
        )
        self.assertRedirects(response, self.listing.get_absolute_url())
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.SOLD)

    def test_get_is_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse('products:mark_status', args=[self.listing.slug, 'SOLD'])
        )
        self.assertEqual(response.status_code, 405)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.AVAILABLE)

    def test_non_owner_gets_404(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('products:mark_status', args=[self.listing.slug, 'SOLD'])
        )
        self.assertEqual(response.status_code, 404)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.AVAILABLE)

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.post(
            reverse('products:mark_status', args=[self.listing.slug, 'SOLD'])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response['Location'])


class DetailViewTests(ListingTestBase):
    def setUp(self):
        self.listing = self.make_listing()

    def test_views_increment_for_a_visitor(self):
        self.client.get(self.listing.get_absolute_url())
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.views, 1)

    def test_views_do_not_increment_for_the_owner(self):
        self.client.force_login(self.owner)
        self.client.get(self.listing.get_absolute_url())
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.views, 0)

    def test_anonymous_user_is_asked_to_log_in_to_contact(self):
        response = self.client.get(self.listing.get_absolute_url())
        self.assertContains(response, 'Log in to contact the seller')
        self.assertNotContains(response, 'wa.me')

    def test_logged_in_non_owner_sees_the_whatsapp_link(self):
        self.client.force_login(self.other)
        response = self.client.get(self.listing.get_absolute_url())
        self.assertContains(response, 'wa.me/254712345678')

    def test_owner_sees_management_actions(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.listing.get_absolute_url())
        self.assertContains(response, 'This is your listing')
        self.assertNotContains(response, 'wa.me')


class RecentlyViewedSessionTests(ListingTestBase):
    """Recently viewed listings are tracked in request.session."""

    def setUp(self):
        self.first = self.make_listing(title='Calculus 8th ed')
        self.second = self.make_listing(title='Casio fx-991ES')
        self.mine = self.make_listing(title='My own hoodie', seller=self.other)

    def test_viewing_listings_records_them_most_recent_first(self):
        self.client.get(self.first.get_absolute_url())
        self.client.get(self.second.get_absolute_url())
        self.assertEqual(
            self.client.session['recently_viewed'],
            [self.second.pk, self.first.pk],
        )

    def test_revisiting_moves_it_to_the_front_without_duplicating(self):
        self.client.get(self.first.get_absolute_url())
        self.client.get(self.second.get_absolute_url())
        self.client.get(self.first.get_absolute_url())
        self.assertEqual(
            self.client.session['recently_viewed'],
            [self.first.pk, self.second.pk],
        )

    def test_your_own_listings_are_not_recorded(self):
        self.client.force_login(self.other)
        self.client.get(self.mine.get_absolute_url())
        self.assertNotIn('recently_viewed', self.client.session)

    def test_only_the_last_five_are_kept(self):
        listings = [self.make_listing(title=f'Item {i}') for i in range(7)]
        for listing in listings:
            self.client.get(listing.get_absolute_url())
        recorded = self.client.session['recently_viewed']
        self.assertEqual(len(recorded), 5)
        self.assertEqual(recorded, [l.pk for l in reversed(listings[-5:])])

    def test_home_page_shows_the_recently_viewed_strip(self):
        self.client.get(self.first.get_absolute_url())
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Recently viewed')
        self.assertEqual(
            [l.pk for l in response.context['recently_viewed']], [self.first.pk]
        )


class SearchTests(ListingTestBase):
    def setUp(self):
        self.make_listing(title='Calculus 8th ed')
        self.make_listing(
            title='Casio fx-991ES', description='Scientific calculator.'
        )

    def test_home_search_filters_by_title(self):
        response = self.client.get(reverse('home'), {'q': 'calculus'})
        self.assertContains(response, 'Calculus 8th ed')
        self.assertNotContains(response, 'Casio fx-991ES')

    def test_home_search_also_matches_the_description(self):
        response = self.client.get(reverse('home'), {'q': 'scientific'})
        self.assertContains(response, 'Casio fx-991ES')

    def test_sold_listings_are_not_in_the_public_grid(self):
        self.make_listing(title='Sold hoodie', status=Listing.Status.SOLD)
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'Sold hoodie')


class MyListingsTests(ListingTestBase):
    def test_requires_login(self):
        url = reverse('products:my_listings')
        self.assertRedirects(
            self.client.get(url), f'{reverse("accounts:login")}?next={url}'
        )

    def test_shows_only_your_own_listings(self):
        self.make_listing(title='Mine')
        self.make_listing(title='Theirs', seller=self.other)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('products:my_listings'))
        self.assertContains(response, 'Mine')
        self.assertNotContains(response, 'Theirs')

    def test_status_tab_filters(self):
        self.make_listing(title='Still here')
        self.make_listing(title='Gone already', status=Listing.Status.SOLD)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('products:my_listings'), {'status': 'SOLD'})
        self.assertContains(response, 'Gone already')
        self.assertNotContains(response, 'Still here')
