from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import ListingForm, ListingSearchForm
from .models import Category, Listing


def available_listings():
    """The base queryset for every public list page."""
    return (
        Listing.objects
        .select_related('seller', 'category')
        .filter(status=Listing.Status.AVAILABLE)
    )


def categories_with_counts():
    """Categories annotated with how many available listings they hold."""
    return Category.objects.annotate(
        listing_count=Count(
            'listings', filter=Q(listings__status=Listing.Status.AVAILABLE)
        )
    )


def home(request):
    """Landing page: hero search plus the latest available listings."""
    search_form = ListingSearchForm(request.GET or None)
    listings = search_form.filter(available_listings())
    searching = bool(request.GET.get('q') or request.GET.get('category'))

    return render(request, 'home.html', {
        'search_form': search_form,
        'latest_listings': listings[:8],
        'searching': searching,
        'result_count': listings.count() if searching else None,
        'categories': categories_with_counts(),
    })


def index(request):
    """Simple browse page. The full filtered version is chunk B1."""
    search_form = ListingSearchForm(request.GET or None)
    listings = search_form.filter(available_listings())
    return render(request, 'products/index.html', {
        'search_form': search_form,
        'listings': listings,
        'result_count': listings.count(),
    })


def category_detail(request, slug):
    """Listings in one category. Reuses the browse template."""
    category = get_object_or_404(Category, slug=slug)
    listings = available_listings().filter(category=category)
    return render(request, 'products/index.html', {
        'listings': listings,
        'category': category,
        'result_count': listings.count(),
    })


class ListingDetailView(DetailView):
    """Public listing page. Counts a view for everyone but the owner."""

    model = Listing
    template_name = 'products/listing_detail.html'
    context_object_name = 'listing'

    def get_queryset(self):
        return Listing.objects.select_related('seller', 'category')

    def get_object(self, queryset=None):
        listing = super().get_object(queryset)
        if listing.seller_id != self.request.user.pk:
            # F() increments in the database, so two people opening the page
            # at the same time can't overwrite each other's count.
            Listing.objects.filter(pk=listing.pk).update(views=F('views') + 1)
            listing.views += 1
        return listing

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        listing = self.object
        user = self.request.user

        is_owner = user.is_authenticated and listing.seller_id == user.pk
        context['is_owner'] = is_owner
        context['can_contact'] = (
            user.is_authenticated and not is_owner and bool(listing.seller.phone)
        )
        if context['can_contact']:
            text = f'Hi, I saw your "{listing.title}" on CampusSwap. Is it still available?'
            context['whatsapp_url'] = (
                f'https://wa.me/{listing.seller.phone.lstrip("+")}?text={quote(text)}'
            )
        return context


class ListingCreateView(LoginRequiredMixin, CreateView):
    model = Listing
    form_class = ListingForm
    template_name = 'products/listing_form.html'
    extra_context = {'heading': 'Sell an item', 'submit_label': 'Post listing'}

    def form_valid(self, form):
        # The seller is always the logged-in user, never a posted field.
        form.instance.seller = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Your listing is up.')
        return response


class OwnerListingMixin(LoginRequiredMixin):
    """Restrict a view to listings the logged-in user owns.

    Filtering the queryset (rather than fetching and then checking) means
    another student's listing simply does not exist for this view, so they
    get a plain 404 with no hint that the listing is real.
    """

    model = Listing

    def get_queryset(self):
        return Listing.objects.filter(seller=self.request.user)


class ListingUpdateView(OwnerListingMixin, UpdateView):
    form_class = ListingForm
    template_name = 'products/listing_form.html'
    extra_context = {'heading': 'Edit listing', 'submit_label': 'Save changes'}

    def form_valid(self, form):
        messages.success(self.request, 'Listing updated.')
        return super().form_valid(form)


class ListingDeleteView(OwnerListingMixin, DeleteView):
    template_name = 'products/listing_confirm_delete.html'
    success_url = reverse_lazy('products:my_listings')

    def form_valid(self, form):
        messages.success(self.request, 'Listing deleted.')
        return super().form_valid(form)


class MyListingsView(LoginRequiredMixin, ListView):
    """The student's own listings, optionally filtered by status."""

    template_name = 'products/my_listings.html'
    context_object_name = 'listings'

    def get_queryset(self):
        queryset = (
            Listing.objects
            .select_related('category')
            .filter(seller=self.request.user)
        )
        status = self.request.GET.get('status', '').upper()
        if status in Listing.Status.values:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mine = Listing.objects.filter(seller=self.request.user)

        # One grouped query for the counts instead of one query per tab.
        per_status = {
            row['status']: row['total']
            for row in mine.values('status').annotate(total=Count('pk'))
        }
        active = self.request.GET.get('status', '').upper()
        if active not in Listing.Status.values:
            active = ''

        context['active_status'] = active
        context['tabs'] = [
            {'value': '', 'label': 'All', 'count': sum(per_status.values())},
            *(
                {
                    'value': value,
                    'label': label,
                    'count': per_status.get(value, 0),
                }
                for value, label in Listing.Status.choices
            ),
        ]
        return context


@require_POST
def mark_status(request, slug, status):
    """Owner-only status change. POST only, so a stray link can't trigger it."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    status = status.upper()
    if status not in Listing.Status.values:
        messages.error(request, 'Unknown status.')
        return redirect('products:my_listings')

    # Filtered by seller, so a non-owner gets a 404 rather than a hint.
    listing = get_object_or_404(Listing, slug=slug, seller=request.user)
    listing.status = status
    listing.save(update_fields=['status', 'updated_at'])

    messages.success(request, f'Marked as {listing.get_status_display().lower()}.')
    return redirect(listing.get_absolute_url())
