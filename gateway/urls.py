from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from django.shortcuts import redirect
from .views import (
    CheckoutCreateAPIView,
    DeviceSyncSMSAPIView,
    CheckoutVerifyAPIView,
    CheckoutDetailAPIView,
    checkout_page_view,
    merchant_dashboard_view,
    admin_dashboard_view,
    admin_action_api,
    service_worker_view,
    manifest_view
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # PWA Endpoints
    path('serviceworker.js', service_worker_view, name='pwa-serviceworker'),
    path('manifest.json', manifest_view, name='pwa-manifest'),

    # Admin Control Center with Sidebar
    path('admin-dashboard/', admin_dashboard_view, name='admin-dashboard'),
    path('api/v1/admin/action/', admin_action_api, name='admin-action-api'),

    # Merchant Dashboard PWA
    path('', lambda request: redirect('admin-dashboard'), name='root-redirect'),
    path('dashboard/', merchant_dashboard_view, name='merchant-dashboard'),

    # Hosted Checkout Customer UI
    path('checkout/<uuid:reference_id>/', checkout_page_view, name='hosted-checkout'),

    # DRF API Routes
    path('api/v1/checkout/create/', CheckoutCreateAPIView.as_view(), name='api-checkout-create'),
    path('api/v1/device/sync-sms/', DeviceSyncSMSAPIView.as_view(), name='api-device-sync-sms'),
    path('api/v1/checkout/<uuid:reference_id>/verify/', CheckoutVerifyAPIView.as_view(), name='api-checkout-verify'),
    path('api/v1/checkout/<uuid:reference_id>/', CheckoutDetailAPIView.as_view(), name='api-checkout-detail'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
