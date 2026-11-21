from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Listing, SavedListing


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'ordering', 'listing_count')
    list_editable = ('ordering',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

    @admin.display(description='Listings')
    def listing_count(self, obj):
        return obj.listings.count()


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

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('seller', 'category')

    @admin.display(description='')
    def thumbnail(self, obj):
        if not obj.image:
            return '—'
        return format_html(
            '<img src="{}" style="width:56px;height:42px;object-fit:cover;border-radius:6px;">',
            obj.image.url,
        )

    @admin.display(description='Price')
    def display_price(self, obj):
        return obj.display_price


@admin.register(SavedListing)
class SavedListingAdmin(admin.ModelAdmin):
    list_display = ('user', 'listing', 'created_at')
    search_fields = ('user__username', 'listing__title')
