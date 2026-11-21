from django import forms

from config.forms import FormStyleMixin

from .models import Category, Listing

IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')


class ListingForm(FormStyleMixin, forms.ModelForm):
    """Post or edit a listing. Mirrors the model's rules as field errors."""

    class Meta:
        model = Listing
        fields = (
            'title', 'category', 'listing_type', 'condition', 'price',
            'trade_for', 'description', 'meetup_spot', 'image',
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

    def clean_image(self):
        image = self.cleaned_data.get('image')
        # A freshly uploaded file has .size; an untouched existing one does not.
        if image and hasattr(image, 'size'):
            if image.size > IMAGE_MAX_BYTES:
                raise forms.ValidationError('Keep the photo under 5 MB.')
            if not image.name.lower().endswith(IMAGE_EXTENSIONS):
                raise forms.ValidationError('Use a JPG, PNG or WebP image.')
        return image


class ListingSearchForm(forms.Form):
    """GET-based search. Plain Form: it filters, it never saves anything."""

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            # A GET form should not mark anything required in the markup.
            field.widget.attrs.pop('required', None)

    def filter(self, queryset):
        """Apply whatever the student actually filled in."""
        from django.db.models import Q

        if not self.is_valid():
            return queryset

        q = self.cleaned_data.get('q')
        category = self.cleaned_data.get('category')
        listing_type = self.cleaned_data.get('listing_type')

        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )
        if category:
            queryset = queryset.filter(category=category)
        if listing_type:
            queryset = queryset.filter(listing_type=listing_type)
        return queryset
