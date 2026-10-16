from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    CheckoutCreateAPIView,
    DeviceSyncSMSAPIView,
    CheckoutVerifyAPIView,
    CheckoutDetailAPIView,
    checkout_page_view,
    merchant_dashboard_view,
    merchant_integration_guide_view,
    merchant_payment_method_action,
    payment_method_qr_view,
    admin_dashboard_view,
    admin_action_api,
    dashboard_home,
    account_login,
    account_logout,
    merchant_register,
    service_worker_view,
    manifest_view,
    download_sms_forwarder_apk,
    download_sms_forwarder_source
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', account_login, name='login'),
    path('register/', merchant_register, name='merchant-register'),
    path('logout/', account_logout, name='logout'),

    # PWA Endpoints
    path('serviceworker.js', service_worker_view, name='pwa-serviceworker'),
    path('manifest.json', manifest_view, name='pwa-manifest'),

    # Admin Control Center with Sidebar
    path('admin-dashboard/', admin_dashboard_view, name='admin-dashboard'),
    path('api/v1/admin/action/', admin_action_api, name='admin-action-api'),

    # Merchant Dashboard PWA
    path('', dashboard_home, name='root-redirect'),
    path('dashboard/', merchant_dashboard_view, name='merchant-dashboard'),
    path('dashboard/integration/', merchant_integration_guide_view, name='merchant-integration-guide'),
    path('api/v1/merchant/payment-method/', merchant_payment_method_action, name='merchant-payment-method-action'),
    path('payment-qr/<uuid:payment_method_id>/', payment_method_qr_view, name='payment-method-qr'),

    # Hosted Checkout Customer UI
    path('checkout/<uuid:reference_id>/', checkout_page_view, name='hosted-checkout'),

    # SMS Forwarder App Downloads
    path('download/sms-forwarder/', download_sms_forwarder_apk, name='download-sms-forwarder-apk'),
    path('download/sms-forwarder-source/', download_sms_forwarder_source, name='download-sms-forwarder-source'),

    # DRF API Routes
    path('api/v1/checkout/create/', CheckoutCreateAPIView.as_view(), name='api-checkout-create'),
    path('api/v1/device/sync-sms/', DeviceSyncSMSAPIView.as_view(), name='api-device-sync-sms'),
    path('api/v1/checkout/<uuid:reference_id>/verify/', CheckoutVerifyAPIView.as_view(), name='api-checkout-verify'),
    path('api/v1/checkout/<uuid:reference_id>/', CheckoutDetailAPIView.as_view(), name='api-checkout-detail'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
