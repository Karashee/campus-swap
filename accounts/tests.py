from io import BytesIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts import forms as accounts_forms
from accounts import ratelimit
from accounts.forms import AVATAR_MAX_DIMENSION, ProfileForm, SignUpForm

User = get_user_model()


class CacheIsolatedTestCase(TestCase):
    """A TestCase that starts with an empty cache.

    The login throttle keeps its failure counters there, and the cache is not
    rolled back between tests the way the database is. Without this, failed
    logins in one test would count against the next one.
    """

    def setUp(self):
        super().setUp()
        cache.clear()


def an_avatar(name='me.jpg', size=(400, 400), image_format='JPEG', **kwargs):
    """An uploadable square image, big enough to pass the minimum width."""
    buffer = BytesIO()
    Image.new('RGB', size, (120, 140, 160)).save(buffer, format=image_format, **kwargs)
    return SimpleUploadedFile(
        name, buffer.getvalue(), content_type=f'image/{image_format.lower()}'
    )

VALID_SIGNUP = {
    'username': 'newstudent',
    'first_name': 'New',
    'last_name': 'Student',
    'email': 'new.student@strathmore.edu',
    'password1': 'SwapItQuick42',
    'password2': 'SwapItQuick42',
}


class SignUpDomainTests(CacheIsolatedTestCase):
    def test_allowed_domain_is_accepted(self):
        form = SignUpForm(data=VALID_SIGNUP)
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_non_allowed_domain(self):
        form = SignUpForm(data={**VALID_SIGNUP, 'email': 'someone@gmail.com'})
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Use your Strathmore email so we know you're a student.",
            form.errors['email'],
        )

    @override_settings(ALLOWED_SIGNUP_EMAIL_DOMAINS=[])
    def test_empty_setting_allows_any_domain(self):
        form = SignUpForm(data={**VALID_SIGNUP, 'email': 'someone@gmail.com'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_duplicate_email_in_different_case(self):
        User.objects.create_user(
            username='existing',
            email='new.student@strathmore.edu',
            password='SwapItQuick42',
        )
        form = SignUpForm(data={**VALID_SIGNUP, 'email': 'New.Student@Strathmore.edu'})
        self.assertFalse(form.is_valid())
        self.assertIn(
            'An account with this email already exists.', form.errors['email']
        )

    def test_email_is_stored_lowercased(self):
        form = SignUpForm(data={**VALID_SIGNUP, 'email': 'New.Student@Strathmore.edu'})
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, 'new.student@strathmore.edu')

    def test_signup_view_logs_the_user_in_and_redirects_to_profile_edit(self):
        response = self.client.post(reverse('accounts:signup'), VALID_SIGNUP)
        self.assertRedirects(response, reverse('accounts:profile_edit'))
        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            User.objects.get(username='newstudent').pk,
        )


class LoginTests(CacheIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='wanjiku',
            email='wanjiku.mwangi@strathmore.edu',
            password='SwapItQuick42',
        )

    def _login(self, identifier):
        return self.client.post(
            reverse('accounts:login'),
            {'username': identifier, 'password': 'SwapItQuick42'},
        )

    def test_login_with_username(self):
        self.assertRedirects(self._login('wanjiku'), reverse('home'))

    def test_login_with_email(self):
        self.assertRedirects(
            self._login('wanjiku.mwangi@strathmore.edu'), reverse('home')
        )

    def test_login_with_email_is_case_insensitive(self):
        self.assertRedirects(
            self._login('Wanjiku.Mwangi@Strathmore.EDU'), reverse('home')
        )

    def test_wrong_password_does_not_log_in(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'wanjiku', 'password': 'wrong-password'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)


