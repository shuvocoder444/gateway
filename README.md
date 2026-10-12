# 🚀 MFS Multi-Tenant Automated Payment Gateway

> একটি সম্পূর্ণ স্বয়ংক্রিয়, নিরাপদ ও স্কেলেবল মাল্টি-টেন্যান্ট মোবাইল ফিন্যান্সিয়াল সার্ভিস (MFS) পেমেন্ট গেটওয়ে প্ল্যাটফর্ম (যেমন: UddoktaPay, Shurjopay-এর মতো নিজস্ব সেলফ-হোস্টেড বিকল্প)। এটি **bKash, Nagad, Rocket, Cellfin, Upay** ইত্যাদি অ্যাকাউন্টের মাধ্যমে অটোমেটিক টাকা গ্রহণ, অ্যান্ড্রয়েড ডিভাইস থেকে ইনস্ট্যান্ট SMS সিঙ্ক এবং ডাবল-স্পেন্ডিং রোধ করে স্বয়ংক্রিয় অর্ডার ভেরিফিকেশন সম্পন্ন করে।

---

## 📑 সূচিপত্র (Table of Contents)
1. [সফটওয়্যার পরিচিতি ও ফিচার](#-সফটওয়্যার-পরিচিতি-ও-ফিচার)
2. [সিস্টেমের কাজের ধাপ (How it Works)](#-সিস্টেমের-কাজের-ধাপ-how-it-works)
3. [ড্যাশবোর্ডসমূহ ও অ্যাক্সেস লিঙ্ক](#-ড্যাশবোর্ডসমূহ-ও-অ্যাক্সেস-লিঙ্ক)
4. [সফটওয়্যার পরিচালনা করার নির্দেশিকা (Step-by-Step Operation Guide)](#-সফটওয়্যার-পরিচালনা-করার-নির্দেশিকা)
5. [অ্যান্ড্রয়েড SMS ফরওয়ার্ডার সেটআপ (Android Bridge Setup)](#-অ্যান্ড্রয়েড-sms-ফরওয়ার্ডার-সেটআপ)
6. [API ইন্টিগ্রেশন গাইড (Merchant Integration)](#-api-ইন্টিগ্রেশন-গাইড)
7. [লোকাল সার্ভার রান ও ডিপ্লয়মেন্ট](#-লোকাল-সার্ভার-রান-ও-ডিপ্লয়মেন্ট)
8. [অটোমেটেড টেস্টিং](#-অটোমেটেড-টেস্টিং)

---

## 🌟 সফটওয়্যার পরিচিতি ও ফিচার

* **মাল্টি-টেন্যান্ট মার্চেন্ট সিস্টেম:** আনলিমিটেড মার্চেন্ট বা প্রজেক্ট যোগ করা যায়। প্রতিটি মার্চেন্টের নিজস্ব ইউনিক API Key, API Secret, এবং আলাদা Webhook URL থাকে।
* **ডাইনামিক পেমেন্ট মেথড:** প্রতিটি মার্চেন্ট তাদের নিজস্ব বিকাশ, নগদ, রকেট বা সেলফিন নম্বর (Personal/Agent/Merchant) যুক্ত করতে পারে।
* **অ্যান্ড্রয়েড SMS অটো-লিসেনার ব্রিজ:** গ্রাহক টাকা পাঠালে অ্যান্ড্রয়েড ফোনে আসা SMS সাথে সাথে এপিআই-এর মাধ্যমে গেটওয়েতে চলে আসে।
* **ডাবল-স্পেন্ডিং প্রটেকশন (Pessimistic Locking):** একই TrxID দিয়ে দুইবার পেমেন্ট করা বা একাধিক ট্যাবে একসাথে ভেরিফাই করার কোনো সুযোগ নেই। ডাটাবেজ লেভেলে `select_for_update()` লক কাজ করে।
* **হোস্টেড ডায়নামিক চেকআউট:** আধুনিক রেসপনসিভ UI, ১৫ মিনিটের কাউন্টডাউন টাইমার, ১-ক্লিকে নম্বর কপি এবং লাইভ AJAX TrxID ভেরিফিকেশন।
* **প্রফেশনাল অ্যাডমিন ড্যাশবোর্ড:** সাইডবার মেনু, Chart.js লাইভ চার্ট, ভলিউম মেট্রিক্স, ইনভয়েস হিস্ট্রি ও বিল্ট-ইন টেস্ট স্যান্ডবক্স।
* **ইনস্টলেবল PWA মার্চেন্ট ড্যাশবোর্ড:** মোবাইল ও পিসিতে সরাসরি অ্যাপ হিসেবে ইনস্টলযোগ্য (Offline Service Worker সাপোর্টেড)।

---

## 🔄 সিস্টেমের কাজের ধাপ (How it Works)

```
[ মার্চেন্ট ওয়েবসাইট / ই-কমার্স ]
       │  (1) POST /api/v1/checkout/create/ (with X-API-KEY)
       ▼
[ গেটওয়ে সার্ভার ] ──► ইনভয়েস তৈরি ও Hosted Checkout URL রিটার্ন
       │
       ▼
[ কাস্টমার চেকআউট পেজ (/checkout/<uuid>/) ]
       │  (2) কাস্টমার প্রদর্শিত MFS নম্বরে টাকা পাঠায়
       ▼
[ মার্চেন্টের বিকাশ/নগদ সিম থাকা অ্যান্ড্রয়েড ফোন ]
       │  (3) SMS আসে: "Tk 500 received... TrxID 9K201..."
       │  (4) SMS Forwarder অ্যাপ ব্যাকগ্রাউন্ডে পুশ করে -> /api/v1/device/sync-sms/
       ▼
[ গেটওয়ে সার্ভার ডাটাবেজ ] ──► TrxID ও Amount সেভ হয় (UNUSED)
       ▲
       │  (5) কাস্টমার চেকআউট পেজে TrxID লিখে "Verify Payment" চাপলে
       ▼
[ গেটওয়ে ভেরিফিকেশন ইঞ্জিন ] ──► পার্সড SMS-এর সাথে ম্যাচিং ও ডাবল স্পেন্ডিং চেক
       │  (6) ম্যাচ হলে ইনভয়েস -> PAID, ট্রানজ্যাকশন -> MATCHED
       ▼
[ মার্চেন্ট Webhook URL ] ──► HMAC-SHA256 সাইনড ইনস্ট্যান্ট নোটিফিকেশন ডেলিভারি
```

---

## 🔗 ড্যাশবোর্ডসমূহ ও অ্যাক্সেস লিঙ্ক

সার্ভার চালু থাকা অবস্থায় ব্রাউজারে নিচের লিঙ্কগুলো ব্যবহার করুন:

| ড্যাশবোর্ড / পেজ | URL | ইউজার / বিবরণ |
| :--- | :--- | :--- |
| 🛡️ **Master Admin Control Center** | `http://127.0.0.1:8000/admin-dashboard/` | সম্পূর্ণ গেটওয়ের অ্যাডমিন কন্ট্রোল ও সাইডবার নেভিগেশন |
| 💼 **Merchant PWA Dashboard** | `http://127.0.0.1:8000/dashboard/` | মার্চেন্ট লেভেল ইনভয়েস, ট্রানজ্যাকশন ও PWA ইনস্টলেশন |
| ⚙️ **Django Core Superadmin** | `http://127.0.0.1:8000/admin/` | ইউজারনেম: `admin` \| পাসওয়ার্ড: `admin123` |
| 💳 **Hosted Checkout ডেমো** | `http://127.0.0.1:8000/checkout/<invoice-uuid>/` | গ্রাহকদের জন্য তৈরি পেমেন্ট পেজ |

---

## 🛠️ সফটওয়্যার পরিচালনা করার নির্দেশিকা

### ধাপ ১: নতুন মার্চেন্ট তৈরি করা
1. ব্রাউজারে `http://127.0.0.1:8000/admin/` অথবা `http://127.0.0.1:8000/admin-dashboard/` এ যান।
2. **Merchants** মেনুতে ক্লিক করে নতুন মার্চেন্টের নাম, ইমেইল, Webhook URL এবং Return URL দিন।
3. সেভ করলে সিস্টেম স্বয়ংক্রিয়ভাবে একটি ইউনিক `api_key` এবং `api_secret` তৈরি করে দেবে।

### ধাপ ২: মার্চেন্টের পেমেন্ট মেথড (bKash/Nagad/Rocket) যুক্ত করা
1. **Payment Methods** সেকশনে যান।
2. মার্চেন্ট নির্বাচন করুন এবং প্রোভাইডার সিলেক্ট করুন (যেমন: `BKASH`, `NAGAD`, `ROCKET`, `CELLFIN`)।
3. একাউন্ট নাম্বার (যেমন: `01700000000`), টাইপ (`PERSONAL`/`MERCHANT`/`AGENT`) এবং নির্দেশিকা লিখে সক্রিয় (Active) করুন।

### ধাপ ৩: অ্যান্ড্রয়েড ডিভাইস ব্রিজ যুক্ত করা
1. **Devices** সেকশনে যান।
2. আপনার ফোনের নাম (যেমন: `Samsung Galaxy MFS Bridge 1`) এবং সিমের ফোন নম্বর দিন।
3. সিস্টেম একটি সিক্রেট `device_token` দেবে (যেমন: `dev_live_xxxxx`)। এটি আপনার অ্যান্ড্রয়েড অ্যাপে কনফিগার করতে হবে।

---

## 📱 অ্যান্ড্রয়েড SMS ফরওয়ার্ডার সেটআপ

মার্চেন্টের ফোনে যে সিমে টাকা ঢুকবে, সেই ফোনে যেকোনো স্ট্যান্ডার্ড SMS Forwarder অ্যাপ (যেমন: *SMS Forwarder by Dan Ward*, *SmsForwarder Webhook*, অথবা কাস্টম নোটিফিকেশন লিসেনার APK) ইনস্টল করুন:

1. **Webhook URL দিন:**  
   `http://your-server-domain.com/api/v1/device/sync-sms/`
2. **HTTP Header যোগ করুন:**  
   `X-DEVICE-TOKEN: <আপনার_ডিভাইস_টোকেন>`  
   `Content-Type: application/json`
3. **Payload Format (JSON):**
   ```json
   {
     "sender": "bKash",
     "raw_message": "You have received Tk 500.00 from 017XXXXXXXX. Fee Tk 0.00. Balance Tk 5,500.00. TrxID 9K201A4BC1 at 12/10/2026 11:45"
   }
   ```
4. **টেস্টিং:** ফোন থেকে SMS আসলে তা সরাসরি গেটওয়ের **Raw SMS Logs** ট্যাবে জমা হবে।

---

## 💻 API ইন্টিগ্রেশন গাইড

### ১. চেকআউট ইনভয়েস তৈরি (Create Checkout)

আপনার ই-কমার্স বা ক্লায়েন্ট সাইট থেকে গ্রাহককে পেমেন্ট পেজে পাঠাতে এই রিকোয়েস্ট করুন:

* **Endpoint:** `POST /api/v1/checkout/create/`
* **Headers:**
  ```http
  Content-Type: application/json
  X-API-KEY: <আপনার_মার্চেন্ট_API_KEY>
  ```
* **Payload:**
  ```json
  {
    "order_id": "ORDER-9876",
    "amount": "500.00",
    "customer_name": "Rahim Ahmed",
    "customer_email": "rahim@example.com",
    "customer_phone": "01711223344",
    "metadata": {
      "plan": "Premium Package",
      "user_id": 45
    }
  }
  ```
* **Response (Success 201 Created):**
  ```json
  {
    "status": "success",
    "invoice_id": "2aef777e-14d5-4e17-a6bd-296b966acc4a",
    "order_id": "ORDER-9876",
    "amount": "500.00",
    "checkout_url": "http://127.0.0.1:8000/checkout/2aef777e-14d5-4e17-a6bd-296b966acc4a/",
    "expires_at": "2026-10-12T12:35:00Z"
  }
  ```
  *(আপনার গ্রাহককে সরাসরি `checkout_url`-এ রিডাইরেক্ট করুন)*

---

### ২. TrxID ভেরিফিকেশন (Manual / Hosted Verify)

কাস্টমার চেকআউট পেজে সাবমিট করলে বা এপিআই দিয়ে ভেরিফাই করতে চাইলে:

* **Endpoint:** `POST /api/v1/checkout/<invoice_uuid>/verify/`
* **Payload:**
  ```json
  {
    "trx_id": "9K201A4BC1",
    "provider": "BKASH"
  }
  ```
* **Response:**
  ```json
  {
    "status": "success",
    "message": "Payment verified successfully.",
    "invoice_id": "2aef777e-14d5-4e17-a6bd-296b966acc4a",
    "trx_id": "9K201A4BC1",
    "return_url": "https://merchant.example.com/payment/success?order_id=ORDER-9876"
  }
  ```

---

### ৩. মার্চেন্ট ওয়েবহুক হ্যান্ডলিং (Webhook Security)

পেমেন্ট সফল হওয়ার সাথে সাথে ব্যাকগ্রাউন্ডে আপনার মার্চেন্ট Webhook URL-এ একটি `POST` রিকোয়েস্ট পাঠানো হয়। এটি HMAC-SHA256 দ্বারা সাইন করা থাকে:

* **Header:** `X-SIGNATURE: <hmac_sha256_hash>`
* **Payload:**
  ```json
  {
    "event": "PAYMENT_COMPLETED",
    "invoice_id": "2aef777e-14d5-4e17-a6bd-296b966acc4a",
    "order_id": "ORDER-9876",
    "amount": "500.00",
    "trx_id": "9K201A4BC1",
    "customer_phone": "01711223344",
    "metadata": { "plan": "Premium Package" }
  }
  ```

#### সাইন ভেরিফাই করার PHP উদাহরণ:
```php
<?php
$payload = file_get_contents('php://input');
$signature = $_SERVER['HTTP_X_SIGNATURE'] ?? '';
$secret = 'YOUR_MERCHANT_API_SECRET';

$expectedSignature = hash_hmac('sha256', $payload, $secret);

if (hash_equals($expectedSignature, $signature)) {
    $data = json_decode($payload, true);
    // পেমেন্ট সফল, ডেটাবেজে অর্ডার কনফার্ম করুন
    $orderId = $data['order_id'];
    $trxId = $data['trx_id'];
    http_response_code(200);
    echo json_encode(["status" => "ok"]);
} else {
    http_response_code(400);
    exit('Invalid Signature');
}
?>
```

---

## ⚡ লোকাল সার্ভার রান ও ডিপ্লয়মেন্ট

### ১. সার্ভার রান করা (Local Development)
প্রজেক্ট ফোল্ডারে টার্মিনাল ওপেন করে নিচের কমান্ডটি দিন:
```bash
python manage.py runserver 127.0.0.1:8000
```

### ২. নতুন ডাটাবেজ মাইগ্রেশন (যদি মডেল পরিবর্তন করেন)
```bash
python manage.py makemigrations
python manage.py migrate
```

### ৩. স্ট্যাটিক ফাইল ও আইকন প্রস্তুত করা
```bash
python manage.py collectstatic --noinput
```

### ৪. নতুন অ্যাডমিন তৈরি করা
```bash
python manage.py createsuperuser
```

---

## 🧪 অটোমেটেড টেস্টিং

সিস্টেমে মাল্টি-টেন্যান্ট আইসোলেশন, ইনভয়েস মেয়াদ শেষ হওয়া, SMS ইনজেস্টের ইডেমপোটেন্সি (Duplicate TrxID হ্যান্ডলিং) এবং কনকারেন্ট ডাবল-স্পেন্ডিং রোধ সংক্রান্ত **৩০টি অটোমেটেড ইউনিট ও ইন্টিগ্রেশন টেস্ট** সংরক্ষিত রয়েছে।

সবগুলো টেস্ট রান করতে টার্মিনালে চালান:
```bash
python manage.py test
```
*ফলাফল:*
```text
Ran 30 tests in 0.481s
OK
```

---

## 💡 টিপস ও ট্রাবলশুটিং

1. **স্যান্ডবক্সে টেস্ট করতে চান?**  
   কোনো কোডিং ছাড়া টেস্ট করতে [http://127.0.0.1:8000/admin-dashboard/](http://127.0.0.1:8000/admin-dashboard/) এ যান এবং বামপাশের মেনু থেকে **API Sandbox** সিলেক্ট করুন। সেখান থেকে ৩ ক্লিকে ইনভয়েস তৈরি, ফেক SMS পাঠানো এবং TrxID ম্যাচ করে দেখতে পারবেন।
2. **ডাবল স্পেন্ডিং প্রোটেকশন:**  
   একই TrxID দিয়ে যদি দুইজন গ্রাহক একই মুহূর্তে সাবমিট করে, শুধুমাত্র প্রথম জন সফল হবে; দ্বিতীয় জনের রিকোয়েস্ট সাথে সাথে "Already Claimed" বা "Invalid" হিসেবে রিজেক্ট হয়ে যাবে।
3. **PWA অ্যাপ হিসেবে ব্যবহার:**  
   ব্রাউজারে [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/) ওপেন করলে ব্রাউজার বারে "Install App" বাটন পাবেন। ক্লিক করলে এটি পিসিতে বা ফোনে আলাদা সফটওয়্যার অ্যাপের মতো ইনস্টল হয়ে যাবে।
# gateway
