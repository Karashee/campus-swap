from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.forms import SignUpForm

User = get_user_model()

VALID_SIGNUP = {
    'username': 'newstudent',
    'first_name': 'New',
    'last_name': 'Student',
    'email': 'new.student@strathmore.edu',
    'password1': 'SwapItQuick42',
    'password2': 'SwapItQuick42',
}


class SignUpDomainTests(TestCase):
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


class LoginTests(TestCase):
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


class LogoutTests(TestCase):
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


class ProfileTests(TestCase):
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


class PasswordResetTests(TestCase):
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
