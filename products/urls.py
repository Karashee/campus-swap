from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    path('', views.index, name='index'),
    path('new/', views.ListingCreateView.as_view(), name='create'),
    path('my-listings/', views.MyListingsView.as_view(), name='my_listings'),
    path('c/<slug:slug>/', views.category_detail, name='category'),
    path('<slug:slug>/', views.ListingDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', views.ListingUpdateView.as_view(), name='edit'),
    path('<slug:slug>/delete/', views.ListingDeleteView.as_view(), name='delete'),
    path('<slug:slug>/status/<str:status>/', views.mark_status, name='mark_status'),
]
