import uuid
import secrets
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_api_key():
    """Generates a secure 32-character hexadecimal API Key with prefix."""
    return f"mfs_live_{secrets.token_hex(16)}"


def generate_api_secret():
    """Generates a secure 48-character hexadecimal API Secret with prefix."""
    return f"mfs_sec_{secrets.token_hex(24)}"


def generate_device_token():
    """Generates a secure device token for Android SMS forwarder bridge."""
    return f"dev_{secrets.token_hex(20)}"


def default_invoice_expiration():
    """Default invoice expiration is set to 15 minutes from creation."""
    return timezone.now() + timedelta(minutes=15)


class MFSProvider(models.TextChoices):
    BKASH = 'BKASH', 'bKash'
    NAGAD = 'NAGAD', 'Nagad'
    ROCKET = 'ROCKET', 'Rocket'
    CELLFIN = 'CELLFIN', 'Cellfin'
    UPAY = 'UPAY', 'Upay'
    OTHER = 'OTHER', 'Other'


class AccountType(models.TextChoices):
    PERSONAL = 'PERSONAL', 'Personal'
    MERCHANT = 'MERCHANT', 'Merchant'
    AGENT = 'AGENT', 'Agent'


class InvoiceStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'
    EXPIRED = 'EXPIRED', 'Expired'
    CANCELLED = 'CANCELLED', 'Cancelled'


class SMSTransactionStatus(models.TextChoices):
    UNUSED = 'UNUSED', 'Unused'
    MATCHED = 'MATCHED', 'Matched'
    IGNORED = 'IGNORED', 'Ignored'


class Merchant(models.Model):
    """
    Independent tenant / project in the multi-tenant payment gateway platform.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Tenant UUID primary key"
    )
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='merchant_profile',
        help_text="Login account that owns this merchant workspace"
    )
    name = models.CharField(
        max_length=255,
        help_text="Merchant or business project name"
    )
    email = models.EmailField(
        blank=True,
        null=True,
        help_text="Primary merchant contact email"
    )
    api_key = models.CharField(
        max_length=64,
        unique=True,
        default=generate_api_key,
        db_index=True,
        help_text="Public API Key passed via X-API-KEY header"
    )
    api_secret = models.CharField(
        max_length=64,
        default=generate_api_secret,
        help_text="Private Secret Key used for HMAC webhook signing and signature verification"
    )
    webhook_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Target URL for automated IPN/webhook delivery on invoice completion"
    )
    return_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Default redirect URL after successful checkout"
    )
    cancel_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Default redirect URL on checkout cancellation"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this merchant account is enabled"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = 'Merchant'
        verbose_name_plural = 'Merchants'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['api_key', 'is_active'], name='merchant_key_active_idx'),
        ]

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return f"{self.name} ({self.api_key[:12]}...)"

    def regenerate_credentials(self, save=True):
        """Regenerate API Key and Secret."""
        self.api_key = generate_api_key()
        self.api_secret = generate_api_secret()
        if save:
            self.save(update_fields=['api_key', 'api_secret', 'updated_at'])


class PaymentMethod(models.Model):
    """
    Dynamic MFS payment numbers (bKash, Nagad, Rocket, Cellfin, etc.)
    configured per merchant tenant.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="UUID primary key"
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name='payment_methods',
        db_index=True
    )
    provider = models.CharField(
        max_length=20,
        choices=MFSProvider.choices,
        default=MFSProvider.BKASH,
        db_index=True,
        help_text="MFS Provider brand"
    )
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.PERSONAL,
        help_text="Account type: Personal (Send Money), Merchant (Make Payment), Agent (Cash Out)"
    )
    account_number = models.CharField(
        max_length=32,
        help_text="Receiving wallet/phone number (e.g. 017XXXXXXXX)"
    )
    instructions = models.TextField(
        blank=True,
        help_text="Custom step-by-step instructions shown to customers on checkout"
    )
    qr_code = models.ImageField(
        upload_to='qrcodes/%Y/%m/',
        blank=True,
        null=True,
        help_text="Optional QR code for fast payment scan"
    )
    charge_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Additional fee percentage charged to customer (if any)"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Sorting order in checkout page"
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = 'Payment Method'
        verbose_name_plural = 'Payment Methods'
        ordering = ['display_order', 'created_at']
        indexes = [
            models.Index(fields=['merchant', 'provider', 'is_active'], name='pm_merch_prov_active_idx'),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} ({self.account_number}) - {self.merchant.name}"


