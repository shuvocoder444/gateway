from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta
from decimal import Decimal

from .models import (
    Merchant,
    PaymentMethod,
    Device,
    Invoice,
    SMSTransaction,
    InvoiceStatus,
    SMSTransactionStatus,
    MFSProvider
)

admin.site.site_header = "MFS Payment Gateway Administration"
admin.site.site_title = "Gateway Admin Portal"
admin.site.index_title = "Multi-Tenant Payment Aggregator & Device Bridge"


class PaymentMethodInline(admin.TabularInline):
    model = PaymentMethod
    extra = 0
    fields = ('provider', 'account_type', 'account_number', 'charge_percentage', 'is_active', 'display_order')
    show_change_link = True


class DeviceInline(admin.TabularInline):
    model = Device
    extra = 0
    fields = ('device_name', 'device_token_preview', 'sim_slot', 'battery_status', 'is_active', 'last_synced_at')
    readonly_fields = ('device_token_preview', 'battery_status', 'last_synced_at')
    show_change_link = True

    def device_token_preview(self, obj):
        if obj.device_token:
            return f"{obj.device_token[:8]}...{obj.device_token[-4:]}"
        return "-"
    device_token_preview.short_description = "Device Token"

    def battery_status(self, obj):
        if obj.battery_percentage is None:
            return "-"
        return f"{obj.battery_percentage}%"
    battery_status.short_description = "Battery"


