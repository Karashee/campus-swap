from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

from products.forms import ListingSearchForm
from products.models import Category, Listing


class ListingSearchBackend(BaseFilterBackend):
    """Searching and filtering for /api/v1/listings/, driven by the web form.

    Rather than describe the query parameters a second time (django-filter or
    a hand-written set of ``request.query_params.get`` calls), this hands the
    query string to ``ListingSearchForm`` -- the same form the browse page and
    the category pages use -- and lets it validate and apply the filters. One
    definition of "what you can search by", and one definition of what each
    filter means.

    Two differences from the web page, both deliberate:

    * ``category`` accepts a slug as well as the numeric id, because a URL
      like ``?category=textbooks`` is far more usable than ``?category=3``.
      The slug is translated to an id before the form sees it, so the form
      itself stays untouched.
    * Contradictory input is a 400 with the form's error messages. The browse
      page quietly falls back to the unfiltered list and renders the errors
      next to the inputs, which an API client cannot see.
    """

    #: Shown in the OpenAPI schema, in this order.
    PARAM_DESCRIPTIONS = {
        'q': 'Free text, matched against the title and the description.',
        'category': 'Category slug (or numeric id).',
        'listing_type': 'One of SELL, TRADE, FREE.',
        'condition': 'One of NEW, LIKE_NEW, GOOD, FAIR.',
        'min_price': 'Lowest price in KSh. Only matches items that are for sale.',
        'max_price': 'Highest price in KSh. Only matches items that are for sale.',
        'sort': 'newest (default), price_asc or price_desc.',
        'show_sold': 'true to include sold listings, which are hidden by default.',
    }

    #: Values the enum parameters accept, for the schema.
    PARAM_ENUMS = {
        'listing_type': Listing.ListingType.values,
        'condition': Listing.Condition.values,
        'sort': [value for value, _label in ListingSearchForm.SORT_CHOICES],
    }

    def filter_queryset(self, request, queryset, view):
        form = ListingSearchForm(self._form_data(request))
        if not form.is_valid():
            raise ValidationError(form.errors)
        return form.filter(queryset)

    def _form_data(self, request):
        """The query string, with a category slug swapped for its id."""
        data = request.query_params.copy()
        category = data.get('category', '').strip()
        if category and not category.isdigit():
            # An unknown slug leaves the value in place, so the form reports
            # "not a valid choice" instead of silently ignoring the filter.
            pk = (
                Category.objects.filter(slug=category)
                .values_list('pk', flat=True)
                .first()
            )
            if pk is not None:
                data['category'] = str(pk)
        return data

    def get_schema_operation_parameters(self, view):
        """Describe the filters for drf-spectacular.

        Without this the docs page would show the endpoint as taking nothing
        but a page number, because the filtering happens in a form that the
        schema generator cannot introspect.
        """
        parameters = []
        for name, description in self.PARAM_DESCRIPTIONS.items():
            schema = {'type': self._schema_type(name)}
            if name in self.PARAM_ENUMS:
                schema['enum'] = self.PARAM_ENUMS[name]
            parameters.append({
                'name': name,
                'required': False,
                'in': 'query',
                'description': description,
                'schema': schema,
            })
        return parameters

    @staticmethod
    def _schema_type(name):
        if name == 'show_sold':
            return 'boolean'
        if name in {'min_price', 'max_price'}:
            return 'number'
        return 'string'
