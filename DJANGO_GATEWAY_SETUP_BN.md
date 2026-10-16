# Django project-এ Payment Gateway যুক্ত করার নির্দেশিকা

এই guide অনুসরণ করে Django website-এ hosted checkout যুক্ত করুন। উদাহরণগুলো `payment.webkoders.com`-এর gateway API অনুযায়ী লেখা। নিজের Django project-এর `Order` model ও field-এর নাম অনুযায়ী ছোটখাটো পরিবর্তন লাগতে পারে।

## Payment flow সংক্ষেপে

1. Customer আপনার website-এ order তৈরি করে **Pay** চাপবে।
2. আপনার Django backend API Key দিয়ে gateway-তে invoice তৈরি করবে।
3. Gateway থেকে আসা `checkout_url`-এ customer-কে পাঠাবেন।
4. Customer hosted checkout page-এ payment দেবেন। Gateway payment যাচাই করে webhook পাঠাবে।
5. আপনার webhook signature ও order details যাচাই করে local order paid করবে।

> Customer checkout page থেকে ফিরে এলেই order paid করবেন না। Payment নিশ্চিত করতে signed webhook যাচাই করুন।

## যা আগে লাগবে

- HTTPS চালু থাকা Django website এবং বাইরে থেকে খোলা যায় এমন domain।
- Gateway-তে সক্রিয় merchant account।
- Merchant dashboard-এর **API Credentials** থেকে API Key ও API Secret।
- Merchant dashboard-এর **Payment Accounts** থেকে সক্রিয় bKash/Nagad/Rocket বা অন্য payment number।
- আপনার Django project-এ থাকা Order model; order amount অবশ্যই server-side থেকে নেবেন।

Gateway-তে আপনার webhook ও return URL সেট করতে Super Admin-কে দিন:

- Webhook: `https://your-site.com/payments/gateway-webhook/`
- Return page: `https://your-site.com/payments/return/`

Gateway-র merchant settings-এ Webhook URL ও Return URL আলাদাভাবে সেট করান। Checkout create request-এ `callback_url` আপাতত পাঠাবেন না: gateway-তে এই field webhook target এবং customer return destination—দুই কাজেই ব্যবহৃত হয়। আলাদা webhook ও return URL দরকার হলে merchant settings ব্যবহার করুন।

## ধাপ ১: `requests` ইনস্টল করুন

```bash
pip install requests
```

## ধাপ ২: API secret-গুলো environment-এ রাখুন

Project root-এ `.env` (বা hosting provider-এর environment settings) ব্যবহার করুন:

```env
GATEWAY_BASE_URL=https://payment.webkoders.com
GATEWAY_API_KEY=dashboard-theke-pawa-api-key
GATEWAY_API_SECRET=dashboard-theke-pawa-api-secret
```

`.env` GitHub-এ push করবেন না। `.gitignore`-এ `.env` আছে কি না দেখুন। Django `settings.py`-এ environment value পড়ুন; `python-decouple` ব্যবহার করলে:

```bash
pip install python-decouple
```

```python
# settings.py
from decouple import config

GATEWAY_BASE_URL = config(
    "GATEWAY_BASE_URL", default="https://payment.webkoders.com"
).rstrip("/")
GATEWAY_API_KEY = config("GATEWAY_API_KEY")
GATEWAY_API_SECRET = config("GATEWAY_API_SECRET")
```

Hosting environment variable ব্যবহার করলে সেই অনুযায়ী `os.environ` থেকে পড়তে পারেন। API Key/Secret কখনো HTML, JavaScript, mobile app বা browser request-এ রাখবেন না।

## ধাপ ৩: Checkout তৈরির service লিখুন

`payments/services.py` (অথবা project-এর service module)-এ:

```python
import requests
from django.conf import settings


class GatewayError(Exception):
    pass


def create_gateway_checkout(order):
    # Amount এবং customer details নিজের database-এর Order থেকে নিন,
    # browser থেকে পাঠানো amount বিশ্বাস করবেন না।
    payload = {
        "order_id": str(order.pk),
        "amount": f"{order.amount:.2f}",
        "currency": "BDT",
        "customer_name": order.customer_name or "",
        "customer_email": order.customer_email or None,
        "customer_phone": order.customer_phone or "",
        "metadata": {"local_order_id": str(order.pk)},
    }

    try:
        response = requests.post(
            f"{settings.GATEWAY_BASE_URL}/api/v1/checkout/create/",
            headers={"X-API-KEY": settings.GATEWAY_API_KEY},
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GatewayError("Gateway-তে checkout তৈরি করা যায়নি।") from exc

    if result.get("status") != "success" or not result.get("checkout_url"):
        raise GatewayError("Gateway বৈধ checkout link দেয়নি।")

    return result
```

