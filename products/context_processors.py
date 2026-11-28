"""Template context that every page needs.

Only one entry so far: which listings the visitor has saved. It lives in a
context processor rather than in each view because the save button appears on
the listing cards, and those cards are included from six different templates
(home, browse, category, profile, my listings, saved).
"""

from django.utils.functional import SimpleLazyObject

from .models import SavedListing


def saved_listings(request):
    """``saved_listing_ids``: the listing ids this visitor has saved.

    Wrapped in SimpleLazyObject so the query runs only on a page that
    actually renders a save button, and runs at most once per response. An
    anonymous visitor never has saves, so they get an empty set without
    touching the database.
    """

    def ids():
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return frozenset()
        return frozenset(
            SavedListing.objects
            .filter(user=user)
            .values_list('listing_id', flat=True)
        )

    return {'saved_listing_ids': SimpleLazyObject(ids)}
