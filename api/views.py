from django.utils.csp import CSP
from django.views.decorators.csp import csp_override
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from drf_spectacular.views import SpectacularSwaggerSplitView
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from products.views import categories_with_counts, listing_queryset

from .filters import ListingSearchBackend
from .permissions import IsOwnerOrReadOnly
from .serializers import CategorySerializer, ListingSerializer


class ListingPagination(PageNumberPagination):
    """Twelve per page like the browse grid, up to 50 if the client asks."""

    page_size_query_param = 'page_size'
    max_page_size = 50


@extend_schema_view(
    list=extend_schema(
        summary='List categories',
        description='All categories, with a count of the available listings in each.',
    ),
    retrieve=extend_schema(summary='Fetch one category by slug'),
)
class CategoryViewSet(ReadOnlyModelViewSet):
    """Read-only: categories are seeded by a data migration, not by students."""

    serializer_class = CategorySerializer
    lookup_field = 'slug'
    # A handful of rows that the clients all want in full, so no pagination.
    pagination_class = None

    def get_queryset(self):
        return categories_with_counts()


@extend_schema_view(
    list=extend_schema(
        summary='Search listings',
        description=(
            'Available listings, newest first. Sold listings are left out '
            'unless show_sold is set. Every filter is optional.'
        ),
    ),
    retrieve=extend_schema(summary='Fetch one listing by slug'),
    create=extend_schema(
        summary='Post a listing',
        description=(
            'You become the seller. Photos cannot be attached here: add them '
            'on the website, then they appear in the images field.'
        ),
    ),
    update=extend_schema(summary='Replace your listing'),
    partial_update=extend_schema(summary='Change some fields of your listing'),
    destroy=extend_schema(
        summary='Delete your listing',
        responses={204: OpenApiResponse(description='Deleted.')},
    ),
)
class ListingViewSet(ModelViewSet):
    """Listings: public to read, yours to write.

    The queryset is every listing, including sold ones, so a link to a sold
    item keeps working. Hiding sold items from the list is the search form's
    job (see ListingSearchBackend), not the queryset's.
    """

    serializer_class = ListingSerializer
    permission_classes = [IsOwnerOrReadOnly]
    pagination_class = ListingPagination
    filter_backends = [ListingSearchBackend]
    lookup_field = 'slug'

    def get_queryset(self):
        # The same select_related/prefetch_related the web pages use, so a
        # page of twelve listings with their photos is still a few queries.
        return listing_queryset()

    def perform_create(self, serializer):
        # The seller is the caller, never a posted field: 'seller' is
        # read-only on the serializer, so a client that sends one is ignored.
        serializer.save(seller=self.request.user)


@extend_schema(
    summary='Exchange a username and password for an API token',
    description=(
        'Send the token back as the header `Authorization: Token <key>`. '
        'Browser clients can skip this and use the session cookie instead.'
    ),
)
class ApiTokenView(ObtainAuthToken):
    """Issue the caller's API token.

    ``authentication_classes`` is emptied on purpose: this endpoint proves who
    you are with a username and password in the body, so running session
    authentication over it as well would only mean a logged-in browser needed
    a CSRF token to ask for a token.
    """

    authentication_classes = []


#: /api/docs/.
#:
#: Two things make the Swagger UI page fit inside the strict CSP from B7
#: without loosening it anywhere:
#:
#: * ``SpectacularSwaggerSplitView`` serves the UI's init script as its own
#:   request (/api/docs/?script=) instead of an inline <script> block, and
#:   the sidecar puts the bundle in our own static files instead of a CDN, so
#:   ``script-src 'self'`` covers everything on the page.
#: * ``templates/drf_spectacular/swagger_ui.html`` shadows the packaged
#:   template to move its three inline CSS rules into a static file, so
#:   ``style-src 'self'`` covers the stylesheets too.
#:
#: The override here therefore only *tightens* the site policy: the docs page
#: has no inline script of ours to nonce and loads no Google Fonts, so both
#: of those sources come off. If a future Swagger UI release does need
#: something more, this is the one place to say so, and the site's own pages
#: are not affected.
docs_view = csp_override({
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF],
    'style-src': [CSP.SELF],
    # The Swagger UI stylesheet draws its icons with inline data: SVGs.
    'img-src': [CSP.SELF, 'data:'],
    'connect-src': [CSP.SELF],
    'base-uri': [CSP.SELF],
    'form-action': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
    'object-src': [CSP.NONE],
})(SpectacularSwaggerSplitView.as_view(url_name='api:schema'))
