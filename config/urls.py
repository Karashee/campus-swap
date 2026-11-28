from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from products import views as product_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', product_views.home, name='home'),
    path('accounts/', include('accounts.urls')),
    # The JSON API (/api/v1/) and its OpenAPI docs (/api/docs/).
    path('api/', include('api.urls')),
    # Mounted at the root so the public pages read as /browse/, /c/<slug>/
    # and /listings/<slug>/.
    path('', include('products.urls')),
]

# Serve user-uploaded media with the dev server. Never used in production.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
