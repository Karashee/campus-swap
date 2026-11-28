from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import F, Q
from django.forms import BaseInlineFormSet, inlineformset_factory

from config.forms import FormStyleMixin

from .imaging import (
    MAX_UPLOAD_BYTES,
    MIN_WIDTH,
    ImageTooSmall,
    UnidentifiedImageError,
    process_upload,
)
from .models import Category, Listing, ListingImage


class ListingForm(FormStyleMixin, forms.ModelForm):
    """Post or edit a listing. Mirrors the model's rules as field errors."""

    class Meta:
        model = Listing
        # Photos are not here: they live in their own formset (see
        # ListingImageFormSet below) because a listing can have several.
        fields = (
            'title', 'category', 'listing_type', 'condition', 'price',
            'trade_for', 'description', 'meetup_spot',
        )
        widgets = {
            'listing_type': forms.RadioSelect(attrs={'class': 'segmented'}),
            'condition': forms.RadioSelect(attrs={'class': 'segmented'}),
            'description': forms.Textarea(attrs={'rows': 5}),
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Scientific calculator Casio fx-991ES'}),
            'meetup_spot': forms.TextInput(attrs={'placeholder': 'e.g. Library entrance'}),
            'trade_for': forms.TextInput(attrs={'placeholder': 'e.g. A desk lamp or a kettle'}),
        }
        labels = {
            'listing_type': 'What do you want to do with it?',
            'trade_for': 'What do you want in exchange?',
            'meetup_spot': 'Meet-up spot on campus',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.all()
        self.fields['category'].empty_label = 'Choose a category'
        # Radio widgets render their own choices, so drop the blank option.
        self.fields['listing_type'].choices = Listing.ListingType.choices
        self.fields['condition'].choices = Listing.Condition.choices

    def clean(self):
        """Keep cleaned_data consistent with the model's rules.

        The SELL/TRADE/FREE rules themselves live in Listing.clean(). A
        ModelForm runs that during _post_clean and maps the error dict onto
        the matching fields, so 'price' and 'trade_for' errors already appear
        next to those inputs -- re-checking them here would show every
        message twice. All this does is mirror the model's "a free item has
        no price" so the field re-renders empty.
        """
        cleaned = super().clean()
        if cleaned.get('listing_type') == Listing.ListingType.FREE:
            cleaned['price'] = None
            self.data = self.data.copy()
            self.data['price'] = ''
        return cleaned


class ListingImageForm(FormStyleMixin, forms.ModelForm):
    """One photo slot in the gallery formset.

    Every accepted upload is re-encoded by products.imaging, so the file that
    reaches storage is a downscaled JPEG with no EXIF metadata.
    """

    class Meta:
        model = ListingImage
        fields = ('image',)
        labels = {'image': 'Photo'}
        # Plain FileInput, not the default ClearableFileInput: its "clear"
        # checkbox would empty the file on an existing row and leave a photo
        # with no image. Removing a photo is what the delete checkbox is for.
        widgets = {'image': forms.FileInput(
            attrs={'accept': 'image/jpeg,image/png,image/webp'}
        )}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Replacing an existing photo is optional; adding one is handled by
        # the formset, which refuses a listing with no photos at all.
        self.fields['image'].required = False

    def has_changed(self):
        """An empty slot is not a new photo.

        Without this, nudging a slot's hidden ORDER field would make Django
        treat the empty form as a new row and try to save a photo with no file.
        """
        if not self.instance.pk and self.add_prefix('image') not in self.files:
            return False
        return super().has_changed()

    def clean_image(self):
        upload = self.cleaned_data.get('image')
        # Only a new upload is an UploadedFile. An untouched row's value is
        # the stored FieldFile, which must be left exactly as it is: running
        # it through the processor again would re-encode it and write a second
        # copy to the media folder on every edit.
        if not isinstance(upload, UploadedFile):
            return upload

        if upload.size > MAX_UPLOAD_BYTES:
            raise ValidationError('Keep each photo under 5 MB.')

        try:
            return process_upload(upload)
        except ImageTooSmall:
            raise ValidationError(
                f'That photo is too small. Use one at least {MIN_WIDTH}px wide.'
            )
        except UnidentifiedImageError:
            raise ValidationError('That file is not an image we can read.')


class BaseListingImageFormSet(BaseInlineFormSet):
    """Gallery rules that only make sense across the whole set of photos."""

    def clean(self):
        super().clean()
        if any(self.errors):
            # Per-photo problems are already on the individual forms.
            return

        if not self.kept_forms():
            raise ValidationError('Add at least one photo of the item.')

    def kept_forms(self):
        """The forms that will still hold a photo after this submission."""
        kept = []
        for form in self.forms:
            if not form.cleaned_data or self._should_delete_form(form):
                continue
            if form.cleaned_data.get('image') or form.instance.pk:
                kept.append(form)
        return kept


#: The formset prefix, so the view, the template and the tests agree on it.
PHOTO_PREFIX = 'photos'


def listing_image_formset_class(extra):
    """An inline formset of photos with ``extra`` empty slots.

    can_order adds the per-form ORDER input that the arrow buttons rewrite;
    validate_max counts deletions, so swapping one photo out and another in
    still passes the five-photo cap.
    """
    return inlineformset_factory(
        Listing,
        ListingImage,
        form=ListingImageForm,
        formset=BaseListingImageFormSet,
        fields=('image',),
        extra=extra,
        max_num=ListingImage.MAX_PHOTOS,
        validate_max=True,
        can_delete=True,
        can_order=True,
    )


def build_image_formset(listing=None, data=None, files=None):
    """The gallery formset with empty slots up to the photo cap.

    Three empty slots at a time: enough to add a few photos without a wall of
    file inputs, and never more than the five-photo total allows.
    """
    existing = listing.images.count() if listing and listing.pk else 0
    formset_class = listing_image_formset_class(
        extra=min(3, max(ListingImage.MAX_PHOTOS - existing, 0))
    )
    return formset_class(
        data=data, files=files, instance=listing, prefix=PHOTO_PREFIX
    )


class ListingSearchForm(FormStyleMixin, forms.Form):
    """GET-based search, filter and sort. Plain Form: it never saves anything.

    One form drives the home hero search, the browse page sidebar and the
    category pages, so the query rules live in exactly one place.
    """

    NEWEST = 'newest'
    PRICE_ASC = 'price_asc'
    PRICE_DESC = 'price_desc'
    SORT_CHOICES = [
        (NEWEST, 'Newest first'),
        (PRICE_ASC, 'Price: low to high'),
        (PRICE_DESC, 'Price: high to low'),
    ]

    q = forms.CharField(
        required=False,
        label='Search',
        widget=forms.TextInput(attrs={
            'placeholder': 'Search listings',
            'type': 'search',
        }),
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label='All categories',
    )
    listing_type = forms.ChoiceField(
        choices=[('', 'Any type')] + Listing.ListingType.choices,
        required=False,
        label='Type',
    )
    condition = forms.ChoiceField(
        choices=[('', 'Any condition')] + Listing.Condition.choices,
        required=False,
    )
    min_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        label='Min price',
        help_text='Price filters only match items that are for sale.',
        widget=forms.NumberInput(attrs={'placeholder': 'KSh 0', 'min': '0', 'step': '50'}),
    )
    max_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        label='Max price',
        widget=forms.NumberInput(attrs={'placeholder': 'Any', 'min': '0', 'step': '50'}),
    )
    sort = forms.ChoiceField(choices=SORT_CHOICES, required=False, label='Sort by')
    show_sold = forms.BooleanField(required=False, label='Include sold items')

    #: Fields that are filters rather than presentation, in chip order.
    FILTER_FIELDS = (
        'q', 'category', 'listing_type', 'condition',
        'min_price', 'max_price', 'show_sold',
    )

    def __init__(self, *args, locked_category=None, **kwargs):
        super().__init__(*args, **kwargs)
        #: Set on the /c/<slug>/ pages, where the URL already fixes the category.
        self.locked_category = locked_category
        if locked_category is not None:
            del self.fields['category']
        for field in self.fields.values():
            # A GET form should not mark anything required in the markup.
            field.widget.attrs.pop('required', None)

    def clean(self):
        cleaned = super().clean()
        low = cleaned.get('min_price')
        high = cleaned.get('max_price')
        if low is not None and high is not None and low > high:
            self.add_error(
                'min_price', 'The lowest price cannot be above the highest.'
            )
        return cleaned

    def filter(self, queryset):
        """Apply whatever the student actually filled in, then sort."""
        if not self.is_valid():
            # Contradictory input (min above max, a bad number). Fall back to
            # the default view of the data; the form renders its own errors.
            return queryset.exclude(status=Listing.Status.SOLD)

        data = self.cleaned_data

        if data.get('q'):
            queryset = queryset.filter(
                Q(title__icontains=data['q']) | Q(description__icontains=data['q'])
            )
        if data.get('category'):
            queryset = queryset.filter(category=data['category'])
        if data.get('listing_type'):
            queryset = queryset.filter(listing_type=data['listing_type'])
        if data.get('condition'):
            queryset = queryset.filter(condition=data['condition'])

        # A price range is only meaningful for priced items, so trade and free
        # listings (price IS NULL) drop out of the results once one is set.
        if data.get('min_price') is not None:
            queryset = queryset.filter(price__gte=data['min_price'])
        if data.get('max_price') is not None:
            queryset = queryset.filter(price__lte=data['max_price'])

        if not data.get('show_sold'):
            queryset = queryset.exclude(status=Listing.Status.SOLD)

        return queryset.order_by(*self.ordering())

    def ordering(self):
        """The order_by arguments for the chosen sort.

        Free and trade listings have no price, so they sit at the end of a
        price sort either way rather than clumping at the cheap end.
        """
        sort = self.cleaned_data.get('sort') if self.is_valid() else None
        if sort == self.PRICE_ASC:
            return (F('price').asc(nulls_last=True), '-created_at')
        if sort == self.PRICE_DESC:
            return (F('price').desc(nulls_last=True), '-created_at')
        return ('-created_at',)

    def active_filters(self):
        """The filters currently in force, for the removable chips.

        Each entry names the GET parameter to drop and the label to show.
        """
        if not self.is_valid():
            return []

        chips = []
        for name in self.FILTER_FIELDS:
            if name not in self.fields:
                continue
            value = self.cleaned_data.get(name)
            if value in (None, '', False):
                continue

            if name == 'q':
                label = f'“{value}”'
            elif name == 'category':
                label = str(value)
            elif name == 'listing_type':
                label = Listing.ListingType(value).label
            elif name == 'condition':
                label = Listing.Condition(value).label
            elif name == 'min_price':
                label = f'From KSh {value:,.0f}'
            elif name == 'max_price':
                label = f'Up to KSh {value:,.0f}'
            else:  # show_sold
                label = 'Including sold'

            chips.append({'param': name, 'label': label})
        return chips
