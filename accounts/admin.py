from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Django's UserAdmin plus our student profile fields."""

    list_display = (
        'username', 'email', 'display_name', 'course', 'year_of_study', 'is_staff',
    )
    list_filter = BaseUserAdmin.list_filter + ('year_of_study',)
    search_fields = ('username', 'first_name', 'last_name', 'email', 'course')

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Student profile', {
            'fields': ('phone', 'course', 'year_of_study', 'bio', 'avatar'),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Student profile', {
            'fields': ('email', 'first_name', 'last_name'),
        }),
    )

    @admin.display(description='Name')
    def display_name(self, obj):
        return obj.display_name
