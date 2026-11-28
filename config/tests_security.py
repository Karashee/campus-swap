"""Site-wide security tests: the B7 audit, written down as assertions.

These are deliberately kept together rather than spread through the app test
modules, because the point of them is coverage of the *whole* URL map. If a
later chunk adds a view and forgets to protect it, the tables below are where
that shows up: a new named URL that is not listed in one of them fails
``test_every_url_is_accounted_for``.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase
from django.urls import get_resolver, reverse
from rest_framework.authtoken.models import Token

from config.redirects import safe_next_url
from products.models import Category, Listing, ListingImage

from products.tests import an_image

User = get_user_model()


class SecurityTestBase(TestCase):
    """Two students, a category and a listing owned by the first of them."""

    def setUp(self):
        super().setUp()
        # The login throttle's counters live in the cache, which is not rolled
        # back between tests the way the database is.
        cache.clear()

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='wanjiku',
            email='wanjiku@strathmore.edu',
            password='SwapItQuick42',
        )
        cls.other = User.objects.create_user(
            username='brian',
            email='brian@strathmore.edu',
            password='SwapItQuick42',
        )
        cls.staff = User.objects.create_user(
            username='admin',
            email='admin@strathmore.edu',
            password='SwapItQuick42',
            is_staff=True,
            is_superuser=True,
        )
        cls.category, _ = Category.objects.get_or_create(
            slug='textbooks', defaults={'name': 'Textbooks', 'ordering': 1}
        )
        cls.listing = Listing.objects.create(
            seller=cls.owner,
            title='Calculus 8th ed',
            description='Used for one semester.',
            category=cls.category,
            condition=Listing.Condition.GOOD,
            listing_type=Listing.ListingType.SELL,
            price=1800,
            meetup_spot='Library entrance',
        )
        ListingImage.objects.create(
            listing=cls.listing, image=an_image('cover.jpg'), order=0
        )


#: Pages anyone may read, named URL -> kwargs.
PUBLIC_URLS = {
    'home': {},
    'products:browse': {},
    'products:category': {'slug': 'textbooks'},
    'products:detail': {'slug': None},  # filled in from the test listing
    'accounts:login': {},
    'accounts:signup': {},
    'accounts:profile': {'username': 'wanjiku'},
    'accounts:password_reset': {},
    'accounts:password_reset_done': {},
    'accounts:password_reset_complete': {},
}

#: Pages that must bounce an anonymous visitor to the login page.
LOGIN_REQUIRED_URLS = {
    'products:create': {},
    'products:my_listings': {},
    'products:edit': {'slug': None},
    'products:delete': {'slug': None},
    'accounts:profile_edit': {},
    'accounts:password_change': {},
    'accounts:password_change_done': {},
}

#: Owner-only pages: a logged-in student who does not own the listing must get
#: a 404, not a 403, so the existence of someone else's listing is not
#: confirmed by the response.
OWNER_ONLY_URLS = {
    'products:edit': {'slug': None},
    'products:delete': {'slug': None},
}

#: API endpoints anyone may read (chunk B8). The API is a second door onto the
#: same data, so it gets its own row in the audit rather than being assumed to
#: inherit the web pages' checks.
API_PUBLIC_URLS = {
    'api:api-root': {},
    'api:schema': {},
    'api:docs': {},
    'api:category-list': {},
    'api:category-detail': {'slug': 'textbooks'},
    'api:listing-list': {},
    'api:listing-detail': {'slug': None},
}

#: API endpoints that must refuse a write from a client who is not the owner.
#: The value is the method to try, since there is no page to GET.
API_OWNER_ONLY_WRITES = {
    'api:listing-detail': ('patch', {'slug': None}),
}

#: Named URLs that are intentionally not in any table above, with the reason.
UNCHECKED_URLS = {
    # POST-only, so it has its own tests rather than a GET check.
    'products:mark_status': 'POST-only, covered by MarkStatusTests',
    'accounts:logout': 'POST-only, covered by LogoutTests',
    # Reached only through a one-time emailed token.
    'accounts:password_reset_confirm': 'token URL, covered by PasswordResetTests',
    # POST-only: it swaps a password for an API token.
    'api:token': 'POST-only, covered by api.tests.ApiAuthenticationTests',
}


def _fill(kwargs, slug):
    """Substitute the test listing's slug for the None placeholders."""
    return {
        key: (slug if value is None else value) for key, value in kwargs.items()
    }