class SMSTransactionInline(admin.TabularInline):
    model = SMSTransaction
    extra = 0
    fk_name = 'matched_invoice'
    fields = ('trx_id', 'provider', 'amount', 'sender', 'status', 'received_at')
    readonly_fields = ('trx_id', 'provider', 'amount', 'sender', 'status', 'received_at')
    can_delete = False
    show_change_link = True
    verbose_name = "Settled SMS Transaction"
    verbose_name_plural = "Settled SMS Transactions"


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'api_key_badge',
        'active_payment_methods',
        'active_devices',
        'webhook_url_preview',
        'status_badge',
        'created_at',
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'email', 'api_key', 'id')
    readonly_fields = ('id', 'api_key', 'api_secret', 'created_at', 'updated_at')
    fieldsets = (
        ('Tenant Profile', {
            'fields': ('id', 'name', 'email', 'is_active')
        }),
        ('API Authentication & Security', {
            'description': 'Merchant credentials for API request authorization and HMAC signatures.',
            'fields': ('api_key', 'api_secret')
        }),
        ('Webhook & Callbacks', {
            'fields': ('webhook_url', 'return_url', 'cancel_url')
        }),
        ('System Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        }),
    )
    inlines = [PaymentMethodInline, DeviceInline]
    actions = ['regenerate_credentials_action', 'activate_merchants', 'deactivate_merchants']

    def api_key_badge(self, obj):
        key = obj.api_key
        return format_html(
            '<code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-weight: 600; color: #0f172a;">{}...</code>',
            key[:16]
        )
    api_key_badge.short_description = 'API Key'

    def active_payment_methods(self, obj):
        count = obj.payment_methods.filter(is_active=True).count()
        total = obj.payment_methods.count()
        return format_html('<span style="font-weight: 500;">{}/{} active</span>', count, total)
    active_payment_methods.short_description = 'Payment Accounts'

    def active_devices(self, obj):
        count = obj.devices.filter(is_active=True).count()
        return format_html('<span style="font-weight: 500;">{} device(s)</span>', count)
    active_devices.short_description = 'Forwarder Devices'

    def webhook_url_preview(self, obj):
        if not obj.webhook_url:
            return format_html('<span style="color: #94a3b8; font-style: italic;">Not set</span>')
        return format_html('<a href="{}" target="_blank" style="color: #2563eb; text-decoration: none;">🔗 {}</a>', obj.webhook_url, obj.webhook_url[:30])
    webhook_url_preview.short_description = 'Webhook'

    def status_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="background-color: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 11px;">ACTIVE</span>'
            )
        return format_html(
            '<span style="background-color: #fee2e2; color: #b91c1c; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 11px;">DISABLED</span>'
        )
    status_badge.short_description = 'Status'

    @admin.action(description='Regenerate API Key and Secret for selected merchants')
    def regenerate_credentials_action(self, request, queryset):
        for merchant in queryset:
            merchant.regenerate_credentials(save=True)
        self.message_user(
            request,
            f"Successfully regenerated API credentials for {queryset.count()} merchant(s).",
            messages.SUCCESS
        )

    @admin.action(description='Activate selected merchants')
    def activate_merchants(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Selected merchants activated.", messages.SUCCESS)

    @admin.action(description='Deactivate selected merchants')
    def deactivate_merchants(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Selected merchants deactivated.", messages.WARNING)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = (
        'provider_badge',
        'account_type_badge',
        'account_number',
        'merchant_link',
        'charge_percentage',
        'display_order',
        'status_badge',
        'created_at',
    )
    list_filter = ('provider', 'account_type', 'is_active', 'merchant')
    search_fields = ('account_number', 'merchant__name', 'instructions')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Account Info', {
            'fields': ('id', 'merchant', 'provider', 'account_type', 'account_number', 'charge_percentage', 'display_order', 'is_active')
        }),
        ('Customer Instructions & QR', {
            'fields': ('instructions', 'qr_code')
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        })
    )
    actions = ['enable_methods', 'disable_methods']

    def provider_badge(self, obj):
        colors = {
            MFSProvider.BKASH: ('#e2136e', '#ffffff'),
            MFSProvider.NAGAD: ('#f7941d', '#ffffff'),
            MFSProvider.ROCKET: ('#8c3494', '#ffffff'),
            MFSProvider.CELLFIN: ('#00693e', '#ffffff'),
            MFSProvider.UPAY: ('#ffcd00', '#000000'),
            MFSProvider.OTHER: ('#475569', '#ffffff'),
        }
        bg, fg = colors.get(obj.provider, ('#475569', '#ffffff'))
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 11px;">{}</span>',
            bg, fg, obj.get_provider_display()
        )
    provider_badge.short_description = 'Provider'

    def account_type_badge(self, obj):
        return format_html(
            '<span style="background: #f1f5f9; color: #334155; padding: 2px 6px; border-radius: 4px; font-weight: 500; font-size: 11px;">{}</span>',
            obj.get_account_type_display()
        )
    account_type_badge.short_description = 'Type'

    def merchant_link(self, obj):
        url = reverse('admin:gateway_merchant_change', args=[obj.merchant.pk])
        return format_html('<a href="{}" style="color: #2563eb; font-weight: 500;">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #16a34a; font-weight: 600;">Active</span>')
        return format_html('<span style="color: #dc2626; font-weight: 600;">Disabled</span>')
    status_badge.short_description = 'Status'

    @admin.action(description='Enable selected payment methods')
    def enable_methods(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description='Disable selected payment methods')
    def disable_methods(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        'device_name',
        'merchant_link',
        'token_badge',
        'sim_slot',
        'battery_badge',
        'connectivity_badge',
        'last_synced_at',
        'status_badge',
    )
    list_filter = ('is_active', 'sim_slot', 'merchant', 'last_synced_at')
    search_fields = ('device_name', 'device_token', 'model_name', 'merchant__name')
    readonly_fields = ('id', 'device_token', 'last_synced_at', 'created_at', 'updated_at')
    fieldsets = (
        ('Device Identity', {
            'fields': ('id', 'merchant', 'device_name', 'model_name', 'sim_slot', 'is_active')
        }),
        ('Forwarder Authentication Token', {
            'description': 'Supply this token in the Android app header: X-DEVICE-TOKEN',
            'fields': ('device_token',)
        }),
        ('Telemetry & Sync Status', {
            'fields': ('battery_percentage', 'ip_address', 'last_synced_at')
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        })
    )

    def merchant_link(self, obj):
        url = reverse('admin:gateway_merchant_change', args=[obj.merchant.pk])
        return format_html('<a href="{}" style="color: #2563eb; font-weight: 500;">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def token_badge(self, obj):
        return format_html(
            '<code style="background: #f8fafc; padding: 2px 6px; border: 1px solid #e2e8f0; border-radius: 4px; font-size: 11px;">{}...{}</code>',
            obj.device_token[:8],
            obj.device_token[-4:]
        )
    token_badge.short_description = 'Device Token'

    def battery_badge(self, obj):
        if obj.battery_percentage is None:
            return format_html('<span style="color: #94a3b8;">N/A</span>')
        lvl = obj.battery_percentage
        color = '#16a34a' if lvl >= 50 else ('#ea580c' if lvl >= 20 else '#dc2626')
        return format_html(
            '<span style="color: {}; font-weight: 700;">🔋 {}%</span>',
            color, lvl
        )
    battery_badge.short_description = 'Battery'

    def connectivity_badge(self, obj):
        if not obj.last_synced_at:
            return format_html('<span style="color: #94a3b8;">Never</span>')
        diff = timezone.now() - obj.last_synced_at
        if diff < timedelta(minutes=10):
            return format_html('<span style="background: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 10px; font-size: 10px; font-weight: 700;">🟢 ONLINE</span>')
        elif diff < timedelta(hours=1):
            return format_html('<span style="background: #fef9c3; color: #854d0e; padding: 2px 6px; border-radius: 10px; font-size: 10px; font-weight: 700;">🟡 IDLE</span>')
        return format_html('<span style="background: #fee2e2; color: #991b1b; padding: 2px 6px; border-radius: 10px; font-size: 10px; font-weight: 700;">🔴 OFFLINE</span>')
    connectivity_badge.short_description = 'Bridge Status'

    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #16a34a; font-weight: 600;">Active</span>')
        return format_html('<span style="color: #dc2626; font-weight: 600;">Inactive</span>')
    status_badge.short_description = 'Active'


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'checkout_link',
        'merchant_link',
        'order_id',
        'amount_display',
        'status_badge',
        'trx_id_display',
        'customer_info',
        'expiration_status',
        'webhook_status',
        'created_at',
    )
    list_filter = ('status', 'webhook_delivered', 'merchant', 'created_at')
    search_fields = ('reference_id', 'order_id', 'trx_id', 'customer_phone', 'customer_email', 'merchant__name')
    readonly_fields = ('id', 'reference_id', 'created_at', 'updated_at', 'paid_at')
    fieldsets = (
        ('Invoice Reference & Merchant', {
            'fields': ('id', 'reference_id', 'merchant', 'order_id')
        }),
        ('Payment Specification', {
            'fields': ('amount', 'currency', 'status', 'payment_method', 'trx_id', 'sender_number', 'paid_at')
        }),
        ('Customer Details', {
            'fields': ('customer_name', 'customer_email', 'customer_phone')
        }),
        ('Lifecycle & Expiration (15-min)', {
            'fields': ('expires_at',)
        }),
        ('Webhook & IPN Delivery', {
            'fields': ('callback_url', 'webhook_delivered', 'webhook_response_code')
        }),
        ('Arbitrary Metadata', {
            'classes': ('collapse',),
            'fields': ('metadata',)
        }),
        ('System Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        })
    )
    inlines = [SMSTransactionInline]
    actions = ['mark_as_completed_action', 'mark_as_expired_action', 'reset_to_pending_action']

    def checkout_link(self, obj):
        ref = str(obj.reference_id)
        return format_html(
            '<a href="/checkout/{}/" target="_blank" style="font-family: monospace; font-weight: 700; color: #2563eb; text-decoration: none;" title="Open Hosted Checkout">🔗 {}...{}</a>',
            ref, ref[:8], ref[-4:]
        )
    checkout_link.short_description = 'Checkout UUID'

    def merchant_link(self, obj):
        url = reverse('admin:gateway_merchant_change', args=[obj.merchant.pk])
        return format_html('<a href="{}" style="color: #0f172a; font-weight: 600;">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def amount_display(self, obj):
        return format_html('<span style="font-weight: 700; color: #047857;">{} {}</span>', obj.amount, obj.currency)
    amount_display.short_description = 'Amount'

    def status_badge(self, obj):
        status_styles = {
            InvoiceStatus.PENDING: ('#fef3c7', '#92400e'),
            InvoiceStatus.COMPLETED: ('#d1fae5', '#065f46'),
            InvoiceStatus.EXPIRED: ('#f1f5f9', '#475569'),
            InvoiceStatus.CANCELLED: ('#fee2e2', '#991b1b'),
        }
        bg, fg = status_styles.get(obj.status, ('#f1f5f9', '#334155'))
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; border-radius: 12px; font-weight: 700; font-size: 11px;">{}</span>',
            bg, fg, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def trx_id_display(self, obj):
        if obj.trx_id:
            return format_html('<code style="font-weight: 700; color: #1e40af;">{}</code>', obj.trx_id)
        return format_html('<span style="color: #94a3b8;">-</span>')
    trx_id_display.short_description = 'TrxID'

    def customer_info(self, obj):
        phone = obj.customer_phone or obj.customer_email or "-"
        return format_html('<span style="font-size: 12px;">{}</span>', phone)
    customer_info.short_description = 'Customer'

    def expiration_status(self, obj):
        if obj.status == InvoiceStatus.COMPLETED:
            return format_html('<span style="color: #059669; font-weight: 600;">Paid</span>')
        if obj.is_expired:
            return format_html('<span style="color: #dc2626; font-weight: 600;">Expired</span>')
        diff = obj.expires_at - timezone.now()
        minutes = max(0, int(diff.total_seconds() // 60))
        return format_html('<span style="color: #d97706; font-weight: 600;">{}m left</span>', minutes)
    expiration_status.short_description = 'Validity'

    def webhook_status(self, obj):
        if obj.webhook_delivered:
            return format_html('<span style="color: #16a34a; font-weight: 700;">✓ Delivered ({})</span>', obj.webhook_response_code or 200)
        return format_html('<span style="color: #94a3b8;">Pending</span>')
    webhook_status.short_description = 'Webhook'

    @admin.action(description='Mark selected invoices as COMPLETED')
    def mark_as_completed_action(self, request, queryset):
        queryset.update(status=InvoiceStatus.COMPLETED, paid_at=timezone.now())
        self.message_user(request, "Selected invoices marked as COMPLETED.", messages.SUCCESS)

    @admin.action(description='Mark selected invoices as EXPIRED')
    def mark_as_expired_action(self, request, queryset):
        queryset.update(status=InvoiceStatus.EXPIRED)
        self.message_user(request, "Selected invoices marked as EXPIRED.", messages.WARNING)

    @admin.action(description='Reset to PENDING with fresh 15-minute window')
    def reset_to_pending_action(self, request, queryset):
        queryset.update(
            status=InvoiceStatus.PENDING,
            expires_at=timezone.now() + timedelta(minutes=15),
            paid_at=None
        )
        self.message_user(request, "Selected invoices reset to PENDING with 15-min window.", messages.INFO)


@admin.register(SMSTransaction)
class SMSTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'trx_id_badge',
        'merchant_link',
        'provider_badge',
        'amount_display',
        'sender',
        'status_badge',
        'matched_invoice_link',
        'received_at',
    )
    list_filter = ('status', 'provider', 'merchant', 'received_at')
    search_fields = ('trx_id', 'sender', 'counterpart_number', 'raw_sms', 'merchant__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Parsed Transaction Data', {
            'fields': ('id', 'merchant', 'device', 'provider', 'sender', 'trx_id', 'amount', 'counterpart_number', 'status')
        }),
        ('Matching Details', {
            'fields': ('matched_invoice', 'received_at')
        }),
        ('Raw SMS Ingestion Payload', {
            'fields': ('raw_sms',)
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        })
    )
    actions = ['mark_unused_action', 'mark_ignored_action']

    def trx_id_badge(self, obj):
        return format_html(
            '<code style="background: #eff6ff; color: #1d4ed8; padding: 3px 6px; border: 1px solid #bfdbfe; border-radius: 4px; font-weight: 700; font-size: 12px;">{}</code>',
            obj.trx_id
        )
    trx_id_badge.short_description = 'TrxID'

    def merchant_link(self, obj):
        url = reverse('admin:gateway_merchant_change', args=[obj.merchant.pk])
        return format_html('<a href="{}" style="color: #0f172a; font-weight: 600;">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def provider_badge(self, obj):
        colors = {
            MFSProvider.BKASH: ('#e2136e', '#ffffff'),
            MFSProvider.NAGAD: ('#f7941d', '#ffffff'),
            MFSProvider.ROCKET: ('#8c3494', '#ffffff'),
            MFSProvider.CELLFIN: ('#00693e', '#ffffff'),
            MFSProvider.UPAY: ('#ffcd00', '#000000'),
            MFSProvider.OTHER: ('#475569', '#ffffff'),
        }
        bg, fg = colors.get(obj.provider, ('#475569', '#ffffff'))
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 10px;">{}</span>',
            bg, fg, obj.get_provider_display()
        )
    provider_badge.short_description = 'Provider'

    def amount_display(self, obj):
        return format_html('<span style="font-weight: 700; color: #047857;">{} BDT</span>', obj.amount)
    amount_display.short_description = 'Amount'

    def status_badge(self, obj):
        if obj.status == SMSTransactionStatus.MATCHED:
            return format_html(
                '<span style="background-color: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 12px; font-weight: 700; font-size: 11px;">MATCHED</span>'
            )
        elif obj.status == SMSTransactionStatus.UNUSED:
            return format_html(
                '<span style="background-color: #dbeafe; color: #1d4ed8; padding: 3px 8px; border-radius: 12px; font-weight: 700; font-size: 11px;">UNUSED</span>'
            )
        return format_html(
            '<span style="background-color: #f1f5f9; color: #64748b; padding: 3px 8px; border-radius: 12px; font-weight: 700; font-size: 11px;">IGNORED</span>'
        )
    status_badge.short_description = 'Status'

    def matched_invoice_link(self, obj):
        if obj.matched_invoice:
            url = reverse('admin:gateway_invoice_change', args=[obj.matched_invoice.pk])
            ref = str(obj.matched_invoice.reference_id)
            return format_html('<a href="{}" style="color: #2563eb; font-weight: 600;">Invoice {}...</a>', url, ref[:8])
        return format_html('<span style="color: #94a3b8;">None</span>')
    matched_invoice_link.short_description = 'Settled Invoice'

    @admin.action(description='Mark selected transactions as UNUSED')
    def mark_unused_action(self, request, queryset):
        queryset.update(status=SMSTransactionStatus.UNUSED, matched_invoice=None)
        self.message_user(request, "Selected SMS transactions marked as UNUSED.", messages.INFO)

    @admin.action(description='Mark selected transactions as IGNORED')
    def mark_ignored_action(self, request, queryset):
        queryset.update(status=SMSTransactionStatus.IGNORED)
        self.message_user(request, "Selected SMS transactions marked as IGNORED.", messages.WARNING)
