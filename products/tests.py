from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from products.forms import PHOTO_PREFIX
from products.imaging import (
    MAX_DIMENSION,
    ImageTooLarge,
    ImageTooSmall,
    UnidentifiedImageError,
    process_upload,
)
from products.models import Category, Listing, ListingImage

User = get_user_model()


def an_image(name='photo.jpg', size=(600, 450), image_format='JPEG', **kwargs):
    """An uploadable image file, 600x450 by default."""
    buffer = BytesIO()
    Image.new('RGB', size, (200, 180, 160)).save(buffer, format=image_format, **kwargs)
    return SimpleUploadedFile(
        name, buffer.getvalue(), content_type=f'image/{image_format.lower()}'
    )


def photo_post(count=1, initial=0, extra_rows=0, **overrides):
    """Management-form data for the photo formset, plus `count` uploads.

    `initial` is how many existing photos the page rendered, so the keys line
    up with what the real form would post back.
    """
    total = initial + count + extra_rows
    data = {
        f'{PHOTO_PREFIX}-TOTAL_FORMS': str(total),
        f'{PHOTO_PREFIX}-INITIAL_FORMS': str(initial),
        f'{PHOTO_PREFIX}-MIN_NUM_FORMS': '0',
        f'{PHOTO_PREFIX}-MAX_NUM_FORMS': str(ListingImage.MAX_PHOTOS),
    }
    for index in range(initial, initial + count):
        data[f'{PHOTO_PREFIX}-{index}-image'] = an_image(f'photo{index}.jpg')
        data[f'{PHOTO_PREFIX}-{index}-ORDER'] = str(index + 1)
    data.update(overrides)
    return data


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

    def make_listing(self, photos=1, **kwargs):
        defaults = {
            'seller': self.owner,
            'title': 'Calculus 8th ed',
            'description': 'Used for one semester.',
            'category': self.category,
            'condition': Listing.Condition.GOOD,
            'listing_type': Listing.ListingType.SELL,
            'price': 1800,
            'meetup_spot': 'Library entrance',
        }
        listing = Listing.objects.create(**{**defaults, **kwargs})
        for position in range(photos):
            ListingImage.objects.create(
                listing=listing,
                image=an_image(f'photo{position}.jpg'),
                order=position,
            )
        return listing

    def listing_post(self, photos=1, initial=0, extra_rows=0, **fields):
        """POST data for the listing form plus its photo formset."""
        data = {
            'title': 'Casio fx-991ES',
            'category': self.category.pk,
            'listing_type': 'SELL',
            'condition': 'GOOD',
            'price': '1200',
            'trade_for': '',
            'description': 'Barely used.',
            'meetup_spot': 'Student Centre',
        }
        data.update(fields)
        data.update(photo_post(count=photos, initial=initial, extra_rows=extra_rows))
        return data


