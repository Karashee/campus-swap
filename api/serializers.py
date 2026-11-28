from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from products.models import Category, Listing, ListingImage

User = get_user_model()


class CategoryBriefSerializer(serializers.ModelSerializer):
    """A category as it appears nested inside a listing."""

    class Meta:
        model = Category
        fields = ('id', 'name', 'slug')
        read_only_fields = fields


class CategorySerializer(CategoryBriefSerializer):
    """A category on its own, plus how many available listings it holds.

    ``listing_count`` comes from the annotation the viewset's queryset adds,
    so reading it costs no extra query. It is only on this serializer, not on
    the brief one: a listing's nested category is a plain row with no
    annotation, and a field that silently disappeared from half the responses
    would make the published schema a lie.
    """

    listing_count = serializers.IntegerField(read_only=True)

    class Meta(CategoryBriefSerializer.Meta):
        fields = ('id', 'name', 'slug', 'ordering', 'listing_count')
        read_only_fields = fields


class ListingImageSerializer(serializers.ModelSerializer):
    """One photo. Read-only: uploads go through the web form.

    ``image`` renders as a URL rather than a path. DRF makes it absolute when
    the request is in the serializer context, which the viewsets provide.
    """

    image = serializers.ImageField(read_only=True)

    class Meta:
        model = ListingImage
        fields = ('id', 'image', 'order')
        read_only_fields = fields


class SellerSerializer(serializers.ModelSerializer):
    """The public face of a seller. Deliberately not the whole user row.

    No email and no phone number: those are what the WhatsApp link on the
    website is for, and an API that handed out every student's phone number to
    anonymous callers would be the biggest hole in the project.
    """

    display_name = serializers.CharField(read_only=True)

    class Meta:
        # get_user_model(), never auth.User: the project has a custom user.
        model = User
        fields = ('username', 'display_name', 'course', 'year_of_study')
        read_only_fields = fields


class ListingSerializer(serializers.ModelSerializer):
    """A listing, with the model's own business rules re-run on write.

    The SELL/TRADE/FREE rules live in ``Listing.clean()``. A ModelForm calls
    that for free; a DRF serializer does not, so ``validate()`` below builds
    the listing the request is asking for and calls ``clean()`` on it. That
    way the API cannot create something the web form would have rejected --
    a priced trade, a sale with no price -- and there is still only one copy
    of the rules.
    """

    # Nested for reading, so a client gets the category name without a second
    # call; writing uses the separate *_id fields below.
    category = CategoryBriefSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True,
        label='Category',
    )
    seller = SellerSerializer(read_only=True)
    images = ListingImageSerializer(many=True, read_only=True)
    display_price = serializers.CharField(read_only=True)
    web_url = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = (
            'id', 'title', 'slug', 'description',
            'category', 'category_id',
            'seller', 'condition', 'listing_type', 'price', 'display_price',
            'trade_for', 'status', 'meetup_spot', 'images', 'views',
            'web_url', 'created_at', 'updated_at',
        )
        # The slug is generated from the title, the seller is always the
        # caller, and the view counter belongs to the web pages.
        read_only_fields = ('id', 'slug', 'seller', 'views', 'created_at', 'updated_at')

    def get_web_url(self, listing) -> str:
        """The listing's page on the website, absolute if we know the host."""
        url = listing.get_absolute_url()
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        """Run Listing.clean() against the listing this request would save."""
        listing = self._merged_instance(attrs)

        try:
            listing.clean()
        except DjangoValidationError as exc:
            # as_serializer_error turns a Django error dict (which may use
            # NON_FIELD_ERRORS) into DRF's own shape.
            raise serializers.ValidationError(serializers.as_serializer_error(exc))

        # clean() blanks the price of a free item. Mirror that, so "free with
        # a price" saves as free rather than quietly keeping the number.
        if 'price' in attrs or 'listing_type' in attrs:
            attrs['price'] = listing.price
        return attrs

    def _merged_instance(self, attrs):
        """An unsaved Listing holding the current values plus this request's.

        Built field by field rather than by copying ``self.instance`` so a
        PATCH is validated against the row as it will be, and so nothing here
        can accidentally mutate (or save) the real object.
        """
        listing = Listing()
        for field in Listing._meta.concrete_fields:
            if self.instance is not None:
                setattr(listing, field.attname, getattr(self.instance, field.attname))
        for name, value in attrs.items():
            setattr(listing, name, value)
        return listing