class UrlCoverageTests(SecurityTestBase):
    """Every named URL in the project appears in one of the tables above."""

    def test_every_url_is_accounted_for(self):
        resolver = get_resolver()
        named = set()
        for key in resolver.reverse_dict:
            if isinstance(key, str):
                named.add(key)
        for namespace, (prefix, sub) in resolver.namespace_dict.items():
            for key in sub.reverse_dict:
                if isinstance(key, str):
                    named.add(f'{namespace}:{key}')

        covered = (
            set(PUBLIC_URLS)
            | set(LOGIN_REQUIRED_URLS)
            | set(OWNER_ONLY_URLS)
            | set(API_PUBLIC_URLS)
            | set(API_OWNER_ONLY_WRITES)
            | set(UNCHECKED_URLS)
        )
        # The admin registers a long list of its own names; it is tested
        # separately in AdminAccessTests.
        named = {name for name in named if not name.startswith('admin:')}

        self.assertEqual(
            named - covered,
            set(),
            'These named URLs have no security test. Add them to PUBLIC_URLS, '
            'LOGIN_REQUIRED_URLS, OWNER_ONLY_URLS or UNCHECKED_URLS.',
        )


class PublicAccessTests(SecurityTestBase):
    def test_public_pages_load_for_anonymous_visitors(self):
        for name, kwargs in PUBLIC_URLS.items():
            kwargs = _fill(kwargs, self.listing.slug)
            with self.subTest(url=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)

    def test_a_disabled_account_has_no_public_profile(self):
        self.other.is_active = False
        self.other.save(update_fields=['is_active'])
        response = self.client.get(
            reverse('accounts:profile', kwargs={'username': 'brian'})
        )
        self.assertEqual(response.status_code, 404)


class LoginRequiredTests(SecurityTestBase):
    def test_private_pages_redirect_anonymous_visitors_to_login(self):
        login_url = reverse(settings.LOGIN_URL)
        for name, kwargs in LOGIN_REQUIRED_URLS.items():
            kwargs = _fill(kwargs, self.listing.slug)
            with self.subTest(url=name):
                url = reverse(name, kwargs=kwargs)
                response = self.client.get(url)
                self.assertRedirects(
                    response, f'{login_url}?next={url}', fetch_redirect_response=False
                )

    def test_private_pages_load_for_a_logged_in_student(self):
        self.client.force_login(self.owner)
        for name, kwargs in LOGIN_REQUIRED_URLS.items():
            kwargs = _fill(kwargs, self.listing.slug)
            with self.subTest(url=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)