class Device(models.Model):
    """
    Android SMS/Notification forwarder device registered to forward incoming payment SMS
    to the gateway on behalf of a merchant.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="UUID primary key"
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name='devices',
        db_index=True
    )
    device_name = models.CharField(
        max_length=128,
        help_text="Human-readable device nickname (e.g., Primary Gateway Phone - SIM 1)"
    )
    device_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_device_token,
        db_index=True,
        help_text="Authentication token sent via X-DEVICE-TOKEN header"
    )
    model_name = models.CharField(
        max_length=128,
        blank=True,
        help_text="Hardware / Android OS device model"
    )
    sim_slot = models.CharField(
        max_length=32,
        blank=True,
        default='SIM 1',
        help_text="Designated SIM slot monitoring transactions"
    )
    battery_percentage = models.IntegerField(
        null=True,
        blank=True,
        help_text="Last reported battery percentage"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Last known IP address"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp of latest heartbeat / sync-sms call"
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = 'Device'
        verbose_name_plural = 'Devices'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', 'is_active'], name='device_merch_active_idx'),
        ]

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return f"{self.device_name} ({self.merchant.name})"

    def record_sync(self, battery=None, ip=None):
        """Update last sync timestamp and telemetry."""
        self.last_synced_at = timezone.now()
        if battery is not None:
            self.battery_percentage = battery
        if ip:
            self.ip_address = ip
        self.save(update_fields=['last_synced_at', 'battery_percentage', 'ip_address', 'updated_at'])


class Invoice(models.Model):
    """
    Dynamic transaction request initiated by external merchant projects.
    Carries a unique hosted checkout reference and enforces a 15-minute expiration window.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="UUID primary key"
    )
    reference_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="UUID reference key for hosted checkout URL (/checkout/<uuid>/)"
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name='invoices',
        db_index=True
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
        help_text="Selected payment method on checkout (if chosen)"
    )
    order_id = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text="External Order / Bill ID provided by the merchant"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Billable amount in currency units"
    )
    currency = models.CharField(
        max_length=10,
        default='BDT'
    )
    customer_name = models.CharField(
        max_length=128,
        blank=True
    )
    customer_email = models.EmailField(
        blank=True,
        null=True
    )
    customer_phone = models.CharField(
        max_length=32,
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.PENDING,
        db_index=True
    )
    trx_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Matched MFS Transaction ID submitted by user or verified from SMS"
    )
    sender_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="Customer paying MFS wallet number"
    )
    callback_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Invoice-specific override callback URL"
    )
    expires_at = models.DateTimeField(
        default=default_invoice_expiration,
        db_index=True,
        help_text="Expiration timestamp (default: 15 minutes after creation)"
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp when payment was successfully verified"
    )
    webhook_delivered = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether notification webhook was successfully received by merchant"
    )
    webhook_response_code = models.IntegerField(
        null=True,
        blank=True,
        help_text="HTTP status code returned from merchant webhook URL"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary JSON metadata passed during invoice initiation"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-created_at']
        indexes = [
            # Explicit composite index on (merchant, trx_id) as required
            models.Index(fields=['merchant', 'trx_id'], name='invoice_merch_trx_idx'),
            models.Index(fields=['merchant', 'status'], name='invoice_merch_status_idx'),
            models.Index(fields=['status', 'expires_at'], name='invoice_status_expires_idx'),
            models.Index(fields=['reference_id'], name='invoice_ref_id_idx'),
        ]

    def __str__(self):
        return f"Invoice {self.reference_id} - {self.amount} {self.currency} ({self.status})"

    @property
    def is_expired(self):
        """Returns True if pending invoice has exceeded expires_at."""
        if self.status == InvoiceStatus.PENDING and timezone.now() > self.expires_at:
            return True
        return self.status == InvoiceStatus.EXPIRED

    def check_expiration(self):
        """Checks and updates status to EXPIRED if past expiration window."""
        if self.status == InvoiceStatus.PENDING and timezone.now() > self.expires_at:
            self.status = InvoiceStatus.EXPIRED
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False


class SMSTransaction(models.Model):
    """
    Parsed SMS/Notification messages ingested from forwarder Android devices.
    Used for atomic matching against pending Invoices.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="UUID primary key"
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name='sms_transactions',
        db_index=True
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_transactions',
        help_text="Originating Android device forwarder"
    )
    provider = models.CharField(
        max_length=20,
        choices=MFSProvider.choices,
        default=MFSProvider.BKASH,
        db_index=True,
        help_text="Detected MFS provider"
    )
    sender = models.CharField(
        max_length=64,
        help_text="SMS sender header e.g. bKash, 16216, NAGAD"
    )
    trx_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Extracted Transaction ID (e.g. BL90XXYYZZ)"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        db_index=True,
        help_text="Amount credited according to SMS"
    )
    counterpart_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="Sending customer phone number (if extracted)"
    )
    raw_sms = models.TextField(
        help_text="Complete raw text of SMS/Notification"
    )
    status = models.CharField(
        max_length=20,
        choices=SMSTransactionStatus.choices,
        default=SMSTransactionStatus.UNUSED,
        db_index=True
    )
    matched_invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matched_transactions',
        help_text="Invoice matched and settled using this SMS"
    )
    received_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Timestamp of incoming message on device"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = 'SMS Transaction'
        verbose_name_plural = 'SMS Transactions'
        ordering = ['-received_at']
        indexes = [
            # Explicit composite index on (merchant, trx_id) as required
            models.Index(fields=['merchant', 'trx_id'], name='smstrx_merch_trx_idx'),
            models.Index(fields=['merchant', 'status'], name='smstrx_merch_status_idx'),
            models.Index(fields=['trx_id', 'amount'], name='smstrx_trx_amount_idx'),
        ]
        constraints = [
            # Prevent replay attacks: duplicate TrxID for the same merchant
            models.UniqueConstraint(
                fields=['merchant', 'trx_id'],
                condition=models.Q(trx_id__gt=''),
                name='unique_merchant_trx_id'
            )
        ]

    def __str__(self):
        return f"{self.trx_id} - {self.amount} BDT ({self.status}) [{self.merchant.name}]"
