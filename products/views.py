from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import HttpResponseRedirect
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

from .forms import ListingForm, ListingSearchForm, build_image_formset
from .models import Category, Listing


def listing_queryset():
    """Listings with everything a card or detail page needs, in two queries.

    select_related for the two foreign keys, prefetch_related for the photos,
    so a 12-card grid does not run three queries per card.
    """
    return (
        Listing.objects
        .select_related('seller', 'category')
        .prefetch_related('images')
    )


def available_listings():
    """The base queryset for every public list page."""
    return listing_queryset().filter(status=Listing.Status.AVAILABLE)


RECENTLY_VIEWED_KEY = 'recently_viewed'


def remember_viewed(request, listing):
    """Keep the last few listing ids this visitor opened in their session.

    Most recent first, no duplicates, and the visitor's own listings are
    skipped by the caller.
    """
    limit = getattr(settings, 'RECENTLY_VIEWED_LIMIT', 5)
    viewed = [pk for pk in request.session.get(RECENTLY_VIEWED_KEY, []) if pk != listing.pk]
    viewed.insert(0, listing.pk)
    request.session[RECENTLY_VIEWED_KEY] = viewed[:limit]


def recently_viewed_listings(request):
    """The session's recently viewed listings, still in session order."""
    pks = request.session.get(RECENTLY_VIEWED_KEY, [])
    if not pks:
        return []

    by_pk = {
        listing.pk: listing
        for listing in listing_queryset().filter(pk__in=pks)
    }
    # Keep the session's order, and drop anything since deleted.
    return [by_pk[pk] for pk in pks if pk in by_pk]


def categories_with_counts():
    """Categories annotated with how many available listings they hold."""
    return Category.objects.annotate(
        listing_count=Count(
            'listings', filter=Q(listings__status=Listing.Status.AVAILABLE)
        )
    )


def home(request):
    """Landing page: hero search plus the latest available listings.

    The hero form only collects the query and posts it to the browse page,
    which is where all the real filtering happens.
    """
    return render(request, 'home.html', {
        'search_form': ListingSearchForm(),
        'latest_listings': available_listings()[:8],
        'categories': categories_with_counts(),
        'recently_viewed': recently_viewed_listings(request),
    })


class ListingListView(ListView):
    """Browse: search, filter, sort and paginate the public listings.

    The same view serves /browse/ and /c/<slug>/. On a category page the URL
    fixes the category, so that filter is taken out of the sidebar instead of
    being offered twice.
    """

    template_name = 'products/browse.html'
    context_object_name = 'listings'
    paginate_by = 12

    def get(self, request, *args, **kwargs):
        self.category = (
            get_object_or_404(Category, slug=kwargs['slug'])
            if 'slug' in kwargs
            else None
        )
        # Always bound, even with an empty query string: a GET form with no
        # required fields validates fine, and binding keeps the sidebar
        # showing whatever the student picked.
        self.search_form = ListingSearchForm(
            request.GET, locked_category=self.category
        )
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = listing_queryset()
        if self.category:
            queryset = queryset.filter(category=self.category)
        return self.search_form.filter(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Everything except the page number, so pagination links and chips
        # keep the current search.
        params = self.request.GET.copy()
        params.pop('page', None)

        chips = []
        for chip in self.search_form.active_filters():
            remaining = params.copy()
            remaining.pop(chip['param'], None)
            chips.append({**chip, 'query': remaining.urlencode()})

        page = context.get('page_obj')
        context['search_form'] = self.search_form
        context['category'] = self.category
        context['categories'] = categories_with_counts()
        context['result_count'] = (
            page.paginator.count if page else len(context['listings'])
        )
        context['active_filters'] = chips
        context['querystring'] = params.urlencode()
        return context


class ListingDetailView(DetailView):
    """Public listing page. Counts a view for everyone but the owner."""

    model = Listing
    template_name = 'products/listing_detail.html'
    context_object_name = 'listing'

    def get_queryset(self):
        return listing_queryset()

    def get_object(self, queryset=None):
        listing = super().get_object(queryset)
        if listing.seller_id != self.request.user.pk:
            # F() increments in the database, so two people opening the page
            # at the same time can't overwrite each other's count.
            Listing.objects.filter(pk=listing.pk).update(views=F('views') + 1)
            listing.views += 1
            # Own listings are deliberately left out of "recently viewed".
            remember_viewed(self.request, listing)
        return listing

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        listing = self.object
        user = self.request.user

        is_owner = user.is_authenticated and listing.seller_id == user.pk
        context['is_owner'] = is_owner
        # Evaluated once here so the gallery and the lightbox iterate the same
        # prefetched list instead of hitting the database again.
        context['photos'] = list(listing.images.all())
        context['can_contact'] = (
            user.is_authenticated and not is_owner and bool(listing.seller.phone)
        )
        if context['can_contact']:
            text = f'Hi, I saw your "{listing.title}" on CampusSwap. Is it still available?'
            context['whatsapp_url'] = (
                f'https://wa.me/{listing.seller.phone.lstrip("+")}?text={quote(text)}'
            )
        return context


class PhotoFormsetMixin:
    """Adds the photo gallery formset to a listing create/update view.

    The listing form and the formset have to stand or fall together: a listing
    with no photos is not valid, and a photo row with no listing cannot be
    saved. So nothing is written until both are clean, inside one transaction.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'image_formset' not in context:
            context['image_formset'] = build_image_formset(listing=self.object)
        return context

    def form_valid(self, form):
        formset = build_image_formset(
            listing=form.instance if form.instance.pk else None,
            data=self.request.POST,
            files=self.request.FILES,
        )
        if not formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, image_formset=formset)
            )

        with transaction.atomic():
            response = super().form_valid(form)  # saves the listing
            formset.instance = self.object
            self.save_photos(formset)
        return response

    def save_photos(self, formset):
        """Save the photo rows, then renumber them into the chosen order."""
        for photo in formset.save(commit=False):
            photo.listing = self.object
            photo.save()
        for photo in formset.deleted_objects:
            photo.delete()

        # ordered_forms is sorted by the ORDER inputs the arrow buttons
        # rewrite, and leaves out deleted and still-empty slots. Position 0
        # becomes the cover.
        for position, photo_form in enumerate(formset.ordered_forms):
            photo = photo_form.instance
            if photo.pk and photo.order != position:
                photo.order = position
                photo.save(update_fields=['order'])


class ListingCreateView(LoginRequiredMixin, PhotoFormsetMixin, CreateView):
    model = Listing
    form_class = ListingForm
    template_name = 'products/listing_form.html'
    extra_context = {'heading': 'Sell an item', 'submit_label': 'Post listing'}

    def form_valid(self, form):
        # The seller is always the logged-in user, never a posted field.
        form.instance.seller = self.request.user
        response = super().form_valid(form)
        if isinstance(response, HttpResponseRedirect):
            # Anything else means the photo formset sent the page back.
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


class ListingUpdateView(OwnerListingMixin, PhotoFormsetMixin, UpdateView):
    form_class = ListingForm
    template_name = 'products/listing_form.html'
    extra_context = {'heading': 'Edit listing', 'submit_label': 'Save changes'}

    def get_queryset(self):
        return super().get_queryset().prefetch_related('images')

    def form_valid(self, form):
        response = super().form_valid(form)
        if isinstance(response, HttpResponseRedirect):
            # A redirect means both the form and the photo formset saved.
            messages.success(self.request, 'Listing updated.')
        return response


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
            .prefetch_related('images')
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
