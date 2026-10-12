import hmac
import hashlib
import json
import logging
import threading
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
import requests
from rest_framework import exceptions

from .models import (
    Invoice,
    SMSTransaction,
    InvoiceStatus,
    SMSTransactionStatus
)

logger = logging.getLogger(__name__)


def generate_hmac_signature(payload_str: str, secret_key: str) -> str:
    """Generate SHA256 HMAC hexadecimal signature for webhook payload."""
    return hmac.new(
        secret_key.encode('utf-8'),
        payload_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def send_webhook_http(invoice_id: str):
    """
    HTTP POST webhook notification to merchant's webhook_url or invoice.callback_url.
    Carries HMAC-SHA256 signature in X-Signature header.
    """
    try:
        invoice = Invoice.objects.select_related('merchant').get(id=invoice_id)
        target_url = invoice.callback_url or invoice.merchant.webhook_url
        if not target_url:
            logger.info("No webhook URL configured for merchant %s (invoice %s)", invoice.merchant.name, invoice.id)
            return

        payload = {
            "event": "payment.completed",
            "invoice_id": str(invoice.id),
            "reference_id": str(invoice.reference_id),
            "order_id": invoice.order_id,
            "amount": str(invoice.amount),
            "currency": invoice.currency,
            "trx_id": invoice.trx_id,
            "sender_number": invoice.sender_number,
            "status": invoice.status,
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            "customer_phone": invoice.customer_phone,
            "customer_email": invoice.customer_email,
            "metadata": invoice.metadata,
            "timestamp": timezone.now().isoformat()
        }

        payload_json = json.dumps(payload, separators=(',', ':'))
        signature = generate_hmac_signature(payload_json, invoice.merchant.api_secret)

        headers = {
            'Content-Type': 'application/json',
            'X-Signature': signature,
            'X-Signature-SHA256': signature,
            'X-Timestamp': timezone.now().isoformat(),
            'User-Agent': 'MFS-Gateway-Webhook/1.0',
        }

        response = requests.post(
            target_url,
            data=payload_json,
            headers=headers,
            timeout=10
        )

        invoice.webhook_delivered = (200 <= response.status_code < 300)
        invoice.webhook_response_code = response.status_code
        invoice.save(update_fields=['webhook_delivered', 'webhook_response_code', 'updated_at'])
        logger.info(
            "Webhook delivered for invoice %s to %s with status %s",
            invoice.id, target_url, response.status_code
        )

    except Exception as exc:
        logger.error("Failed to deliver webhook for invoice %s: %s", invoice_id, exc)
        try:
            Invoice.objects.filter(id=invoice_id).update(
                webhook_delivered=False,
                webhook_response_code=500
            )
        except Exception:
            pass


def dispatch_merchant_webhook(invoice: Invoice, background: bool = None):
    """
    Trigger webhook delivery for a completed invoice.
    Can be run in background daemon thread or synchronously.
    """
    import sys
    if background is None:
        background = 'test' not in sys.argv

    if background:
        thread = threading.Thread(target=send_webhook_http, args=(str(invoice.id),), daemon=True)
        thread.start()
    else:
        send_webhook_http(str(invoice.id))


def verify_and_settle_invoice(reference_id, trx_id: str, sender_number: str = None) -> Invoice:
    """
    Atomically verify and settle an invoice using database-level pessimistic locking (select_for_update).
    Prevents double spending and race conditions.
    """
    normalized_trx_id = trx_id.strip().upper()

    # 1. Fetch invoice and check expiration state
    try:
        invoice = Invoice.objects.select_related('merchant', 'payment_method').get(
            reference_id=reference_id
        )
    except Invoice.DoesNotExist:
        raise exceptions.NotFound({"detail": "Invoice not found."})

    # Check expiration and persist status before transaction block
    if invoice.check_expiration() or invoice.status == InvoiceStatus.EXPIRED:
        raise exceptions.ValidationError({
            "detail": "Invoice has expired. Please initiate a new payment request.",
            "status": InvoiceStatus.EXPIRED
        })

    if invoice.status == InvoiceStatus.COMPLETED:
        raise exceptions.ValidationError({
            "detail": "Invoice has already been completed.",
            "status": invoice.status,
            "trx_id": invoice.trx_id
        })

    if invoice.status == InvoiceStatus.CANCELLED:
        raise exceptions.ValidationError({
            "detail": "Invoice has been cancelled.",
            "status": InvoiceStatus.CANCELLED
        })

    with transaction.atomic():
        # 2. Pessimistically lock invoice
        invoice = Invoice.objects.select_for_update().select_related('merchant', 'payment_method').get(
            reference_id=reference_id
        )

        # Re-check inside pessimistic lock
        if invoice.status == InvoiceStatus.COMPLETED:
            raise exceptions.ValidationError({
                "detail": "Invoice has already been completed.",
                "status": invoice.status,
                "trx_id": invoice.trx_id
            })

        if invoice.check_expiration() or invoice.status == InvoiceStatus.EXPIRED:
            raise exceptions.ValidationError({
                "detail": "Invoice has expired. Please initiate a new payment request.",
                "status": InvoiceStatus.EXPIRED
            })

        if invoice.status == InvoiceStatus.CANCELLED:
            raise exceptions.ValidationError({
                "detail": "Invoice has been cancelled.",
                "status": InvoiceStatus.CANCELLED
            })

        # 4. Pessimistically lock matching unused SMS transaction for this merchant
        sms_qs = SMSTransaction.objects.select_for_update().filter(
            merchant=invoice.merchant,
            trx_id=normalized_trx_id,
            status=SMSTransactionStatus.UNUSED
        )

        sms = sms_qs.first()

        if not sms:
            # Check if this trx_id was already matched to another invoice (double-spend attempt)
            already_used = SMSTransaction.objects.filter(
                merchant=invoice.merchant,
                trx_id=normalized_trx_id,
                status=SMSTransactionStatus.MATCHED
            ).exists()
            if already_used:
                raise exceptions.ValidationError({
                    "detail": f"Transaction ID '{normalized_trx_id}' has already been matched and redeemed.",
                    "code": "TRX_ALREADY_USED"
                })

            raise exceptions.ValidationError({
                "detail": f"Transaction ID '{normalized_trx_id}' not found for this merchant. Please ensure payment is completed and TrxID is correct.",
                "code": "TRX_NOT_FOUND"
            })

        # 5. Verify transaction amount matches invoice amount
        if Decimal(str(sms.amount)) != Decimal(str(invoice.amount)):
            raise exceptions.ValidationError({
                "detail": f"Amount mismatch. Invoice requires {invoice.amount} {invoice.currency}, but SMS transaction shows {sms.amount} {invoice.currency}.",
                "code": "AMOUNT_MISMATCH",
                "invoice_amount": str(invoice.amount),
                "received_amount": str(sms.amount)
            })

        # 6. Atomically update SMSTransaction and Invoice
        now = timezone.now()
        sms.status = SMSTransactionStatus.MATCHED
        sms.matched_invoice = invoice
        sms.save(update_fields=['status', 'matched_invoice', 'updated_at'])

        invoice.status = InvoiceStatus.COMPLETED
        invoice.trx_id = normalized_trx_id
        invoice.paid_at = now
        if sender_number:
            invoice.sender_number = sender_number
        elif sms.counterpart_number:
            invoice.sender_number = sms.counterpart_number
        invoice.save(update_fields=['status', 'trx_id', 'paid_at', 'sender_number', 'updated_at'])

    # 7. Dispatch webhook outside the lock / atomic block
    dispatch_merchant_webhook(invoice)

    return invoice
