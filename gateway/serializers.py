import re
from decimal import Decimal
from rest_framework import serializers
from django.urls import reverse
from .models import (
    Merchant,
    PaymentMethod,
    Device,
    Invoice,
    SMSTransaction,
    MFSProvider,
    InvoiceStatus,
    SMSTransactionStatus
)


class PaymentMethodPublicSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source='get_provider_display', read_only=True)
    account_type_name = serializers.CharField(source='get_account_type_display', read_only=True)
    qr_code = serializers.SerializerMethodField()

    def get_qr_code(self, obj):
        if not obj.qr_code:
            return None
        path = reverse('payment-method-qr', args=[obj.id])
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path

    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'provider',
            'provider_name',
            'account_type',
            'account_type_name',
            'account_number',
            'instructions',
            'qr_code',
            'charge_percentage',
            'display_order'
        ]


class CheckoutCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('1.00'))
    currency = serializers.CharField(max_length=10, default='BDT', required=False)
    order_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')
    customer_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')
    customer_email = serializers.EmailField(required=False, allow_null=True, default=None)
    customer_phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    callback_url = serializers.URLField(max_length=500, required=False, allow_null=True, default=None)
    payment_method_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    metadata = serializers.DictField(required=False, default=dict)

    def validate_payment_method_id(self, value):
        if value:
            merchant = self.context.get('merchant')
            if not PaymentMethod.objects.filter(id=value, merchant=merchant, is_active=True).exists():
                raise serializers.ValidationError("Invalid or inactive payment method for this merchant.")
        return value


class CheckoutDetailSerializer(serializers.ModelSerializer):
    merchant_name = serializers.CharField(source='merchant.name', read_only=True)
    checkout_url = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)
    available_payment_methods = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id',
            'reference_id',
            'checkout_url',
            'merchant_name',
            'order_id',
            'amount',
            'currency',
            'customer_name',
            'customer_email',
            'customer_phone',
            'status',
            'trx_id',
            'expires_at',
            'paid_at',
            'is_expired',
            'created_at',
            'metadata',
            'available_payment_methods'
        ]

    def get_checkout_url(self, obj):
        request = self.context.get('request')
        url = f"/checkout/{obj.reference_id}/"
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_available_payment_methods(self, obj):
        methods = obj.merchant.payment_methods.filter(is_active=True).order_by('display_order', 'created_at')
        return PaymentMethodPublicSerializer(methods, many=True, context=self.context).data


class SMSSyncItemSerializer(serializers.Serializer):
    sender = serializers.CharField(max_length=64)
    trx_id = serializers.CharField(max_length=64)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    counterpart_number = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    raw_sms = serializers.CharField(required=False, allow_blank=True, default='')
    provider = serializers.ChoiceField(choices=MFSProvider.choices, required=False, default=MFSProvider.BKASH)
    received_at = serializers.DateTimeField(required=False)

    def validate_trx_id(self, value):
        val = value.strip().upper()
        if not val:
            raise serializers.ValidationError("Transaction ID cannot be blank.")
        return val


class SMSSyncPayloadSerializer(serializers.Serializer):
    battery_percentage = serializers.IntegerField(required=False, min_value=0, max_value=100)
    messages = SMSSyncItemSerializer(many=True, required=False)

    # Also support single message flat fields if sent directly
    sender = serializers.CharField(max_length=64, required=False)
    trx_id = serializers.CharField(max_length=64, required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    counterpart_number = serializers.CharField(max_length=32, required=False, allow_blank=True)
    raw_sms = serializers.CharField(required=False, allow_blank=True)
    provider = serializers.ChoiceField(choices=MFSProvider.choices, required=False)
    received_at = serializers.DateTimeField(required=False)


class CheckoutVerifySerializer(serializers.Serializer):
    trx_id = serializers.CharField(max_length=64, required=True)
    sender_number = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')

    def validate_trx_id(self, value):
        clean = value.strip().upper()
        if not clean:
            raise serializers.ValidationError("Transaction ID is required.")
        return clean
