from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.index, name='index'),
    # Placeholder routes so get_absolute_url() resolves. Real views land in A5/B1.
    path('c/<slug:slug>/', views.category_detail, name='category'),
    path('<slug:slug>/', views.listing_detail, name='detail'),
]