class CreateViewTests(ListingTestBase):
    def test_anonymous_user_is_redirected_to_login(self):
        url = reverse('products:create')
        response = self.client.get(url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={url}')

    def test_sell_without_a_price_shows_an_error_on_price(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:create'),
            self.listing_post(title='Casio fx-991ES', price=''),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'price',
            'Give a price above 0 for an item you are selling.',
        )
        self.assertFalse(Listing.objects.filter(title='Casio fx-991ES').exists())

    def test_trade_without_trade_for_shows_an_error(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:create'),
            self.listing_post(
                title='Study desk', listing_type='TRADE', price='', trade_for=''
            ),
        )
        self.assertFormError(
            response.context['form'], 'trade_for', 'Say what you want in exchange.'
        )

    def test_seller_is_the_logged_in_user_not_a_posted_field(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse('products:create'),
            self.listing_post(
                title='Desk lamp',
                listing_type='FREE',
                price='',
                seller=self.other.pk,  # ignored
            ),
        )
        listing = Listing.objects.get(title='Desk lamp')
        self.assertEqual(listing.seller, self.owner)
        self.assertIsNone(listing.price)


class PhotoFormsetTests(ListingTestBase):
    """The inline formset that gives a listing up to five photos."""

    def setUp(self):
        self.client.force_login(self.owner)

    def test_create_with_several_photos_keeps_them_in_order(self):
        response = self.client.post(
            reverse('products:create'), self.listing_post(photos=3, title='Hotplate')
        )
        listing = Listing.objects.get(title='Hotplate')
        self.assertRedirects(response, listing.get_absolute_url())

        photos = list(listing.images.all())
        self.assertEqual(len(photos), 3)
        self.assertEqual([photo.order for photo in photos], [0, 1, 2])
        self.assertEqual(listing.cover, photos[0])

    def test_a_listing_needs_at_least_one_photo(self):
        response = self.client.post(
            reverse('products:create'), self.listing_post(photos=0, title='No photo')
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'Add at least one photo of the item.',
            response.context['image_formset'].non_form_errors(),
        )
        self.assertFalse(Listing.objects.filter(title='No photo').exists())

    def test_more_than_five_photos_is_rejected(self):
        response = self.client.post(
            reverse('products:create'), self.listing_post(photos=6, title='Too many')
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Listing.objects.filter(title='Too many').exists())
        self.assertFalse(ListingImage.objects.filter(listing__title='Too many').exists())

    def test_empty_extra_slots_do_not_create_blank_photos(self):
        # Three rendered slots, one actually filled.
        self.client.post(
            reverse('products:create'),
            self.listing_post(photos=1, extra_rows=2, title='One photo'),
        )
        listing = Listing.objects.get(title='One photo')
        self.assertEqual(listing.images.count(), 1)

    def test_nothing_is_saved_when_the_photos_are_invalid(self):
        """The listing and its photos stand or fall together."""
        data = self.listing_post(photos=1, title='Tiny photo')
        data[f'{PHOTO_PREFIX}-0-image'] = an_image('tiny.jpg', size=(120, 90))

        response = self.client.post(reverse('products:create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Listing.objects.filter(title='Tiny photo').exists())

    def test_adding_a_photo_on_edit(self):
        listing = self.make_listing(photos=1)
        existing = listing.images.get()

        data = self.listing_post(
            photos=1, initial=1, title=listing.title, price='1800'
        )
        data[f'{PHOTO_PREFIX}-0-id'] = existing.pk
        data[f'{PHOTO_PREFIX}-0-ORDER'] = '1'

        response = self.client.post(
            reverse('products:edit', args=[listing.slug]), data
        )
        self.assertRedirects(response, listing.get_absolute_url())
        self.assertEqual(listing.images.count(), 2)

    def test_removing_a_photo_on_edit(self):
        listing = self.make_listing(photos=3)
        first, second, third = listing.images.all()

        data = self.listing_post(
            photos=0, initial=3, title=listing.title, price='1800'
        )
        for index, photo in enumerate((first, second, third)):
            data[f'{PHOTO_PREFIX}-{index}-id'] = photo.pk
            data[f'{PHOTO_PREFIX}-{index}-ORDER'] = str(index + 1)
        data[f'{PHOTO_PREFIX}-1-DELETE'] = 'on'

        self.client.post(reverse('products:edit', args=[listing.slug]), data)
        self.assertEqual(
            [photo.pk for photo in listing.images.all()], [first.pk, third.pk]
        )

    def test_removing_the_last_photo_is_refused(self):
        listing = self.make_listing(photos=1)
        photo = listing.images.get()

        data = self.listing_post(
            photos=0, initial=1, title=listing.title, price='1800'
        )
        data[f'{PHOTO_PREFIX}-0-id'] = photo.pk
        data[f'{PHOTO_PREFIX}-0-ORDER'] = '1'
        data[f'{PHOTO_PREFIX}-0-DELETE'] = 'on'

        response = self.client.post(
            reverse('products:edit', args=[listing.slug]), data
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'Add at least one photo of the item.',
            response.context['image_formset'].non_form_errors(),
        )
        self.assertTrue(listing.images.filter(pk=photo.pk).exists())

    def test_reordering_changes_the_cover(self):
        listing = self.make_listing(photos=3)
        first, second, third = listing.images.all()

        data = self.listing_post(
            photos=0, initial=3, title=listing.title, price='1800'
        )
        # The arrow buttons move the third photo to the front.
        for index, (photo, order) in enumerate(
            ((first, 2), (second, 3), (third, 1))
        ):
            data[f'{PHOTO_PREFIX}-{index}-id'] = photo.pk
            data[f'{PHOTO_PREFIX}-{index}-ORDER'] = str(order)

        self.client.post(reverse('products:edit', args=[listing.slug]), data)
        self.assertEqual(
            [photo.pk for photo in listing.images.all()],
            [third.pk, first.pk, second.pk],
        )
        self.assertEqual(listing.cover, third)

    def test_reordering_does_not_rewrite_the_stored_files(self):
        """Editing must not re-encode photos that nobody touched."""
        listing = self.make_listing(photos=2)
        first, second = listing.images.all()
        names_before = {first.pk: first.image.name, second.pk: second.image.name}

        data = self.listing_post(
            photos=0, initial=2, title=listing.title, price='1800'
        )
        for index, (photo, order) in enumerate(((first, 2), (second, 1))):
            data[f'{PHOTO_PREFIX}-{index}-id'] = photo.pk
            data[f'{PHOTO_PREFIX}-{index}-ORDER'] = str(order)

        self.client.post(reverse('products:edit', args=[listing.slug]), data)
        for photo in listing.images.all():
            self.assertEqual(photo.image.name, names_before[photo.pk])

    def test_the_form_page_shows_the_photo_formset(self):
        listing = self.make_listing(photos=2)
        response = self.client.get(reverse('products:edit', args=[listing.slug]))
        self.assertContains(response, f'{PHOTO_PREFIX}-TOTAL_FORMS')
        self.assertContains(response, f'{PHOTO_PREFIX}-0-image')
        self.assertEqual(
            response.context['image_formset'].initial_form_count(), 2
        )


class GalleryDisplayTests(ListingTestBase):
    def test_detail_page_lists_every_photo_as_a_thumbnail(self):
        listing = self.make_listing(photos=3)
        response = self.client.get(listing.get_absolute_url())
        self.assertEqual(len(response.context['photos']), 3)
        self.assertContains(response, 'data-thumb data-index', count=3)
        self.assertContains(response, 'id="lightbox"')

    def test_a_single_photo_gets_no_thumbnail_strip(self):
        listing = self.make_listing(photos=1)
        response = self.client.get(listing.get_absolute_url())
        self.assertNotContains(response, 'data-thumb data-index')
        self.assertNotContains(response, 'class="thumbs"')

    def test_cards_show_the_cover_and_a_photo_count(self):
        listing = self.make_listing(photos=2)
        response = self.client.get(reverse('products:browse'))
        self.assertContains(response, listing.cover.image.url)
        self.assertContains(response, '2 photos')

    def test_cover_is_the_lowest_ordered_photo(self):
        listing = self.make_listing(photos=0)
        late = ListingImage.objects.create(
            listing=listing, image=an_image('late.jpg'), order=5
        )
        early = ListingImage.objects.create(
            listing=listing, image=an_image('early.jpg'), order=1
        )
        self.assertEqual(listing.cover, early)
        self.assertTrue(early.is_cover)
        self.assertFalse(late.is_cover)


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


class HomeTests(ListingTestBase):
    def test_sold_listings_are_not_in_the_public_grid(self):
        self.make_listing(title='Sold hoodie', status=Listing.Status.SOLD)
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'Sold hoodie')

    def test_hero_search_submits_to_the_browse_page(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, f'action="{reverse("products:browse")}"')

    def test_category_chips_link_to_the_category_pages(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, self.category.get_absolute_url())


class BrowseBase(ListingTestBase):
    """Three listings covering the types, categories and conditions we filter on."""

    def setUp(self):
        self.electronics, _ = Category.objects.get_or_create(
            slug='electronics', defaults={'name': 'Electronics', 'ordering': 2}
        )
        self.calculus = self.make_listing(title='Calculus 8th ed', price=1800)
        self.casio = self.make_listing(
            title='Casio fx-991ES',
            description='Scientific calculator.',
            category=self.electronics,
            price=900,
            condition=Listing.Condition.NEW,
        )
        self.lamp = self.make_listing(
            title='Desk lamp',
            listing_type=Listing.ListingType.FREE,
            price=None,
        )

    def browse(self, **params):
        return self.client.get(reverse('products:browse'), params)

    def titles(self, response):
        return [listing.title for listing in response.context['listings']]


class BrowseTests(BrowseBase):
    """The /browse/ page: searching, filtering, sorting and paging."""

    def test_search_matches_the_title(self):
        response = self.browse(q='calculus')
        self.assertEqual(self.titles(response), ['Calculus 8th ed'])

    def test_search_also_matches_the_description(self):
        response = self.browse(q='scientific')
        self.assertEqual(self.titles(response), ['Casio fx-991ES'])

    def test_filter_by_category(self):
        response = self.browse(category=self.electronics.pk)
        self.assertEqual(self.titles(response), ['Casio fx-991ES'])

    def test_filter_by_listing_type(self):
        response = self.browse(listing_type='FREE')
        self.assertEqual(self.titles(response), ['Desk lamp'])

    def test_filter_by_condition(self):
        response = self.browse(condition='NEW')
        self.assertEqual(self.titles(response), ['Casio fx-991ES'])

    def test_filter_by_price_range(self):
        response = self.browse(min_price='1000', max_price='2000')
        self.assertEqual(self.titles(response), ['Calculus 8th ed'])

    def test_min_above_max_is_a_form_error_and_does_not_filter(self):
        response = self.browse(min_price='5000', max_price='100')
        self.assertFormError(
            response.context['search_form'], 'min_price',
            'The lowest price cannot be above the highest.',
        )
        self.assertEqual(len(self.titles(response)), 3)

    def test_sort_by_price_ascending_puts_free_items_last(self):
        response = self.browse(sort='price_asc')
        self.assertEqual(
            self.titles(response),
            ['Casio fx-991ES', 'Calculus 8th ed', 'Desk lamp'],
        )

    def test_sort_by_price_descending(self):
        response = self.browse(sort='price_desc')
        self.assertEqual(
            self.titles(response)[:2], ['Calculus 8th ed', 'Casio fx-991ES']
        )

    def test_default_sort_is_newest_first(self):
        response = self.browse()
        self.assertEqual(self.titles(response)[0], 'Desk lamp')

    def test_sold_listings_are_hidden_by_default(self):
        self.make_listing(title='Sold hoodie', status=Listing.Status.SOLD)
        self.assertNotIn('Sold hoodie', self.titles(self.browse()))

    def test_show_sold_includes_them(self):
        self.make_listing(title='Sold hoodie', status=Listing.Status.SOLD)
        self.assertIn('Sold hoodie', self.titles(self.browse(show_sold='on')))

    def test_reserved_listings_still_show(self):
        self.make_listing(title='Held kettle', status=Listing.Status.RESERVED)
        self.assertIn('Held kettle', self.titles(self.browse()))

    def test_filters_combine(self):
        response = self.browse(q='casio', category=self.electronics.pk, condition='NEW')
        self.assertEqual(self.titles(response), ['Casio fx-991ES'])

    def test_active_filter_chips_drop_only_their_own_parameter(self):
        response = self.browse(q='casio', listing_type='SELL')
        chips = {chip['param']: chip['query'] for chip in response.context['active_filters']}
        self.assertEqual(sorted(chips), ['listing_type', 'q'])
        self.assertIn('listing_type=SELL', chips['q'])
        self.assertNotIn('q=casio', chips['q'])

    def test_pagination_is_twelve_per_page_and_keeps_the_query(self):
        for index in range(15):
            self.make_listing(title=f'Extra notebook {index}')

        response = self.browse(q='notebook')
        self.assertEqual(len(self.titles(response)), 12)
        self.assertEqual(response.context['result_count'], 15)
        # The pagination links carry the search along.
        self.assertEqual(response.context['querystring'], 'q=notebook')
        self.assertContains(response, 'page=2&amp;q=notebook')

        page_two = self.browse(q='notebook', page='2')
        self.assertEqual(len(self.titles(page_two)), 3)

    def test_result_count_is_the_whole_result_set_not_the_page(self):
        for index in range(15):
            self.make_listing(title=f'Extra notebook {index}')
        response = self.browse()
        self.assertEqual(response.context['result_count'], 18)
        self.assertEqual(len(self.titles(response)), 12)


class CategoryPageTests(BrowseBase):
    """/c/<slug>/ is the same view with the category fixed by the URL."""

    def test_shows_only_that_category(self):
        response = self.client.get(self.electronics.get_absolute_url())
        self.assertEqual(self.titles(response), ['Casio fx-991ES'])
        self.assertEqual(response.context['category'], self.electronics)

    def test_the_category_filter_is_not_offered_twice(self):
        response = self.client.get(self.electronics.get_absolute_url())
        self.assertNotIn('category', response.context['search_form'].fields)

    def test_other_filters_still_apply(self):
        response = self.client.get(
            self.category.get_absolute_url(), {'listing_type': 'FREE'}
        )
        self.assertEqual(self.titles(response), ['Desk lamp'])

    def test_unknown_category_is_a_404(self):
        response = self.client.get('/c/no-such-category/')
        self.assertEqual(response.status_code, 404)


class ImageProcessingTests(TestCase):
    """products/imaging.py: downscaling and EXIF stripping."""

    def test_large_uploads_are_downscaled(self):
        processed = process_upload(an_image('big.jpg', size=(3000, 2000)))
        with Image.open(processed) as image:
            self.assertEqual(image.width, MAX_DIMENSION)
            self.assertEqual(image.height, 1067)  # aspect ratio kept

    def test_small_enough_uploads_keep_their_size(self):
        processed = process_upload(an_image('ok.jpg', size=(800, 600)))
        with Image.open(processed) as image:
            self.assertEqual(image.size, (800, 600))

    def test_exif_metadata_is_stripped(self):
        source = Image.new('RGB', (900, 700), (10, 20, 30))
        exif = source.getexif()
        exif[0x010F] = 'CampusSwap Test Camera'   # Make
        exif[0x0112] = 1                          # Orientation
        buffer = BytesIO()
        source.save(buffer, format='JPEG', exif=exif)
        upload = SimpleUploadedFile(
            'withexif.jpg', buffer.getvalue(), content_type='image/jpeg'
        )

        # The metadata is really there to begin with.
        with Image.open(upload) as before:
            self.assertEqual(before.getexif().get(0x010F), 'CampusSwap Test Camera')

        processed = process_upload(upload)
        with Image.open(processed) as after:
            self.assertEqual(dict(after.getexif()), {})

    def test_a_rotated_photo_is_uprighted_before_the_exif_goes(self):
        source = Image.new('RGB', (900, 600), (10, 20, 30))
        exif = source.getexif()
        exif[0x0112] = 6  # "rotate 90 degrees clockwise"
        buffer = BytesIO()
        source.save(buffer, format='JPEG', exif=exif)

        processed = process_upload(SimpleUploadedFile('rot.jpg', buffer.getvalue()))
        with Image.open(processed) as image:
            # Landscape became portrait, so the rotation was applied for real
            # rather than left to a flag that is now gone.
            self.assertEqual(image.size, (600, 900))

    def test_transparency_is_flattened_onto_white(self):
        source = Image.new('RGBA', (800, 600), (255, 0, 0, 0))
        buffer = BytesIO()
        source.save(buffer, format='PNG')

        processed = process_upload(SimpleUploadedFile('clear.png', buffer.getvalue()))
        with Image.open(processed) as image:
            self.assertEqual(image.mode, 'RGB')
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))

    def test_too_small_is_rejected(self):
        with self.assertRaises(ImageTooSmall):
            process_upload(an_image('tiny.jpg', size=(200, 150)))

    def test_a_file_that_is_not_an_image_is_rejected(self):
        upload = SimpleUploadedFile(
            'fake.jpg', b'this is not an image', content_type='image/jpeg'
        )
        with self.assertRaises(UnidentifiedImageError):
            process_upload(upload)

    def test_everything_is_stored_as_jpeg(self):
        processed = process_upload(
            an_image('photo.PNG', size=(800, 600), image_format='PNG')
        )
        self.assertEqual(processed.name, 'photo.jpg')

    def test_a_decompression_bomb_is_a_form_error_not_a_crash(self):
        """A small file that decodes to an enormous bitmap.

        Pillow's own pixel ceiling is lowered here rather than crafting a real
        bomb, which would mean shipping a file designed to exhaust memory. The
        path under test is the same one: Image.open raises
        DecompressionBombError and process_upload turns it into ImageTooLarge.
        """
        with mock.patch.object(Image, 'MAX_IMAGE_PIXELS', 100):
            with self.assertRaises(ImageTooLarge):
                process_upload(an_image('bomb.png', size=(600, 450)))

    def test_a_directory_traversal_filename_cannot_escape_the_media_folder(self):
        """The stored name is rebuilt from the stem, so any path part is lost."""
        processed = process_upload(an_image('../../../etc/passwd.jpg'))
        self.assertEqual(processed.name, 'passwd.jpg')


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