`order.customer_name`, `customer_email`, `customer_phone` আপনার model-এ না থাকলে সেগুলো বাদ দিন বা সঠিক field name বসান। Gateway-তে `amount` কমপক্ষে `1.00` হতে হবে। `order_id` আপনার website-এর order-কে gateway invoice-এর সঙ্গে মিলিয়ে রাখে।

Request endpoint:

```text
POST https://payment.webkoders.com/api/v1/checkout/create/
Header: X-API-KEY: <আপনার API Key>
```

Success response-এ `checkout_url`, `reference_id`, `invoice_id`, `invoice_status`, `amount` ও `expires_at` থাকে। Checkout সাধারণত ১৫ মিনিটে expire হয়।

## ধাপ ৪: Pay button-এর Django view যোগ করুন

নিচের উদাহরণে `Order`, `user`, `payment_status`, `gateway_reference` নিজের project-এর সঙ্গে মিলিয়ে নিন। Customer-এর order ownership অবশ্যই যাচাই করুন:

```python
# payments/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from shop.models import Order
from .services import GatewayError, create_gateway_checkout


@login_required
@require_POST
def start_payment(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    if order.payment_status == "PAID":
        return redirect("order-detail", order_id=order.pk)

    try:
        invoice = create_gateway_checkout(order)
    except GatewayError as exc:
        messages.error(request, str(exc))
        return redirect("order-detail", order_id=order.pk)

    # আপনার Order-এ এই field না থাকলে যোগ করুন, অথবা নিজের field ব্যবহার করুন।
    order.gateway_reference = invoice["reference_id"]
    order.payment_status = "PENDING"
    order.save(update_fields=["gateway_reference", "payment_status"])

    return redirect(invoice["checkout_url"])
```

`urls.py`-এ route দিন:

```python
from django.urls import path
from payments import views

urlpatterns = [
    path("orders/<int:order_id>/pay/", views.start_payment, name="start-payment"),
]
```

HTML form-এ CSRF token রাখুন:

```html
<form method="post" action="{% url 'start-payment' order.id %}">
  {% csrf_token %}
  <button type="submit">Pay now</button>
</form>
```

## ধাপ ৫: Signed webhook endpoint বানান

Gateway payment সফল হলে merchant-এর configured Webhook URL-এ JSON `POST` পাঠায়। Payload-এর signature হলো API Secret দিয়ে raw JSON body-র HMAC-SHA256। Header-এর নাম `X-Signature` (একই signature `X-Signature-SHA256`-এও থাকে)।

`payments/views.py`-এ:

```python
import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from shop.models import Order


@csrf_exempt  # CSRF-এর বদলে নিচের HMAC signature যাচাই করে endpoint সুরক্ষিত হয়
@require_POST
def gateway_webhook(request):
    received_signature = (
        request.headers.get("X-Signature")
        or request.headers.get("X-Signature-SHA256", "")
    )
    expected_signature = hmac.new(
        settings.GATEWAY_API_SECRET.encode("utf-8"),
        request.body,  # JSON parse/re-encode না করে মূল body-টাই sign যাচাইয়ে দিন
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, received_signature):
        return HttpResponse("Invalid signature", status=400)

    try:
        event = json.loads(request.body)
        if event.get("event") != "payment.completed":
            return HttpResponse("Ignored", status=200)
        if event.get("status") != "COMPLETED":
            return HttpResponse("Payment is not completed", status=400)

        # Gateway order_id আপনার local Order.pk হিসেবে পাঠানো হয়েছিল।
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=event["order_id"])

            # Local reference এবং amount মেলান—এগুলো না মিললে paid করবেন না।
            if str(order.gateway_reference) != str(event["reference_id"]):
                return HttpResponse("Invoice mismatch", status=400)
            if Decimal(str(order.amount)) != Decimal(str(event["amount"])):
                return HttpResponse("Amount mismatch", status=400)
            if event.get("currency") != "BDT":
                return HttpResponse("Currency mismatch", status=400)

            # Webhook একাধিকবার আসতে পারে; update idempotent রাখুন।
            if order.payment_status != "PAID":
                order.payment_status = "PAID"
                order.gateway_trx_id = event.get("trx_id", "")
                order.save(update_fields=["payment_status", "gateway_trx_id"])

    except (KeyError, ValueError, TypeError, InvalidOperation, Order.DoesNotExist):
        return HttpResponse("Invalid payment notification", status=400)

    # 2xx দিলে gateway webhook delivery সফল হিসেবে সংরক্ষণ করে।
    return HttpResponse("OK", status=200)
```

