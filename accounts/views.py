from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import UpdateView

from config.redirects import NEXT_PARAM, safe_next_url
from products.models import Listing

from . import ratelimit
from .forms import LoginForm, ProfileForm, SignUpForm

User = get_user_model()


def signup(request):
    """Register a student, log them straight in, nudge them to finish the profile.

    A student who was sent here from a listing ("log in to contact the seller")
    carries a ``next`` along, so sign-up finishes where they were headed rather
    than on the profile form. The target is validated, never trusted.
    """
    if request.user.is_authenticated:
        return redirect('home')

    # Where to go afterwards: the page they came from if it is ours, otherwise
    # the profile form, which is where a brand-new account should start.
    destination = safe_next_url(request, reverse('accounts:profile_edit'))

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='accounts.backends.EmailOrUsernameBackend')
            messages.success(request, f'Welcome to CampusSwap, {user.display_name}.')
            if destination == reverse('accounts:profile_edit'):
                messages.info(
                    request, 'Add your course and phone so buyers can reach you.'
                )
            return redirect(destination)
    else:
        form = SignUpForm()

    return render(request, 'registration/signup.html', {
        'form': form,
        # Echoed into the form's hidden field so it survives a failed
        # submission (auth_base.html renders it when set). Deliberately the
        # raw value: autoescaping makes it safe in the attribute, and it is
        # validated again by safe_next_url on the next POST, so a hostile one
        # round-trips harmlessly rather than being silently swapped.
        NEXT_PARAM: request.POST.get(NEXT_PARAM) or request.GET.get(NEXT_PARAM, ''),
    })


class CampusLoginView(auth_views.LoginView):
    """Django's LoginView plus a session-lifetime choice and a login throttle.

    LoginView already validates its own ``next`` against the current host, so
    the redirect side needs nothing extra here. What it does not do is limit
    how many passwords someone may try, which is what accounts.ratelimit adds.
    """

    template_name = 'registration/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    #: Set per request in post(). True once the attempts have been used up.
    locked_out = False

    def attempted_username(self):
        """Whatever was typed in the identifier field, if anything."""
        return self.request.POST.get('username', '')

    def post(self, request, *args, **kwargs):
        """Check the throttle before the form, and answer 429 when it bites."""
        self.locked_out = ratelimit.is_blocked(request, self.attempted_username())
        response = super().post(request, *args, **kwargs)
        if self.locked_out and response.status_code == 200:
            # The page re-renders with the lockout message; the status code
            # should say what happened as well, not just the HTML.
            response.status_code = 429
        return response

    def get_form_kwargs(self):
        """Hand the lockout to the form, which refuses before it authenticates.

        Doing it this way rather than tacking an error onto a validated form
        means the password is never checked at all while the account is locked,
        so a guesser also stops learning anything from the response.
        """
        kwargs = super().get_form_kwargs()
        if self.locked_out:
            kwargs['locked_out_message'] = (
                'Too many failed login attempts. Wait about '
                f'{ratelimit.retry_after_minutes()} minutes and try again, or '
                'reset your password.'
            )
        return kwargs

    def form_valid(self, form):
        # The right password: wipe the slate for this account and address.
        ratelimit.clear(self.request, self.attempted_username())

        # super() calls auth.login(), which cycles the session key, so the
        # expiry has to be set after that or it would be discarded.
        response = super().form_valid(form)
        if form.cleaned_data.get('remember_me'):
            # Fall back to SESSION_COOKIE_AGE (two weeks).
            self.request.session.set_expiry(None)
        else:
            # 0 means "expire when the browser closes".
            self.request.session.set_expiry(0)
        return response

    def form_invalid(self, form):
        """Count the attempt, and say so once it was the last one.

        Only credential failures are counted. An empty form or a missing field
        is a slip, not a guess, and an attempt that was already refused by the
        throttle was never checked, so neither eats into the allowance.
        """
        if not self.locked_out and form.non_field_errors():
            used_up = ratelimit.record_failure(self.request, self.attempted_username())
            if used_up:
                form.add_error(
                    None,
                    'That was the last attempt. The login form is locked for '
                    f'about {ratelimit.retry_after_minutes()} minutes.',
                )
        return super().form_invalid(form)


def profile_detail(request, username):
    """Public profile: who they are plus the items they currently have up."""
    # is_active filters out accounts an admin has disabled: a suspended student
    # should not keep a public page on the site.
    profile_user = get_object_or_404(User, username__iexact=username, is_active=True)
    listings = (
        profile_user.listings
        .select_related('seller', 'category')
        .prefetch_related('images')
        .filter(status=Listing.Status.AVAILABLE)
    )
    return render(
        request,
        'accounts/profile_detail.html',
        {
            'profile_user': profile_user,
            'listings': listings,
            'listing_count': listings.count(),
        },
    )


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Edit your own profile. Always operates on request.user, never on a pk."""

    form_class = ProfileForm
    template_name = 'accounts/profile_form.html'
    success_url = reverse_lazy('accounts:profile_edit')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated.')
        return super().form_valid(form)
