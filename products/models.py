import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    """A listing category, e.g. Textbooks. Seeded by a data migration."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    ordering = models.PositiveSmallIntegerField(
        default=0, help_text='Lower numbers appear first.'
    )

    class Meta:
        ordering = ['ordering', 'name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('products:category', kwargs={'slug': self.slug})


class Listing(models.Model):
    """An item a student is selling, trading or giving away."""

    class Condition(models.TextChoices):
        NEW = 'NEW', 'Brand new'
        LIKE_NEW = 'LIKE_NEW', 'Like new'
        GOOD = 'GOOD', 'Good'
        FAIR = 'FAIR', 'Fair'

    class ListingType(models.TextChoices):
        SELL = 'SELL', 'For sale'
        TRADE = 'TRADE', 'For trade'
        FREE = 'FREE', 'Free'

    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        RESERVED = 'RESERVED', 'Reserved'
        SOLD = 'SOLD', 'Sold'

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listings',
    )
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField()
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='listings',
    )
    condition = models.CharField(
        max_length=10, choices=Condition.choices, default=Condition.GOOD
    )
    listing_type = models.CharField(
        max_length=5, choices=ListingType.choices, default=ListingType.SELL
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='In Kenyan shillings. Leave empty for trade or free items.',
    )
    trade_for = models.CharField(
        max_length=200,
        blank=True,
        help_text='What you want in exchange, for trade listings.',
    )
    status = models.CharField(
        max_length=9, choices=Status.choices, default=Status.AVAILABLE
    )
    meetup_spot = models.CharField(
        max_length=120, help_text='Where on campus you can hand the item over.'
    )
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['category', 'status']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._build_slug()
        super().save(*args, **kwargs)

    def _build_slug(self):
        """Slug from the title plus a short random suffix, so titles can repeat."""
        base = slugify(self.title)[:120] or 'listing'
        while True:
            candidate = f'{base}-{secrets.token_hex(3)}'
            if not Listing.objects.filter(slug=candidate).exists():
                return candidate

    def clean(self):
        """Business rules for the three listing types.

        Enforced here (not only in the form) so the admin, the shell and any
        future API all get the same rules.
        """
        super().clean()
        errors = {}

        if self.listing_type == self.ListingType.SELL:
            if self.price is None or self.price <= 0:
                errors['price'] = 'Give a price above 0 for an item you are selling.'
        elif self.listing_type == self.ListingType.FREE:
            # A free item has no price, whatever was typed in.
            self.price = None
        elif self.listing_type == self.ListingType.TRADE:
            if not self.trade_for:
                errors['trade_for'] = 'Say what you want in exchange.'
            if self.price is not None:
                errors['price'] = 'A trade listing has no price. Clear it or switch to "For sale".'

        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self):
        return reverse('products:detail', kwargs={'slug': self.slug})

    @property
    def is_available(self):
        return self.status == self.Status.AVAILABLE

    @property
    def cover(self):
        """The first photo: the one used on cards and as the main image.

        Slicing rather than .first() so a prefetched ``images`` cache is
        reused instead of firing one extra query per card in a grid.
        """
        images = self.images.all()[:1]
        return images[0] if images else None

    @property
    def photo_count(self):
        return len(self.images.all())

    @property
    def display_price(self):
        """'KSh 1,500' / 'Free' / 'Trade' for templates and the admin."""
        if self.listing_type == self.ListingType.FREE:
            return 'Free'
        if self.listing_type == self.ListingType.TRADE:
            return 'Trade'
        if self.price is None:
            return '—'
        return f'KSh {self.price:,.0f}'


class ListingImage(models.Model):
    """One photo of a listing. The lowest ``order`` is the cover image.

    A listing has between one and MAX_PHOTOS of these; the limit lives in the
    formset, since it is a rule about one submission rather than about the row.
    """

    MAX_PHOTOS = 5

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='listings/%Y/%m/')
    order = models.PositiveSmallIntegerField(
        default=0, help_text='Lowest first. The first photo is the cover.'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # pk breaks ties so the order is stable when two rows share a number.
        ordering = ['order', 'pk']
        indexes = [models.Index(fields=['listing', 'order'])]

    def __str__(self):
        return f'Photo {self.order + 1} of {self.listing.title}'

    @property
    def is_cover(self):
        return self == self.listing.cover


class SavedListing(models.Model):
    """A student bookmarking a listing. Used from Phase B onwards."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_listings',
    )
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='saved_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'listing'], name='unique_saved_listing'
            )
        ]

    def __str__(self):
        return f'{self.user} saved {self.listing}'
