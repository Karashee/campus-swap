from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from products.models import Listing

from .forms import ProfileForm, SignUpForm

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
