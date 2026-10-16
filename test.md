Django-তে integration আপনার server-side থেকে হবে। Merchant dashboard থেকে API Key ও API Secret নিন; দুটোই .env-এ রাখুন, frontend-এ নয়।
GATEWAY_BASE_URL=https://payment.webkoders.com
GATEWAY_API_KEY=আপনার_API_KEY
GATEWAY_API_SECRET=আপনার_API_SECRET
আপনার Django order তৈরি হওয়ার পর gateway-তে checkout request পাঠান:
# services.py
import requests
from django.conf import settings

def create_gateway_checkout(order):
    payload = {
        "amount": str(order.amount),
        "currency": "BDT",
        "order_id": str(order.id),
        "customer_name": order.customer_name,
        "customer_email": order.customer_email or None,
        "customer_phone": order.customer_phone,
        "callback_url": "https://আপনার-সাইট.com/payments/webhook/",
        "metadata": {"local_order_id": str(order.id)},
    }

    response = requests.post(
        f"{settings.GATEWAY_BASE_URL}/api/v1/checkout/create/",
        headers={"X-API-KEY": settings.GATEWAY_API_KEY},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["checkout_url"]
তারপর customer-কে পাওয়া checkout_url-এ redirect করবেন। Gateway payment status verify করে ওই callback_url-এ payment.completed webhook পাঠায়। Webhook-এর X-Signature যাচাই না করে order paid করবেন না:
# views.py
import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

@csrf_exempt
@require_POST
def payment_webhook(request):
    expected = hmac.new(
        settings.GATEWAY_API_SECRET.encode(),
        request.body,  # Gateway-এর পাঠানো আসল JSON bytes
        hashlib.sha256,
    ).hexdigest()

    received = request.headers.get("X-Signature", "")
    if not hmac.compare_digest(expected, received):
        return HttpResponse(status=400)

    event = json.loads(request.body)
    if event.get("event") != "payment.completed":
        return HttpResponse(status=200)

    # এখানে আপনার Order খুঁজুন:
    # order = Order.objects.get(id=event["order_id"])
    # amount/currency মিলিয়ে দেখুন, আগে paid হয়েছে কি না যাচাই করুন,
    # তারপর paid mark করুন. Webhook একাধিকবার আসতে পারে।

    return HttpResponse(status=200)
Order-এর model field আপনার project অনুযায়ী বসাবেন। Return URL customer-কে ফেরানোর জন্য; শুধু ওই page-এ ফেরত এলেই payment সফল ধরে নেবেন না—webhook-এর signature, order ID ও amount যাচাই করে paid করবেন। Gateway-এর checkout endpoint POST /api/v1/checkout/create/, আর header-এর নাম X-API-KEY।