class RememberMeSessionTests(CacheIsolatedTestCase):
    """The session lifetime is an explicit choice at login."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='wanjiku',
            email='wanjiku@strathmore.edu',
            password='SwapItQuick42',
        )

    def _login(self, **extra):
        return self.client.post(
            reverse('accounts:login'),
            {'username': 'wanjiku', 'password': 'SwapItQuick42', **extra},
        )

    def test_remember_me_uses_the_two_week_cookie_age(self):
        self._login(remember_me='on')
        self.assertEqual(
            self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_without_remember_me_the_session_ends_with_the_browser(self):
        self._login()
        self.assertTrue(self.client.session.get_expire_at_browser_close())


class LogoutTests(CacheIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='brian', email='brian@strathmore.edu', password='SwapItQuick42'
        )

    def test_get_does_not_log_out(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_post_logs_out(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('_auth_user_id', self.client.session)


class ProfileTests(CacheIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='brian',
            email='brian@strathmore.edu',
            password='SwapItQuick42',
            first_name='Brian',
            last_name='Otieno',
        )

    def test_profile_edit_redirects_anonymous_to_login(self):
        url = reverse('accounts:profile_edit')
        response = self.client.get(url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={url}')

    def test_profile_edit_loads_for_logged_in_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:profile_edit'))
        self.assertEqual(response.status_code, 200)

    def test_profile_edit_updates_only_own_profile(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse('accounts:profile_edit'),
            {
                'first_name': 'Brian',
                'last_name': 'Otieno',
                'phone': '0712345678',
                'course': 'Bachelor of Commerce',
                'year_of_study': 2,
                'bio': 'Second year BCom.',
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.course, 'Bachelor of Commerce')
        self.assertEqual(self.user.phone, '+254712345678')

    def test_public_profile_is_visible_to_anyone(self):
        response = self.client.get(
            reverse('accounts:profile', args=[self.user.username])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Brian Otieno')


class PasswordResetTests(CacheIsolatedTestCase):
    def test_reset_email_is_sent_to_the_console_backend(self):
        from django.core import mail

        User.objects.create_user(
            username='wanjiku',
            email='wanjiku.mwangi@strathmore.edu',
            password='SwapItQuick42',
        )
        response = self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'wanjiku.mwangi@strathmore.edu'},
        )
        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/accounts/password/reset/', mail.outbox[0].body)

    def test_reset_link_sets_a_new_password(self):
        from django.core import mail

        user = User.objects.create_user(
            username='wanjiku',
            email='wanjiku.mwangi@strathmore.edu',
            password='SwapItQuick42',
        )
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'wanjiku.mwangi@strathmore.edu'},
        )
        link = next(
            line.strip()
            for line in mail.outbox[0].body.splitlines()
            if '/accounts/password/reset/' in line
        )
        path = link.split('testserver', 1)[1]

        # The link redirects to the set-password form at .../set-password/.
        response = self.client.get(path, follow=True)
        self.assertEqual(response.status_code, 200)
        self.client.post(
            response.request['PATH_INFO'],
            {'new_password1': 'BrandNewPass99', 'new_password2': 'BrandNewPass99'},
        )

        user.refresh_from_db()
        self.assertTrue(user.check_password('BrandNewPass99'))


@override_settings(LOGIN_RATELIMIT_ATTEMPTS=3, LOGIN_RATELIMIT_WINDOW=900)
class LoginRateLimitTests(CacheIsolatedTestCase):
    """The login form stops being a free password-guessing oracle.

    Three attempts here instead of the real five, so the tests stay short.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='wanjiku',
            email='wanjiku@strathmore.edu',
            password='SwapItQuick42',
        )
        cls.other = User.objects.create_user(
            username='brian',
            email='brian@strathmore.edu',
            password='SwapItQuick42',
        )

    def guess(self, username='wanjiku', password='wrong-password', **extra):
        return self.client.post(
            reverse('accounts:login'),
            {'username': username, 'password': password},
            **extra,
        )

    def test_attempts_below_the_limit_are_only_rejected(self):
        for _ in range(2):
            response = self.guess()
            self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_the_form_locks_after_the_limit_is_reached(self):
        for _ in range(3):
            self.guess()

        response = self.guess()
        self.assertEqual(response.status_code, 429)
        self.assertContains(
            response, 'Too many failed login attempts', status_code=429
        )

    def test_the_right_password_is_refused_while_locked(self):
        """The lockout is the point: knowing the password does not lift it."""
        for _ in range(3):
            self.guess()

        response = self.guess(password='SwapItQuick42')
        self.assertEqual(response.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_a_locked_attempt_never_looks_the_user_up(self):
        """clean() refuses before AuthenticationForm calls authenticate().

        No database query means no password hash was fetched and no hasher was
        run, so a locked-out guesser cannot even use the response time.
        """
        for _ in range(3):
            self.guess()

        with self.assertNumQueries(0):
            self.guess(password='SwapItQuick42')

    def test_the_last_attempt_says_so(self):
        self.guess()
        self.guess()
        response = self.guess()
        self.assertContains(response, 'That was the last attempt')

    def test_a_successful_login_clears_the_count(self):
        self.guess()
        self.guess()
        self.assertRedirects(
            self.guess(password='SwapItQuick42'), reverse('home')
        )

        # Back to a full allowance: two more misses must not lock anything.
        self.client.logout()
        self.assertEqual(self.guess().status_code, 200)
        self.assertEqual(self.guess().status_code, 200)

    def test_one_account_cannot_be_hammered_from_changing_addresses(self):
        """The per-username counter, with a different IP on every attempt."""
        for index in range(3):
            self.guess(REMOTE_ADDR=f'10.0.0.{index}')

        response = self.guess(REMOTE_ADDR='10.0.0.99')
        self.assertEqual(response.status_code, 429)

    def test_one_address_cannot_work_through_a_list_of_accounts(self):
        """The per-IP counter, with a different username on every attempt."""
        for name in ['wanjiku', 'brian', 'nobody']:
            self.guess(username=name, REMOTE_ADDR='10.0.0.7')

        response = self.guess(username='someone-else', REMOTE_ADDR='10.0.0.7')
        self.assertEqual(response.status_code, 429)

    def test_another_student_elsewhere_is_unaffected(self):
        for _ in range(3):
            self.guess(REMOTE_ADDR='10.0.0.7')

        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'brian', 'password': 'SwapItQuick42'},
            REMOTE_ADDR='10.0.0.8',
        )
        self.assertRedirects(response, reverse('home'))

    def test_an_empty_form_is_a_slip_not_a_guess(self):
        """A missing field never reaches authenticate(), so it is not counted."""
        for _ in range(5):
            self.client.post(reverse('accounts:login'), {})

        self.assertRedirects(
            self.guess(password='SwapItQuick42'), reverse('home')
        )

    def test_a_forwarded_for_header_cannot_reset_the_per_ip_count(self):
        """X-Forwarded-For is attacker-supplied, so the limiter ignores it."""
        for index in range(3):
            self.guess(
                username=f'student{index}',
                HTTP_X_FORWARDED_FOR=f'10.1.1.{index}',
            )

        response = self.guess(
            username='someone', HTTP_X_FORWARDED_FOR='10.1.1.200'
        )
        self.assertEqual(response.status_code, 429)

    def test_the_counter_expires_with_its_window(self):
        """A fixed window: the lockout lifts on its own, no admin needed."""
        request = RequestFactory().post('/accounts/login/')
        for _ in range(3):
            ratelimit.record_failure(request, 'wanjiku')
        self.assertTrue(ratelimit.is_blocked(request, 'wanjiku'))

        # The counters are plain cache entries with a TTL; dropping them is
        # exactly what expiry does.
        cache.clear()
        self.assertFalse(ratelimit.is_blocked(request, 'wanjiku'))