class OwnershipTests(SecurityTestBase):
    """Ownership is enforced in the queryset, not by hiding buttons."""

    def test_a_non_owner_gets_404_on_every_owner_only_page(self):
        self.client.force_login(self.other)
        for name, kwargs in OWNER_ONLY_URLS.items():
            kwargs = _fill(kwargs, self.listing.slug)
            with self.subTest(url=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 404)

    def test_a_non_owner_cannot_change_a_listing_by_posting_directly(self):
        """Hiding the form is not the control; the queryset is."""
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('products:edit', kwargs={'slug': self.listing.slug}),
            {'title': 'Stolen', 'category': self.category.pk,
             'listing_type': 'SELL', 'condition': 'GOOD', 'price': '1',
             'description': 'x', 'meetup_spot': 'y'},
        )
        self.assertEqual(response.status_code, 404)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, 'Calculus 8th ed')

    def test_a_non_owner_cannot_delete_by_posting_directly(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('products:delete', kwargs={'slug': self.listing.slug})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())

    def test_a_non_owner_cannot_change_the_status(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse(
                'products:mark_status',
                kwargs={'slug': self.listing.slug, 'status': 'SOLD'},
            )
        )
        self.assertEqual(response.status_code, 404)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.AVAILABLE)

    def test_the_seller_cannot_be_set_from_posted_data(self):
        """A posted 'seller' is ignored: the view always uses request.user."""
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('products:create'),
            {
                'title': 'Desk lamp', 'category': self.category.pk,
                'listing_type': 'FREE', 'condition': 'GOOD', 'price': '',
                'trade_for': '', 'description': 'Works fine.',
                'meetup_spot': 'Gate B',
                'seller': self.owner.pk,  # the attempt
                'photos-TOTAL_FORMS': '1', 'photos-INITIAL_FORMS': '0',
                'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '5',
                'photos-0-image': an_image('lamp.jpg'), 'photos-0-ORDER': '1',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Listing.objects.get(title='Desk lamp').seller, self.other)

    def test_my_listings_shows_only_your_own(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('products:my_listings'))
        self.assertNotContains(response, 'Calculus 8th ed')


