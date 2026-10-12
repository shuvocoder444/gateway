# Product Specification: Multi-Tenant MFS Payment Gateway (Django + PWA)

## 1. Overview

A self-hosted, scalable, multi-tenant payment gateway aggregator platform (similar to UddoktaPay/PayStation) built with Django, Django REST Framework, and Tailwind CSS. It supports unlimited merchants/projects, custom MFS payment numbers (bKash, Nagad, Rocket, Cellfin), an automated Android SMS/Notification listener bridge, hosted dynamic checkout, and an installable PWA dashboard.

## 2. Core Entities & Multi-Tenancy

- **Merchant**: Independent tenant with unique API Key, API Secret, webhook URL, and return URL. Unlimited merchants supported.
- **PaymentMethod**: Dynamic methods (bKash, Nagad, Rocket, Cellfin) assigned per merchant with custom numbers and instructions.
- **Device**: Android SMS forwarder device tokens mapped per merchant.
- **Invoice**: Dynamic transaction request per merchant with 15-minute expiration, amount, and status (PENDING, COMPLETED, EXPIRED).
- **SMSTransaction**: Parsed messages synced from Android app (sender, trx_id, amount, status: UNUSED / MATCHED).

## 3. Key Flows

1. **Initiate Payment**: External project posts order details to `/api/v1/checkout/create/` with `X-API-KEY`. Returns unique hosted checkout URL (`/checkout/<uuid>/`).
2. **Checkout UI**: Dynamic page rendering merchant-specific MFS accounts, countdown timer, copyable numbers, and TrxID verification field.
3. **SMS Ingestion**: Android app posts received payment SMS/notification to `/api/v1/device/sync-sms/` with `X-DEVICE-TOKEN`.
4. **Verification & Webhook**: When customer submits TrxID, backend atomically matches `trx_id`, `amount`, and `merchant_id`. If valid, marks invoice COMPLETED, transaction MATCHED, and triggers an HMAC-signed background webhook to merchant's server.

## 4. Frontend & PWA

- Responsive checkout built with Tailwind CSS.
- Installable PWA dashboard with `manifest.json` and service worker caching for managing merchants, numbers, and live transaction logs.