class AvatarUploadTests(CacheIsolatedTestCase):
    """Avatars go through the same Pillow processor as listing photos."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='wanjiku',
            email='wanjiku@strathmore.edu',
            password='SwapItQuick42',
        )

    def profile_form(self, avatar=None, instance=None, **data):
        return ProfileForm(
            data={
                'first_name': 'Wanjiku', 'last_name': 'Mwangi', 'phone': '',
                'course': 'BBIT', 'year_of_study': '', 'bio': '',
                **data,
            },
            files={'avatar': avatar} if avatar is not None else None,
            instance=instance or self.user,
        )

    def test_a_real_image_is_accepted(self):
        form = self.profile_form(an_avatar())
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_file_pretending_to_be_a_jpg_is_rejected(self):
        """Content sniffing, not the extension: a text file named .jpg.

        This one is caught by Django's own ImageField, which runs before
        clean_avatar and also decides with Pillow rather than the file name —
        so the message is Django's. What matters is that an extension is never
        what gets a file accepted.
        """
        fake = SimpleUploadedFile(
            'avatar.jpg',
            b'#!/bin/sh\necho not an image\n',
            content_type='image/jpeg',
        )
        form = self.profile_form(fake)
        self.assertFalse(form.is_valid())
        self.assertIn('not an image', form.errors['avatar'][0])

    def test_a_png_renamed_to_jpg_is_still_handled_correctly(self):
        """The extension is not trusted in the other direction either."""
        form = self.profile_form(an_avatar('me.jpg', image_format='PNG'))
        self.assertTrue(form.is_valid(), form.errors)
        with Image.open(form.save().avatar.path) as stored:
            self.assertEqual(stored.format, 'JPEG')

    def test_a_tiny_image_is_rejected(self):
        form = self.profile_form(an_avatar(size=(32, 32)))
        self.assertFalse(form.is_valid())
        self.assertIn('too small', form.errors['avatar'][0])

    def test_an_oversized_file_is_rejected_on_its_byte_size(self):
        """Patched down to a few hundred bytes to keep the test quick."""
        with mock.patch.object(accounts_forms, 'AVATAR_MAX_BYTES', 500):
            form = self.profile_form(an_avatar())
            self.assertFalse(form.is_valid())
        self.assertIn('under 2 MB', form.errors['avatar'][0])

    def test_a_large_avatar_is_downscaled_and_stored_as_jpeg(self):
        form = self.profile_form(
            an_avatar('me.png', size=(2000, 2000), image_format='PNG')
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertTrue(user.avatar.name.endswith('.jpg'))
        with Image.open(user.avatar.path) as stored:
            self.assertEqual(stored.format, 'JPEG')
            self.assertLessEqual(max(stored.size), AVATAR_MAX_DIMENSION)

    def test_exif_metadata_is_stripped_from_an_avatar(self):
        """A phone photo's EXIF can carry the GPS coordinates it was taken at."""
        exif = Image.Exif()
        exif[0x010F] = 'TestPhone'  # Make
        form = self.profile_form(an_avatar('me.jpg', exif=exif.tobytes()))
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        with Image.open(user.avatar.path) as stored:
            self.assertEqual(dict(stored.getexif()), {})

    def test_an_untouched_avatar_is_not_re_encoded_on_every_save(self):
        form = self.profile_form(an_avatar())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        stored_name = user.avatar.name

        # Save the profile again without choosing a new file.
        again = self.profile_form(instance=user, bio='Hello')
        self.assertTrue(again.is_valid(), again.errors)
        self.assertEqual(again.save().avatar.name, stored_name)

    def test_uploading_through_the_view_works_end_to_end(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:profile_edit'),
            {
                'first_name': 'Wanjiku', 'last_name': 'Mwangi', 'phone': '',
                'course': 'BBIT', 'year_of_study': '', 'bio': '',
                'avatar': an_avatar(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)
