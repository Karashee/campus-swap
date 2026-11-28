from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'api'

# DefaultRouter also gives /api/v1/ an index listing the collections, which is
# a useful entry point for anyone poking at the API by hand.
router = DefaultRouter()
router.register('categories', views.CategoryViewSet, basename='category')
router.register('listings', views.ListingViewSet, basename='listing')

urlpatterns = [
    # Versioned in the URL so a later, incompatible shape can live beside this
    # one instead of breaking whatever is already calling it.
    path('v1/', include(router.urls)),
    path('v1/auth/token/', views.ApiTokenView.as_view(), name='token'),
    # The machine-readable schema, and the human page built from it.
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', views.docs_view, name='docs'),
]
