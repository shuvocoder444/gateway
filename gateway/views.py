import json
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.utils.datastructures import MultiValueDict
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status, views, permissions
from rest_framework.response import Response

from .models import (
    Merchant,
    PaymentMethod,
    Device,
    Invoice,
    SMSTransaction,
    InvoiceStatus,
    SMSTransactionStatus,
    AccountType,
    MFSProvider
)
from .authentication import (
    MerchantAPIKeyAuthentication,
    DeviceTokenAuthentication
)
from .permissions import (
    HasMerchantAPIKey,
    HasDeviceToken
)
from .serializers import (
    CheckoutCreateSerializer,
    CheckoutDetailSerializer,
    CheckoutVerifySerializer,
    SMSSyncItemSerializer
)
from .services import verify_and_settle_invoice
from .forms import GatewayAuthenticationForm, MerchantRegistrationForm, PaymentQRCodeUploadForm, MerchantBrandingForm


def _account_destination(user):
    return 'admin-dashboard' if user.is_superuser else 'merchant-dashboard'


@never_cache
def dashboard_home(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return redirect(_account_destination(request.user))


@never_cache
def account_login(request):
    if request.user.is_authenticated:
        return redirect(_account_destination(request.user))

    form = GatewayAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        if not user.is_superuser:
            merchant = getattr(user, 'merchant_profile', None)
            if merchant is None or not merchant.is_active:
                form.add_error(None, 'This account does not have an active merchant workspace.')
            else:
                login(request, user)
                return redirect('merchant-dashboard')
        else:
            login(request, user)
            return redirect('admin-dashboard')

    return render(request, 'accounts/login.html', {'form': form})


@never_cache
def merchant_register(request):
    if request.user.is_authenticated:
        return redirect(_account_destination(request.user))

    form = MerchantRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            Merchant.objects.create(
                owner=user,
                name=form.cleaned_data['business_name'],
                email=user.email,
                is_active=True,
            )
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Your merchant workspace is ready.')
        return redirect('merchant-dashboard')

    return render(request, 'accounts/register.html', {'form': form})


@require_POST
@never_cache
def account_logout(request):
    logout(request)
    return redirect('login')


class CheckoutCreateAPIView(views.APIView):
    """
    POST /api/v1/checkout/create/
    Initiate a hosted checkout payment request. Authenticated via X-API-KEY.
    """
    authentication_classes = [MerchantAPIKeyAuthentication]
    permission_classes = [HasMerchantAPIKey]

    def post(self, request, *args, **kwargs):
        merchant = getattr(request, 'merchant', None)
        if not merchant:
            return Response(
                {"status": "error", "detail": "Merchant authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = CheckoutCreateSerializer(
            data=request.data,
            context={'request': request, 'merchant': merchant}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment_method = None
        if data.get('payment_method_id'):
            payment_method = PaymentMethod.objects.filter(
                id=data['payment_method_id'],
                merchant=merchant,
                is_active=True
            ).first()

        invoice = Invoice.objects.create(
            merchant=merchant,
            payment_method=payment_method,
            order_id=data.get('order_id', ''),
            amount=data['amount'],
            currency=data.get('currency', 'BDT'),
            customer_name=data.get('customer_name', ''),
            customer_email=data.get('customer_email'),
            customer_phone=data.get('customer_phone', ''),
            callback_url=data.get('callback_url'),
            metadata=data.get('metadata', {})
        )

        checkout_url = request.build_absolute_uri(f"/checkout/{invoice.reference_id}/")

        return Response({
            "status": "success",
            "message": "Invoice created successfully.",
            "invoice_id": str(invoice.id),
            "reference_id": str(invoice.reference_id),
            "checkout_url": checkout_url,
            "order_id": invoice.order_id,
            "amount": str(invoice.amount),
            "currency": invoice.currency,
            "invoice_status": invoice.status,
            "expires_at": invoice.expires_at.isoformat(),
            "created_at": invoice.created_at.isoformat()
        }, status=status.HTTP_201_CREATED)


class DeviceSyncSMSAPIView(views.APIView):
    """
    POST /api/v1/device/sync-sms/
    Synchronize incoming SMS/Notification transactions from Android forwarder.
    Authenticated via X-DEVICE-TOKEN. Safely handles duplicate TrxIDs.
    """
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [HasDeviceToken]

    def post(self, request, *args, **kwargs):
        device = getattr(request, 'device', None)
        merchant = getattr(request, 'merchant', None)
        if not device or not merchant:
            return Response(
                {"status": "error", "detail": "Device authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Update telemetry
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()

        battery = None
        if isinstance(request.data, dict) and 'battery_percentage' in request.data:
            try:
                battery = int(request.data.get('battery_percentage'))
            except (ValueError, TypeError):
                pass

        device.record_sync(battery=battery, ip=ip)

        # Extract items to sync
        raw_items = []
        if isinstance(request.data, list):
            raw_items = request.data
        elif isinstance(request.data, dict):
            if 'messages' in request.data and isinstance(request.data['messages'], list):
                raw_items = request.data['messages']
            elif 'trx_id' in request.data:
                raw_items = [request.data]

        if not raw_items:
            return Response({
                "status": "success",
                "message": "Heartbeat recorded. No SMS messages received.",
                "synced_count": 0,
                "duplicates_count": 0,
                "device": device.device_name
            }, status=status.HTTP_200_OK)

        synced = []
        duplicates = []
        errors = []

        for item_data in raw_items:
            serializer = SMSSyncItemSerializer(data=item_data)
            if not serializer.is_valid():
                errors.append({"item": item_data, "errors": serializer.errors})
                continue

            val = serializer.validated_data
            trx_id = val['trx_id']

            # Safely handle duplicate TrxID per merchant
            if SMSTransaction.objects.filter(merchant=merchant, trx_id=trx_id).exists():
                duplicates.append(trx_id)
                continue

            try:
                sms_obj = SMSTransaction.objects.create(
                    merchant=merchant,
                    device=device,
                    provider=val.get('provider', MFSProvider.BKASH),
                    sender=val['sender'],
                    trx_id=trx_id,
                    amount=val['amount'],
                    counterpart_number=val.get('counterpart_number', ''),
                    raw_sms=val.get('raw_sms', ''),
                    received_at=val.get('received_at', timezone.now()),
                    status=SMSTransactionStatus.UNUSED
                )
                synced.append(trx_id)
            except IntegrityError:
                # Concurrent race condition insertion for identical TrxID safely handled
                duplicates.append(trx_id)

        return Response({
            "status": "success",
            "message": f"Processed {len(raw_items)} SMS record(s).",
            "synced_count": len(synced),
            "duplicates_count": len(duplicates),
            "synced_trx_ids": synced,
            "duplicate_trx_ids": duplicates,
            "errors": errors if errors else None,
            "device": device.device_name,
            "last_synced_at": device.last_synced_at.isoformat()
        }, status=status.HTTP_200_OK)


class CheckoutVerifyAPIView(views.APIView):
    """
    POST /api/v1/checkout/<uuid:reference_id>/verify/
    Verify and settle invoice with customer-submitted TrxID.
    Uses pessimistic database-level locking (select_for_update) inside an atomic transaction.
    Triggers HMAC-signed webhook to merchant server upon success.
    """
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, reference_id, *args, **kwargs):
        serializer = CheckoutVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        trx_id = serializer.validated_data['trx_id']
        sender_number = serializer.validated_data.get('sender_number')

        # Atomically verify and settle invoice with pessimistic lock
        invoice = verify_and_settle_invoice(
            reference_id=reference_id,
            trx_id=trx_id,
            sender_number=sender_number
        )

        return Response({
            "status": "success",
            "message": "Payment verified and settled successfully.",
            "invoice_id": str(invoice.id),
            "reference_id": str(invoice.reference_id),
            "order_id": invoice.order_id,
            "amount": str(invoice.amount),
            "currency": invoice.currency,
            "trx_id": invoice.trx_id,
            "invoice_status": invoice.status,
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            "return_url": invoice.callback_url or invoice.merchant.return_url or None
        }, status=status.HTTP_200_OK)


class CheckoutDetailAPIView(views.APIView):
    """
    GET /api/v1/checkout/<uuid:reference_id>/
    Fetch invoice details, status, expiration countdown, and merchant payment accounts.
    """
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, reference_id, *args, **kwargs):
        try:
            invoice = Invoice.objects.select_related('merchant', 'payment_method').get(
                reference_id=reference_id
            )
        except Invoice.DoesNotExist:
            return Response(
                {"status": "error", "detail": "Invoice not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        invoice.check_expiration()
        serializer = CheckoutDetailSerializer(invoice, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


def checkout_page_view(request, reference_id):
    """
    Renders customer hosted checkout page (checkout.html) with active MFS accounts,
    15-minute countdown timer, copy buttons, and AJAX verification.
    """
    from django.shortcuts import render, get_object_or_404

    invoice = get_object_or_404(
        Invoice.objects.select_related('merchant', 'payment_method'),
        reference_id=reference_id
    )
    invoice.check_expiration()

    payment_methods = list(
        invoice.merchant.payment_methods.filter(is_active=True).order_by('display_order', 'created_at')
    )

    now = timezone.now()
    if invoice.status == InvoiceStatus.PENDING and invoice.expires_at > now:
        remaining_seconds = max(0, int((invoice.expires_at - now).total_seconds()))
    else:
        remaining_seconds = 0

    return_url = invoice.callback_url or invoice.merchant.return_url or '#'

    context = {
        'invoice': invoice,
        'merchant': invoice.merchant,
        'payment_methods': payment_methods,
        'remaining_seconds': remaining_seconds,
        'return_url': return_url,
    }
    return render(request, 'checkout.html', context)


@login_required(login_url='login')
@never_cache
def merchant_dashboard_view(request):
    """
    Renders the installable PWA Merchant Dashboard with multi-tenant stats,
    credentials, payment accounts, Android forwarders, and live transaction logs.
    """
    from django.shortcuts import render
    from django.db.models import Sum

    if request.user.is_superuser:
        return redirect('admin-dashboard')

    selected_merchant = getattr(request.user, 'merchant_profile', None)
    if selected_merchant is None or not selected_merchant.is_active:
        return HttpResponseForbidden('This account has no active merchant workspace.')
    merchants = [selected_merchant]
    branding_form = MerchantBrandingForm(initial={
        'checkout_display_name': selected_merchant.checkout_display_name,
        'checkout_copyright': selected_merchant.checkout_copyright,
        'support_email': selected_merchant.support_email,
        'support_phone': selected_merchant.support_phone,
    })

    if request.method == 'POST' and request.POST.get('form_action') == 'save_branding':
        branding_form = MerchantBrandingForm(request.POST, request.FILES)
        if branding_form.is_valid():
            old_logo = selected_merchant.logo.name if selected_merchant.logo else ''
            clear_logo = branding_form.cleaned_data['clear_logo']
            selected_merchant.checkout_display_name = branding_form.cleaned_data['checkout_display_name'].strip()
            selected_merchant.checkout_copyright = branding_form.cleaned_data['checkout_copyright'].strip()
            selected_merchant.support_email = branding_form.cleaned_data['support_email'].strip()
            selected_merchant.support_phone = branding_form.cleaned_data['support_phone'].strip()
            if branding_form.cleaned_data['logo']:
                selected_merchant.logo = branding_form.cleaned_data['logo']
            elif clear_logo:
                selected_merchant.logo = None
            selected_merchant.save()
            if old_logo and (branding_form.cleaned_data['logo'] or clear_logo):
                selected_merchant.logo.storage.delete(old_logo)
            messages.success(request, 'Checkout branding saved.')
            return redirect('/dashboard/#merchant-branding')
        messages.error(request, 'Please check the checkout branding fields and try again.')

    total_volume = Decimal('0.00')
    completed_count = 0
    pending_count = 0
    active_devices_count = 0
    payment_methods = []
    devices = []
    recent_invoices = []

    if selected_merchant:
        invoices_qs = selected_merchant.invoices.all()
        vol_agg = invoices_qs.filter(status=InvoiceStatus.COMPLETED).aggregate(Sum('amount'))
        total_volume = vol_agg['amount__sum'] or Decimal('0.00')
        completed_count = invoices_qs.filter(status=InvoiceStatus.COMPLETED).count()
        pending_count = invoices_qs.filter(status=InvoiceStatus.PENDING).count()
        active_devices_count = selected_merchant.devices.filter(is_active=True).count()
        payment_methods = selected_merchant.payment_methods.all().order_by('display_order', 'created_at')
        devices = selected_merchant.devices.all().order_by('-created_at')
        recent_invoices = invoices_qs.order_by('-created_at')[:15]

    context = {
        'merchants': merchants,
        'selected_merchant': selected_merchant,
        'total_volume': total_volume,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'active_devices_count': active_devices_count,
        'payment_methods': payment_methods,
        'payment_provider_choices': MFSProvider.choices,
        'payment_account_type_choices': AccountType.choices,
        'devices': devices,
        'recent_invoices': recent_invoices,
        'now_ts': int(timezone.now().timestamp()),
        'branding_form': branding_form,
    }
    return render(request, 'dashboard.html', context)


@login_required(login_url='login')
@never_cache
def merchant_integration_guide_view(request):
    if request.user.is_superuser:
        return redirect('admin-dashboard')
    merchant = getattr(request.user, 'merchant_profile', None)
    if merchant is None or not merchant.is_active:
        return HttpResponseForbidden('This account has no active merchant workspace.')
    return render(request, 'merchant_integration_guide.html', {'selected_merchant': merchant})


@login_required(login_url='login')
@require_POST
@never_cache
def merchant_payment_method_action(request):
    """Let a merchant manage only payment methods belonging to its own workspace."""
    if request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Merchant account required.'}, status=403)
    merchant = getattr(request.user, 'merchant_profile', None)
    if merchant is None or not merchant.is_active:
        return JsonResponse({'status': 'error', 'message': 'Active merchant workspace required.'}, status=403)

    if request.content_type == 'multipart/form-data':
        data = request.POST
    else:
        try:
            data = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON body.'}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({'status': 'error', 'message': 'Invalid request data.'}, status=400)

    action = data.get('action')
    if action in ('create', 'update'):
        provider = str(data.get('provider', '')).upper()
        account_type = str(data.get('account_type', '')).upper()
        account_number = str(data.get('account_number', '')).strip()
        if provider not in dict(MFSProvider.choices):
            return JsonResponse({'status': 'error', 'message': 'Select a valid payment provider.'}, status=400)
        if account_type not in dict(AccountType.choices):
            return JsonResponse({'status': 'error', 'message': 'Select a valid account type.'}, status=400)
        if (provider != MFSProvider.BANGLA_QR and not account_number) or len(account_number) > 32:
            return JsonResponse({'status': 'error', 'message': 'Enter an account number up to 32 characters.'}, status=400)
        try:
            fee = Decimal(str(data.get('charge_percentage', '0') or '0'))
            if not fee.is_finite() or fee < 0 or fee > 100 or fee.as_tuple().exponent < -2:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Charge must be between 0 and 100 with up to 2 decimals.'}, status=400)

        if action == 'create':
            payment_method = PaymentMethod(merchant=merchant)
        else:
            payment_method = PaymentMethod.objects.filter(merchant=merchant, id=data.get('id')).first()
            if payment_method is None:
                return JsonResponse({'status': 'error', 'message': 'Payment account not found.'}, status=404)

        uploaded_qr = request.FILES.get('qr_code')
        if uploaded_qr:
            qr_form = PaymentQRCodeUploadForm(files=MultiValueDict({'qr_code': [uploaded_qr]}))
            if not qr_form.is_valid():
                return JsonResponse({'status': 'error', 'message': qr_form.errors['qr_code'][0]}, status=400)
            uploaded_qr = qr_form.cleaned_data['qr_code']
        clear_qr = str(data.get('clear_qr', '')).lower() in ('1', 'true', 'yes', 'on')
        if provider == MFSProvider.BANGLA_QR and not uploaded_qr and (not payment_method.qr_code or clear_qr):
            return JsonResponse({'status': 'error', 'message': 'Upload the merchant-issued Bangla QR image to continue.'}, status=400)

        old_qr_name = payment_method.qr_code.name if payment_method.qr_code else ''
        qr_storage = PaymentMethod._meta.get_field('qr_code').storage
        payment_method.provider = provider
        payment_method.account_type = account_type
        payment_method.account_number = account_number
        payment_method.instructions = str(data.get('instructions', '')).strip()
        payment_method.charge_percentage = fee
        active_value = data.get('is_active', True)
        payment_method.is_active = active_value if isinstance(active_value, bool) else str(active_value).lower() in ('1', 'true', 'yes', 'on')
        if uploaded_qr:
            payment_method.qr_code = uploaded_qr
        elif clear_qr:
            payment_method.qr_code = None
        payment_method.save()
        if old_qr_name and (uploaded_qr or clear_qr):
            qr_storage.delete(old_qr_name)
        return JsonResponse({
            'status': 'success',
            'id': str(payment_method.id),
            'message': f'{payment_method.get_provider_display()} payment account saved.',
        })

    payment_method = PaymentMethod.objects.filter(merchant=merchant, id=data.get('id')).first()
    if payment_method is None:
        return JsonResponse({'status': 'error', 'message': 'Payment account not found.'}, status=404)
    if action == 'toggle':
        payment_method.is_active = not payment_method.is_active
        payment_method.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({'status': 'success', 'is_active': payment_method.is_active})
    if action == 'delete':
        if payment_method.qr_code:
            payment_method.qr_code.delete(save=False)
        payment_method.delete()
        return JsonResponse({'status': 'success', 'message': 'Payment account removed.'})
    return JsonResponse({'status': 'error', 'message': 'Unknown action.'}, status=400)


@require_GET
def payment_method_qr_view(request, payment_method_id):
    payment_method = PaymentMethod.objects.filter(id=payment_method_id).first()
    if payment_method is None or not payment_method.qr_code:
        raise Http404('Payment QR not found.')
    try:
        qr_file = payment_method.qr_code.open('rb')
    except OSError as exc:
        raise Http404('Payment QR not found.') from exc
    try:
        from PIL import Image
        with Image.open(qr_file) as image:
            content_type = {
                'PNG': 'image/png',
                'JPEG': 'image/jpeg',
                'WEBP': 'image/webp',
            }.get(image.format)
        qr_file.seek(0)
    except (OSError, ValueError):
        qr_file.close()
        raise Http404('Invalid payment QR image.')
    if content_type not in {'image/png', 'image/jpeg', 'image/webp'}:
        qr_file.close()
        raise Http404('Unsupported payment QR image.')
    response = FileResponse(qr_file, content_type=content_type)
    response['Cache-Control'] = 'public, max-age=300'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@require_GET
def merchant_logo_view(request, merchant_id):
    merchant = Merchant.objects.filter(id=merchant_id).only('logo').first()
    if merchant is None or not merchant.logo:
        raise Http404('Merchant logo not found.')
    try:
        logo_file = merchant.logo.open('rb')
        from PIL import Image
        with Image.open(logo_file) as image:
            content_type = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}.get(image.format)
        logo_file.seek(0)
    except (OSError, ValueError) as exc:
        if 'logo_file' in locals():
            logo_file.close()
        raise Http404('Invalid merchant logo.') from exc
    if content_type not in {'image/png', 'image/jpeg', 'image/webp'}:
        logo_file.close()
        raise Http404('Unsupported merchant logo.')
    response = FileResponse(logo_file, content_type=content_type)
    response['Cache-Control'] = 'public, max-age=300'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def service_worker_view(request):
    """
    Serves serviceworker.js at root /serviceworker.js with Service-Worker-Allowed header.
    """
    import os
    from django.conf import settings
    from django.http import HttpResponse, HttpResponseNotFound

    sw_path = os.path.join(settings.BASE_DIR, 'static', 'serviceworker.js')
    if not os.path.exists(sw_path):
        return HttpResponseNotFound("Service worker not found.")

    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()

    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


def manifest_view(request):
    """
    Serves manifest.json at root /manifest.json.
    """
    import os
    from django.conf import settings
    from django.http import HttpResponse, HttpResponseNotFound

    manifest_path = os.path.join(settings.BASE_DIR, 'static', 'manifest.json')
    if not os.path.exists(manifest_path):
        return HttpResponseNotFound("Manifest not found.")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()

    response = HttpResponse(content, content_type='application/manifest+json')
    response['Cache-Control'] = 'no-cache'
    return response


@user_passes_test(lambda user: user.is_authenticated and user.is_superuser, login_url='login')
@never_cache
def admin_dashboard_view(request):
    """
    Renders the professional Admin Dashboard with sleek sidebar navigation,
    system-wide volume, forwarder telemetry, interactive sandbox, and real-time logs.
    """
    from django.shortcuts import render
    from django.db.models import Sum

    merchants = list(Merchant.objects.all().order_by('-created_at'))
    default_merchant = merchants[0] if merchants else None

    devices = list(Device.objects.select_related('merchant').all().order_by('-last_synced_at', '-created_at'))
    default_device = devices[0] if devices else None

    payment_methods = list(PaymentMethod.objects.select_related('merchant').all().order_by('display_order'))

    invoices_qs = Invoice.objects.select_related('merchant', 'payment_method').all()
    total_invoices_count = invoices_qs.count()
    completed_count = invoices_qs.filter(status=InvoiceStatus.COMPLETED).count()
    pending_count = invoices_qs.filter(status=InvoiceStatus.PENDING).count()
    expired_count = invoices_qs.filter(status=InvoiceStatus.EXPIRED).count()

    vol_agg = invoices_qs.filter(status=InvoiceStatus.COMPLETED).aggregate(Sum('amount'))
    total_volume = vol_agg['amount__sum'] or Decimal('0.00')

    active_devices_count = Device.objects.filter(is_active=True).count()
    recent_invoices = list(invoices_qs.order_by('-created_at')[:25])
    sms_logs = list(SMSTransaction.objects.select_related('merchant', 'device').all().order_by('-received_at')[:25])

    # Provider distribution stats
    bkash_count = PaymentMethod.objects.filter(provider=MFSProvider.BKASH).count()
    nagad_count = PaymentMethod.objects.filter(provider=MFSProvider.NAGAD).count()
    rocket_count = PaymentMethod.objects.filter(provider=MFSProvider.ROCKET).count()
    cellfin_count = PaymentMethod.objects.filter(provider=MFSProvider.CELLFIN).count()

    context = {
        'merchants': merchants,
        'default_merchant': default_merchant,
        'devices': devices,
        'default_device': default_device,
        'payment_methods': payment_methods,
        'total_invoices_count': total_invoices_count,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'expired_count': expired_count,
        'total_volume': total_volume,
        'active_devices_count': active_devices_count,
        'recent_invoices': recent_invoices,
        'sms_logs': sms_logs,
        'bkash_count': bkash_count,
        'nagad_count': nagad_count,
        'rocket_count': rocket_count,
        'cellfin_count': cellfin_count,
        'now_ts': int(timezone.now().timestamp()),
    }
    return render(request, 'admin_dashboard.html', context)


import secrets

@never_cache
def admin_action_api(request):
    """
    Unified JSON API for the Admin Dashboard to perform full CRUD on
    Merchants, Payment Methods, Android Devices, Invoices, and SMS logs
    without having to navigate to Django standard admin.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required.'}, status=401)
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Super Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed.'}, status=405)

    if request.content_type == 'multipart/form-data':
        data = request.POST
    else:
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON body.'}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({'status': 'error', 'message': 'Invalid request data.'}, status=400)

    action = data.get('action')

    # ==========================
    # 1. MERCHANT ACTIONS
    # ==========================
    if action == 'create_merchant':
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        requested_username = data.get('username', '').strip()
        if not name:
            return JsonResponse({'status': 'error', 'message': 'Merchant name is required.'}, status=400)
        User = get_user_model()
        if email and User.objects.filter(email__iexact=email).exists():
            return JsonResponse({'status': 'error', 'message': 'An account with this email already exists.'}, status=400)
        if requested_username and User.objects.filter(username=requested_username).exists():
            return JsonResponse({'status': 'error', 'message': 'That username is already in use.'}, status=400)
        base_username = requested_username or (email.split('@', 1)[0] if email else '')
        base_username = slugify(base_username or name).replace('-', '_')[:140] or 'merchant'
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f'{base_username[:145]}_{suffix}'
        password = data.get('password') or secrets.token_urlsafe(15)
        if len(password) < 8:
            return JsonResponse({'status': 'error', 'message': 'Password must be at least 8 characters long.'}, status=400)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    is_staff=False,
                    is_superuser=False,
                )
                merchant = Merchant.objects.create(
                    owner=user,
                    name=name,
                    email=email or None,
                    webhook_url=data.get('webhook_url', '').strip() or None,
                    return_url=data.get('return_url', '').strip() or None,
                    is_active=bool(data.get('is_active', True)),
                )
        except IntegrityError:
            return JsonResponse({'status': 'error', 'message': 'Could not create account; check the username and email.'}, status=400)
        return JsonResponse({
            'status': 'success',
            'message': f'Merchant "{merchant.name}" and its login account were created successfully.',
            'merchant': {
                'id': str(merchant.id),
                'name': merchant.name,
                'api_key': merchant.api_key,
                'api_secret': merchant.api_secret
            },
            'account': {'username': username, 'password': password},
        })

    elif action == 'toggle_merchant':
        m_id = data.get('id')
        merchant = Merchant.objects.filter(id=m_id).first()
        if not merchant:
            return JsonResponse({'status': 'error', 'message': 'Merchant not found.'}, status=404)
        merchant.is_active = not merchant.is_active
        merchant.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({
            'status': 'success',
            'is_active': merchant.is_active,
            'message': f'Merchant status set to {"Active" if merchant.is_active else "Inactive"}.'
        })

    elif action == 'regenerate_merchant_keys':
        m_id = data.get('id')
        merchant = Merchant.objects.filter(id=m_id).first()
        if not merchant:
            return JsonResponse({'status': 'error', 'message': 'Merchant not found.'}, status=404)
        merchant.regenerate_credentials(save=True)
        return JsonResponse({
            'status': 'success',
            'message': 'API credentials regenerated successfully.',
            'api_key': merchant.api_key,
            'api_secret': merchant.api_secret
        })

    elif action == 'delete_merchant':
        m_id = data.get('id')
        merchant = Merchant.objects.filter(id=m_id).first()
        if not merchant:
            return JsonResponse({'status': 'error', 'message': 'Merchant not found.'}, status=404)
        m_name = merchant.name
        merchant.delete()
        return JsonResponse({'status': 'success', 'message': f'Merchant "{m_name}" deleted.'})

    # ==========================
    # 2. PAYMENT METHOD ACTIONS
    # ==========================
    elif action == 'create_payment_method':
        m_id = data.get('merchant_id')
        merchant = Merchant.objects.filter(id=m_id).first()
        if not merchant:
            return JsonResponse({'status': 'error', 'message': 'Merchant not found.'}, status=404)

        provider = data.get('provider', 'BKASH').upper()
        account_number = data.get('account_number', '').strip()
        account_type = data.get('account_type', 'PERSONAL').upper()
        if provider not in dict(MFSProvider.choices):
            return JsonResponse({'status': 'error', 'message': 'Select a valid payment provider.'}, status=400)
        if account_type not in dict(AccountType.choices):
            return JsonResponse({'status': 'error', 'message': 'Select a valid account type.'}, status=400)
        if not account_number and provider != MFSProvider.BANGLA_QR:
            return JsonResponse({'status': 'error', 'message': 'Account number is required.'}, status=400)

        uploaded_qr = request.FILES.get('qr_code')
        if uploaded_qr:
            qr_form = PaymentQRCodeUploadForm(files=MultiValueDict({'qr_code': [uploaded_qr]}))
            if not qr_form.is_valid():
                return JsonResponse({'status': 'error', 'message': qr_form.errors['qr_code'][0]}, status=400)
            uploaded_qr = qr_form.cleaned_data['qr_code']
        if provider == MFSProvider.BANGLA_QR and not uploaded_qr:
            return JsonResponse({'status': 'error', 'message': 'Upload the merchant-issued Bangla QR image.'}, status=400)

        pm = PaymentMethod(
            merchant=merchant,
            provider=provider,
            account_type=account_type,
            account_number=account_number,
            instructions=data.get('instructions', '').strip(),
            charge_percentage=Decimal(str(data.get('charge_percentage', '0.00') or '0.00')),
            display_order=int(data.get('display_order', 0) or 0),
            is_active=True
        )
        if uploaded_qr:
            pm.qr_code = uploaded_qr
        pm.save()
        return JsonResponse({
            'status': 'success',
            'message': f'{pm.get_provider_display()} payment method added successfully.',
            'id': str(pm.id)
        })

    elif action == 'toggle_payment_method':
        pm_id = data.get('id')
        pm = PaymentMethod.objects.filter(id=pm_id).first()
        if not pm:
            return JsonResponse({'status': 'error', 'message': 'Payment method not found.'}, status=404)
        pm.is_active = not pm.is_active
        pm.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({
            'status': 'success',
            'is_active': pm.is_active,
            'message': f'Payment method {"activated" if pm.is_active else "deactivated"}.'
        })

    elif action == 'delete_payment_method':
        pm_id = data.get('id')
        pm = PaymentMethod.objects.filter(id=pm_id).first()
        if not pm:
            return JsonResponse({'status': 'error', 'message': 'Payment method not found.'}, status=404)
        if pm.qr_code:
            pm.qr_code.delete(save=False)
        pm.delete()
        return JsonResponse({'status': 'success', 'message': 'Payment method removed.'})

    # ==========================
    # 3. DEVICE ACTIONS
    # ==========================
    elif action == 'create_device':
        m_id = data.get('merchant_id')
        merchant = Merchant.objects.filter(id=m_id).first()
        if not merchant:
            return JsonResponse({'status': 'error', 'message': 'Merchant not found.'}, status=404)

        dev_name = data.get('device_name', '').strip() or 'Android Bridge Phone'
        device = Device.objects.create(
            merchant=merchant,
            device_name=dev_name,
            model_name=data.get('model_name', '').strip() or 'Generic Android',
            sim_slot=data.get('sim_slot', '').strip() or 'SIM 1',
            is_active=bool(data.get('is_active', True))
        )
        return JsonResponse({
            'status': 'success',
            'message': f'Device "{device.device_name}" added successfully.',
            'device_token': device.device_token,
            'id': str(device.id)
        })

    elif action == 'regenerate_device_token':
        dev_id = data.get('id')
        device = Device.objects.filter(id=dev_id).first()
        if not device:
            return JsonResponse({'status': 'error', 'message': 'Device not found.'}, status=404)
        from .models import generate_device_token
        device.device_token = generate_device_token()
        device.save(update_fields=['device_token', 'updated_at'])
        return JsonResponse({
            'status': 'success',
            'device_token': device.device_token,
            'message': 'Device token regenerated successfully.'
        })

    elif action == 'toggle_device':
        dev_id = data.get('id')
        device = Device.objects.filter(id=dev_id).first()
        if not device:
            return JsonResponse({'status': 'error', 'message': 'Device not found.'}, status=404)
        device.is_active = not device.is_active
        device.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({
            'status': 'success',
            'is_active': device.is_active,
            'message': f'Device status set to {"Active" if device.is_active else "Inactive"}.'
        })

    elif action == 'delete_device':
        dev_id = data.get('id')
        device = Device.objects.filter(id=dev_id).first()
        if not device:
            return JsonResponse({'status': 'error', 'message': 'Device not found.'}, status=404)
        device.delete()
        return JsonResponse({'status': 'success', 'message': 'Device removed.'})

    # ==========================
    # 4. INVOICE ACTIONS
    # ==========================
    elif action == 'create_invoice':
        m_id = data.get('merchant_id')
        merchant = Merchant.objects.filter(id=m_id).first()
        if not merchant:
            return JsonResponse({'status': 'error', 'message': 'Merchant not found.'}, status=404)

        amount_raw = data.get('amount')
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError()
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Valid amount greater than 0 is required.'}, status=400)

        order_id = data.get('order_id', '').strip() or f"ORD-{secrets.token_hex(4).upper()}"
        invoice = Invoice.objects.create(
            merchant=merchant,
            order_id=order_id,
            amount=amount,
            customer_name=data.get('customer_name', '').strip() or 'Manual Customer',
            customer_email=data.get('customer_email', '').strip() or None,
            customer_phone=data.get('customer_phone', '').strip() or '',
            status=InvoiceStatus.PENDING
        )
        return JsonResponse({
            'status': 'success',
            'message': f'Invoice {invoice.order_id} created.',
            'invoice_id': str(invoice.id),
            'reference_id': str(invoice.reference_id),
            'checkout_url': f"/checkout/{invoice.reference_id}/"
        })

    elif action == 'mark_invoice_paid':
        inv_id = data.get('id')
        invoice = Invoice.objects.filter(id=inv_id).first()
        if not invoice:
            return JsonResponse({'status': 'error', 'message': 'Invoice not found.'}, status=404)
        invoice.status = InvoiceStatus.COMPLETED
        invoice.trx_id = data.get('trx_id', '').strip() or f"MANUAL-{secrets.token_hex(4).upper()}"
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=['status', 'trx_id', 'paid_at', 'updated_at'])
        return JsonResponse({'status': 'success', 'message': f'Invoice marked as PAID (TrxID: {invoice.trx_id}).'})

    elif action == 'cancel_invoice':
        inv_id = data.get('id')
        invoice = Invoice.objects.filter(id=inv_id).first()
        if not invoice:
            return JsonResponse({'status': 'error', 'message': 'Invoice not found.'}, status=404)
        invoice.status = InvoiceStatus.CANCELLED
        invoice.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'status': 'success', 'message': 'Invoice cancelled.'})

    elif action == 'delete_invoice':
        inv_id = data.get('id')
        invoice = Invoice.objects.filter(id=inv_id).first()
        if not invoice:
            return JsonResponse({'status': 'error', 'message': 'Invoice not found.'}, status=404)
        invoice.delete()
        return JsonResponse({'status': 'success', 'message': 'Invoice deleted.'})

    # ==========================
    # 5. SMS LOG ACTIONS
    # ==========================
    elif action == 'delete_sms':
        sms_id = data.get('id')
        sms = SMSTransaction.objects.filter(id=sms_id).first()
        if not sms:
            return JsonResponse({'status': 'error', 'message': 'SMS log not found.'}, status=404)
        sms.delete()
        return JsonResponse({'status': 'success', 'message': 'SMS log deleted.'})

    elif action == 'clear_unmatched_sms':
        deleted_count, _ = SMSTransaction.objects.filter(status=SMSTransactionStatus.UNUSED).delete()
        return JsonResponse({'status': 'success', 'message': f'Cleared {deleted_count} unused SMS log records.'})

    return JsonResponse({'status': 'error', 'message': f'Unknown action: {action}'}, status=400)


# =====================================================================
# SMS FORWARDER APP DOWNLOAD VIEWS
# =====================================================================
import os
from django.conf import settings
from django.http import FileResponse, Http404

def download_sms_forwarder_apk(request):
    """Serve the SMS Forwarder Android APK directly for instant install."""
    apk_path = settings.BASE_DIR / 'static' / 'downloads' / 'sms-forwarder.apk'
    if not os.path.exists(apk_path):
        raise Http404("SMS Forwarder APK not found.")
    return FileResponse(
        open(apk_path, 'rb'),
        content_type='application/vnd.android.package-archive',
        as_attachment=True,
        filename='SMS_Forwarder.apk'
    )


def download_sms_forwarder_source(request):
    """Serve the complete Android Studio source code as a ZIP archive."""
    zip_path = settings.BASE_DIR / 'static' / 'downloads' / 'mfs-forwarder-source.zip'
    if not os.path.exists(zip_path):
        raise Http404("Source package not found.")
    return FileResponse(
        open(zip_path, 'rb'),
        content_type='application/zip',
        as_attachment=True,
        filename='mfs-sms-forwarder-source.zip'
    )