class ApiAccessTests(SecurityTestBase):
    """The API half of the audit (chunk B8).

    The endpoint behaviour is tested in ``api/tests.py``; what matters here is
    that the API does not quietly become a way around the checks the web pages
    make. Anonymous reads are fine, because the same data is on a public page.
    Anonymous writes are not, and neither are writes to someone else's row.
    """

    def test_api_reads_are_public(self):
        for name, kwargs in API_PUBLIC_URLS.items():
            kwargs = _fill(kwargs, self.listing.slug)
            with self.subTest(url=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)

    def test_an_anonymous_client_cannot_write_through_the_api(self):
        payload = {'title': 'Stolen'}
        cases = {
            'create': ('post', reverse('api:listing-list')),
            'replace': ('put', reverse(
                'api:listing-detail', kwargs={'slug': self.listing.slug}
            )),
            'change': ('patch', reverse(
                'api:listing-detail', kwargs={'slug': self.listing.slug}
            )),
            'delete': ('delete', reverse(
                'api:listing-detail', kwargs={'slug': self.listing.slug}
            )),
        }
        for label, (method, url) in cases.items():
            with self.subTest(method=label):
                send = getattr(self.client, method)
                response = (
                    send(url) if method == 'delete'
                    else send(url, payload, 'application/json')
                )
                # 401: no credentials at all, and the response says what kind
                # the API wants.
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response['WWW-Authenticate'], 'Token')

        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, 'Calculus 8th ed')

    def test_a_logged_in_non_owner_cannot_write_to_someone_else_s_listing(self):
        self.client.force_login(self.other)
        for name, (method, kwargs) in API_OWNER_ONLY_WRITES.items():
            kwargs = _fill(kwargs, self.listing.slug)
            with self.subTest(url=name):
                url = reverse(name, kwargs=kwargs)
                response = getattr(self.client, method)(
                    url, {'title': 'Stolen'}, 'application/json'
                )
                self.assertEqual(response.status_code, 403)

        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, 'Calculus 8th ed')

    def test_the_api_does_not_hand_out_contact_details(self):
        """The web page shows a phone number only to a logged-in non-owner."""
        self.owner.phone = '+254712345678'
        self.owner.save(update_fields=['phone'])

        url = reverse('api:listing-detail', kwargs={'slug': self.listing.slug})
        body = self.client.get(url).content.decode()
        self.assertNotIn('+254712345678', body)
        self.assertNotIn('wanjiku@strathmore.edu', body)

    def test_a_session_authenticated_write_still_needs_a_csrf_token(self):
        """Session auth makes the API reachable from a browser, and so a CSRF
        target. DRF's SessionAuthentication enforces the token for us; this is
        the test that says so out loud.
        """
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        response = strict.patch(
            reverse('api:listing-detail', kwargs={'slug': self.listing.slug}),
            {'title': 'Renamed'},
            'application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, 'Calculus 8th ed')

    def test_a_token_authenticated_write_does_not_need_one(self):
        """The counterpart: a token is not a cookie, so CSRF does not apply."""
        token = Token.objects.create(user=self.owner)
        strict = Client(enforce_csrf_checks=True)
        response = strict.patch(
            reverse('api:listing-detail', kwargs={'slug': self.listing.slug}),
            {'title': 'Renamed'},
            'application/json',
            headers={'authorization': f'Token {token.key}'},
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_docs_page_policy_allows_no_inline_code_and_no_third_party(self):
        """B7's CSP still covers /api/docs/, without being loosened for it."""
        policy = self.client.get(reverse('api:docs'))['Content-Security-Policy']
        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertIn("style-src 'self'", policy)
        self.assertNotIn('unsafe-inline', policy)
        self.assertNotIn('unsafe-eval', policy)
        self.assertNotIn('http', policy.replace("'self'", ''))

    def test_the_rest_of_the_site_keeps_its_own_policy(self):
        """The docs page's override must not leak onto other responses."""
        self.client.get(reverse('api:docs'))
        policy = self.client.get(reverse('home'))['Content-Security-Policy']
        self.assertIn('https://fonts.googleapis.com', policy)
        self.assertIn('nonce-', policy)


class AdminAccessTests(SecurityTestBase):
    def test_anonymous_visitors_are_sent_to_the_admin_login(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_an_ordinary_student_cannot_reach_the_admin(self):
        self.client.force_login(self.other)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_a_staff_user_can(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/admin/').status_code, 200)


class CsrfTests(SecurityTestBase):
    """Every state-changing endpoint is POST and rejects a missing token.

    The test client normally skips CSRF checking, which is why these use a
    client built with enforce_csrf_checks=True: without it, a regression here
    would pass silently.
    """

    def setUp(self):
        super().setUp()
        self.strict = Client(enforce_csrf_checks=True)

    def post_targets(self):
        return {
            'accounts:logout': reverse('accounts:logout'),
            'accounts:login': reverse('accounts:login'),
            'accounts:signup': reverse('accounts:signup'),
            'accounts:profile_edit': reverse('accounts:profile_edit'),
            'accounts:password_change': reverse('accounts:password_change'),
            'accounts:password_reset': reverse('accounts:password_reset'),
            'products:create': reverse('products:create'),
            'products:edit': reverse(
                'products:edit', kwargs={'slug': self.listing.slug}
            ),
            'products:delete': reverse(
                'products:delete', kwargs={'slug': self.listing.slug}
            ),
            'products:mark_status': reverse(
                'products:mark_status',
                kwargs={'slug': self.listing.slug, 'status': 'SOLD'},
            ),
        }

    def test_a_post_without_a_csrf_token_is_refused(self):
        self.strict.force_login(self.owner)
        for name, url in self.post_targets().items():
            with self.subTest(url=name):
                response = self.strict.post(url, {})
                self.assertEqual(
                    response.status_code, 403,
                    f'{name} accepted a POST with no CSRF token',
                )

    def test_a_post_with_the_token_from_the_page_is_accepted(self):
        """The counterpart: the protection does not break normal use."""
        self.strict.force_login(self.owner)
        url = reverse('accounts:profile_edit')
        token = self.strict.get(url).context['csrf_token']
        response = self.strict.post(url, {
            'first_name': 'Wanjiku', 'last_name': 'Mwangi', 'phone': '',
            'course': 'BBIT', 'year_of_study': '', 'bio': '',
            'csrfmiddlewaretoken': token,
        })
        self.assertEqual(response.status_code, 302)

    def test_the_logout_form_in_the_navbar_is_a_post_with_a_token(self):
        self.client.force_login(self.owner)
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn(f'action="{reverse("accounts:logout")}"', html)
        self.assertIn('csrfmiddlewaretoken', html)

    def test_logout_ignores_a_get(self):
        self.client.force_login(self.owner)
        self.client.get(reverse('accounts:logout'))
        self.assertIn('_auth_user_id', self.client.session)


class SafeRedirectTests(SecurityTestBase):
    """A ``next`` parameter is attacker-controlled and must be validated."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def test_safe_next_url_accepts_a_path_on_this_site(self):
        request = self.factory.get('/accounts/login/', {'next': '/browse/'})
        self.assertEqual(safe_next_url(request, '/'), '/browse/')

    def test_safe_next_url_rejects_other_hosts_and_schemes(self):
        for hostile in [
            'http://evil.example/phish',
            'https://evil.example/phish',
            '//evil.example/phish',
            'javascript:alert(1)',
            r'\/\/evil.example',
        ]:
            with self.subTest(next=hostile):
                request = self.factory.get('/accounts/login/', {'next': hostile})
                self.assertEqual(safe_next_url(request, '/fallback/'), '/fallback/')

    def test_safe_next_url_falls_back_when_there_is_no_next(self):
        request = self.factory.get('/accounts/login/')
        self.assertEqual(safe_next_url(request, '/fallback/'), '/fallback/')

    def test_login_honours_an_on_site_next(self):
        response = self.client.post(
            f'{reverse("accounts:login")}?next=/browse/',
            {'username': 'wanjiku', 'password': 'SwapItQuick42'},
        )
        self.assertRedirects(response, '/browse/')

    def test_login_ignores_an_off_site_next(self):
        response = self.client.post(
            f'{reverse("accounts:login")}?next=//evil.example/phish',
            {'username': 'wanjiku', 'password': 'SwapItQuick42'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example', response['Location'])
        self.assertEqual(response['Location'], reverse('home'))

    def test_signup_honours_an_on_site_next(self):
        response = self.client.post(
            f'{reverse("accounts:signup")}?next=/browse/',
            {
                'username': 'newstudent', 'first_name': 'New',
                'last_name': 'Student', 'email': 'new.student@strathmore.edu',
                'password1': 'SwapItQuick42', 'password2': 'SwapItQuick42',
            },
        )
        self.assertRedirects(response, '/browse/')

    def test_signup_ignores_an_off_site_next(self):
        response = self.client.post(
            f'{reverse("accounts:signup")}?next=http://evil.example/phish',
            {
                'username': 'newstudent', 'first_name': 'New',
                'last_name': 'Student', 'email': 'new.student@strathmore.edu',
                'password1': 'SwapItQuick42', 'password2': 'SwapItQuick42',
            },
        )
        self.assertRedirects(response, reverse('accounts:profile_edit'))

    def test_the_login_next_survives_into_the_signup_link(self):
        response = self.client.get(f'{reverse("accounts:login")}?next=/browse/')
        self.assertContains(
            response, f'{reverse("accounts:signup")}?next=%2Fbrowse%2F'
        )

    def test_an_anonymous_status_post_is_sent_to_the_listing_not_the_post_url(self):
        """next must be a page they can actually GET after logging in."""
        response = self.client.post(
            reverse(
                'products:mark_status',
                kwargs={'slug': self.listing.slug, 'status': 'SOLD'},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            f'next={self.listing.get_absolute_url()}', response['Location']
        )


class ContentSecurityPolicyTests(SecurityTestBase):
    def test_the_policy_header_is_sent(self):
        policy = self.client.get(reverse('home'))['Content-Security-Policy']
        self.assertIn("default-src 'self'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("base-uri 'self'", policy)
        self.assertIn("form-action 'self'", policy)

    def test_scripts_are_allowed_only_with_the_per_response_nonce(self):
        response = self.client.get(reverse('home'))
        policy = response['Content-Security-Policy']
        nonce = response.context['csp_nonce']

        self.assertIn(f"script-src 'self' 'nonce-{nonce}'", policy)
        # Our own inline block carries it, so the page still works.
        self.assertContains(response, f'<script nonce="{nonce}">')
        # And 'unsafe-inline' is nowhere, or the nonce would be pointless.
        self.assertNotIn('unsafe-inline', policy)
        self.assertNotIn('unsafe-eval', policy)

    def test_the_nonce_changes_between_responses(self):
        first = self.client.get(reverse('home')).context['csp_nonce']
        second = self.client.get(reverse('home')).context['csp_nonce']
        self.assertNotEqual(str(first), str(second))

    def test_the_fonts_the_pages_actually_load_are_allowed(self):
        policy = self.client.get(reverse('home'))['Content-Security-Policy']
        self.assertIn('https://fonts.googleapis.com', policy)
        self.assertIn('https://fonts.gstatic.com', policy)

    def every_page(self):
        """Every page a logged-in student can reach, rendered."""
        self.client.force_login(self.owner)
        urls = [
            reverse('home'),
            reverse('products:browse'),
            reverse('products:category', kwargs={'slug': 'textbooks'}),
            reverse('products:detail', kwargs={'slug': self.listing.slug}),
            reverse('products:create'),
            reverse('products:edit', kwargs={'slug': self.listing.slug}),
            reverse('products:delete', kwargs={'slug': self.listing.slug}),
            reverse('products:my_listings'),
            reverse('accounts:profile_edit'),
            reverse('accounts:password_change'),
            reverse('accounts:profile', kwargs={'username': 'wanjiku'}),
        ]
        for url in urls:
            yield url, self.client.get(url).content.decode()

        # And the two anonymous pages, posted empty so their error boxes
        # render too.
        self.client.logout()
        for url in [reverse('accounts:login'), reverse('accounts:signup')]:
            yield url, self.client.post(url, {}).content.decode()

    def test_every_page_renders_without_an_inline_style_attribute(self):
        """style-src has no 'unsafe-inline', so an inline style would be dropped.

        Rendering each page and checking keeps a future template from quietly
        reintroducing one and losing the styling only in production.
        """
        for url, html in self.every_page():
            with self.subTest(url=url):
                self.assertNotIn('style="', html)

    def test_no_page_leaks_a_template_comment(self):
        """Not CSP, but the same class of mistake and found while testing it.

        Django's {# #} comment is single-line only: spread one over two lines
        and it is rendered to the visitor instead of stripped.
        """
        for url, html in self.every_page():
            with self.subTest(url=url):
                self.assertNotIn('{#', html)
                self.assertNotIn('{%', html)


class SecurityHeaderTests(SecurityTestBase):
    def test_clickjacking_and_sniffing_headers_are_set(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Referrer-Policy'], 'same-origin')


class XssEscapingTests(SecurityTestBase):
    def test_a_script_tag_in_a_listing_is_escaped_not_executed(self):
        """Autoescaping is the first line of defence; the CSP is the second."""
        nasty = '<script>alert("xss")</script>'
        self.listing.title = nasty
        self.listing.description = nasty
        self.listing.save(update_fields=['title', 'description'])

        html = self.client.get(self.listing.get_absolute_url()).content.decode()
        self.assertNotIn(nasty, html)
        self.assertIn('&lt;script&gt;', html)

    def test_a_script_tag_in_a_profile_bio_is_escaped(self):
        self.owner.bio = '<img src=x onerror=alert(1)>'
        self.owner.save(update_fields=['bio'])
        html = self.client.get(
            reverse('accounts:profile', kwargs={'username': 'wanjiku'})
        ).content.decode()
        self.assertNotIn('<img src=x onerror', html)
        self.assertIn('&lt;img src=x onerror', html)
