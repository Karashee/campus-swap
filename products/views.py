from django.shortcuts import render, get_object_or_404

from .models import Category, Listing


def home(request):
    latest = Listing.objects.select_related('seller', 'category').filter(
        status=Listing.Status.AVAILABLE
    )[:8]
    return render(request, 'home.html', {'latest_listings': latest})


def index(request):
    listings = Listing.objects.select_related('seller', 'category').filter(
        status=Listing.Status.AVAILABLE
    )
    return render(request, 'products/index.html', {'listings': listings})


def category_detail(request, slug):
    """Placeholder until B1 adds real filtering."""
    category = get_object_or_404(Category, slug=slug)
    listings = category.listings.select_related('seller', 'category').filter(
        status=Listing.Status.AVAILABLE
    )
    return render(
        request,
        'products/index.html',
        {'listings': listings, 'category': category},
    )


def listing_detail(request, slug):
    """Minimal detail page. The full one (gallery, seller card, actions) is A5."""
    listing = get_object_or_404(
        Listing.objects.select_related('seller', 'category'), slug=slug
    )
    return render(request, 'products/listing_detail.html', {'listing': listing})
