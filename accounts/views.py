from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from products.models import Listing

from .forms import LoginForm, ProfileForm, SignUpForm

User = get_user_model()


def signup(request):
    """Register a student, log them straight in, nudge them to finish the profile."""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='accounts.backends.EmailOrUsernameBackend')
            messages.success(request, f'Welcome to CampusSwap, {user.display_name}.')
            messages.info(request, 'Add your course and phone so buyers can reach you.')
            return redirect('accounts:profile_edit')
    else:
        form = SignUpForm()

    return render(request, 'registration/signup.html', {'form': form})


class CampusLoginView(auth_views.LoginView):
    """Django's LoginView plus an explicit session-lifetime choice."""

    template_name = 'registration/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
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


def profile_detail(request, username):
    """Public profile: who they are plus the items they currently have up."""
    profile_user = get_object_or_404(User, username__iexact=username)
    listings = (
        profile_user.listings
        .select_related('seller', 'category')
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
