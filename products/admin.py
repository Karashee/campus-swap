from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Listing, ListingImage, SavedListing


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'ordering', 'listing_count')
    list_editable = ('ordering',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

    @admin.display(description='Listings')
    def listing_count(self, obj):
        return obj.listings.count()


class ListingImageInline(admin.TabularInline):
    """The gallery, edited alongside the listing. Lowest order is the cover."""

    model = ListingImage
    extra = 1
    max_num = ListingImage.MAX_PHOTOS
    fields = ('preview', 'image', 'order')
    readonly_fields = ('preview',)
    ordering = ('order', 'pk')

    @admin.display(description='')
    def preview(self, obj):
        if not obj.pk or not obj.image:
            return '—'
        return format_html(
            '<img src="{}" style="width:90px;height:68px;object-fit:cover;border-radius:6px;">',
            obj.image.url,
        )


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = (
        'thumbnail', 'title', 'seller', 'category', 'listing_type',
        'display_price', 'status', 'created_at',
    )
    list_display_links = ('title',)
    list_editable = ('status',)
    list_filter = ('listing_type', 'status', 'condition', 'category', 'created_at')
    search_fields = ('title', 'description', 'seller__username', 'seller__email')
    readonly_fields = ('views', 'slug', 'created_at', 'updated_at')
    autocomplete_fields = ('category',)
    date_hierarchy = 'created_at'
    inlines = (ListingImageInline,)

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('seller', 'category')
            .prefetch_related('images')
        )

    @admin.display(description='')
    def thumbnail(self, obj):
        cover = obj.cover
        if not cover:
            return '—'
        return format_html(
            '<img src="{}" style="width:56px;height:42px;object-fit:cover;border-radius:6px;">',
            cover.image.url,
        )

    @admin.display(description='Price')
    def display_price(self, obj):
        return obj.display_price


@admin.register(SavedListing)
class SavedListingAdmin(admin.ModelAdmin):
    list_display = ('user', 'listing', 'created_at')
    search_fields = ('user__username', 'listing__title')
