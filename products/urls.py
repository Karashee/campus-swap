from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    path('browse/', views.ListingListView.as_view(), name='browse'),
    # Category pages are the same view with the category fixed by the URL.
    path('c/<slug:slug>/', views.ListingListView.as_view(), name='category'),
    path('my-listings/', views.MyListingsView.as_view(), name='my_listings'),
    path('listings/new/', views.ListingCreateView.as_view(), name='create'),
    path('listings/<slug:slug>/', views.ListingDetailView.as_view(), name='detail'),
    path('listings/<slug:slug>/edit/', views.ListingUpdateView.as_view(), name='edit'),
    path('listings/<slug:slug>/delete/', views.ListingDeleteView.as_view(), name='delete'),
    path(
        'listings/<slug:slug>/status/<str:status>/',
        views.mark_status,
        name='mark_status',
    ),
]