আপনার `Order` model-এ উদাহরণস্বরূপ নিচের field লাগতে পারে (আগে থেকে থাকলে আবার যোগ করবেন না):

```python
gateway_reference = models.CharField(max_length=36, blank=True, db_index=True)
gateway_trx_id = models.CharField(max_length=64, blank=True)
# payment_status field-এ অন্তত PENDING এবং PAID রাখুন।
```

URL route:

```python
path(
    "payments/gateway-webhook/",
    views.gateway_webhook,
    name="gateway-webhook",
),
```

Order model বদলালে migration চালান:

```bash
python manage.py makemigrations
python manage.py migrate
```

> Webhook-এ `@csrf_exempt` শুধু এই নির্দিষ্ট route-এ ব্যবহার করুন। Signature, reference, amount এবং currency যাচাই ছাড়া paid status দেবেন না।

## ধাপ ৬: Customer return page

Gateway-র Return URL customer-কে checkout শেষে আপনার site-এ ফেরায়। এই page-এ local order-এর বর্তমান status দেখান। Return URL-এ আসা মানেই payment সফল—এমন ধরে নেবেন না; webhook আসা পর্যন্ত `PENDING` দেখান। Webhook দেরি হলে আপনার backend `GET /api/v1/checkout/<reference_id>/` দিয়ে invoice status পুনরায় মিলিয়ে নিতে পারে। এই status endpoint-এ API Key লাগে না, তাই কেবল নিজের database-এ সংরক্ষিত reference ID দিয়ে যাচাই করুন।

## ধাপ ৭: Payment number ও checkout চালু করুন

1. Merchant dashboard-এর **Payment Accounts** মেনুতে bKash/Rocket/Nagad number যোগ করে Active করুন।
2. Super Admin-কে webhook ও return URL merchant settings-এ configure করতে বলুন।
3. Merchant dashboard থেকে API Key ও API Secret নিয়ে server environment-এ বসান।
4. নিজের site থেকে ছোট amount-এর order তৈরি করে Pay button চাপুন।
5. Customer hosted checkout-এ গিয়ে নির্বাচিত নম্বরে টাকা পাঠিয়ে সঠিক Transaction ID দিন।
6. SMS Forwarder-সহ payment verification চালু থাকলে gateway invoice complete করে webhook পাঠাবে। আপনার server `2xx` দিলে order paid হবে।

## সাধারণ সমস্যা

| সমস্যা | কী দেখবেন |
| --- | --- |
| `401` / `403` checkout create-এ | API Key ঠিক আছে কি না, সঠিক merchant-এর Key কি না। |
| `400` response | `amount` অন্তত `1.00`, decimal-এর পরে সর্বোচ্চ ২ ঘর, এবং `order_id` সর্বোচ্চ ১২৮ অক্ষর কি না। |
| Checkout-এ payment number নেই | Merchant dashboard-এ payment account যোগ করা ও Active করা হয়েছে কি না। |
| Webhook আসছে না | URL public HTTPS কি না, Super Admin সেট করেছেন কি না, server log এবং gateway-তে webhook delivery status দেখুন। |
| Signature মেলে না | JSON-কে re-encode করবেন না; `request.body`-র raw bytes-এ HMAC করুন এবং সঠিক API Secret ব্যবহার করুন। |
| Customer ফিরেছে কিন্তু order Pending | Return page-কে paid confirmation ভাববেন না; webhook বা invoice status যাচাই করুন। |

## গুরুত্বপূর্ণ নিরাপত্তা নিয়ম

- API Key/Secret শুধু Django server-এ রাখুন; browser/mobile app-এ নয়।
- Amount browser input থেকে নেবেন না; নিজের database-এর order থেকে নিন।
- প্রতিটি webhook-এ HMAC, local order, reference, amount এবং currency যাচাই করুন।
- Webhook idempotent রাখুন, কারণ delivery পুনরায় হতে পারে।
- Test করার সময় real payment ও SMS verification flow মনে রাখুন; gateway checkout link তৈরি হওয়াই payment complete হওয়া নয়।
