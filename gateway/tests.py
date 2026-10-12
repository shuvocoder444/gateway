import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.contrib import admin
from rest_framework.test import APITestCase
from rest_framework import status

from gateway.models import (
    Merchant,
    PaymentMethod,
    Device,
    Invoice,
    SMSTransaction,
    MFSProvider,
    InvoiceStatus,
    SMSTransactionStatus,
)


class GatewayModelTests(TestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(
            name="Alpha Store",
            email="merchant@alpha.com",
            webhook_url="https://alpha.com/api/webhook/",
            return_url="https://alpha.com/success/",
            cancel_url="https://alpha.com/cancel/"
        )

        self.payment_method = PaymentMethod.objects.create(
            merchant=self.merchant,
            provider=MFSProvider.BKASH,
            account_number="01711000000",
            instructions="Send Money to this personal number."
        )

        self.device = Device.objects.create(
            merchant=self.merchant,
            device_name="Samsung Galaxy A12 (SIM 1)",
            sim_slot="SIM 1",
            battery_percentage=85
        )

    def test_merchant_creation_and_uuid(self):
        self.assertIsInstance(self.merchant.id, uuid.UUID)
        self.assertTrue(self.merchant.api_key.startswith("mfs_live_"))
        self.assertTrue(self.merchant.api_secret.startswith("mfs_sec_"))
        self.assertTrue(self.merchant.is_active)

    def test_payment_method_creation(self):
        self.assertIsInstance(self.payment_method.id, uuid.UUID)
        self.assertEqual(self.payment_method.provider, MFSProvider.BKASH)
        self.assertEqual(self.payment_method.merchant, self.merchant)

    def test_device_creation(self):
        self.assertIsInstance(self.device.id, uuid.UUID)
        self.assertTrue(self.device.device_token.startswith("dev_"))
        self.assertEqual(self.device.merchant, self.merchant)

    def test_invoice_creation_and_expiration(self):
        invoice = Invoice.objects.create(
            merchant=self.merchant,
            payment_method=self.payment_method,
            order_id="ORD-1001",
            amount=Decimal("1500.00"),
            customer_phone="01800000000"
        )
        self.assertIsInstance(invoice.id, uuid.UUID)
        self.assertIsInstance(invoice.reference_id, uuid.UUID)
        self.assertEqual(invoice.status, InvoiceStatus.PENDING)
        self.assertFalse(invoice.is_expired)
        self.assertGreater(invoice.expires_at, timezone.now())

    def test_sms_transaction_and_indexing(self):
        sms = SMSTransaction.objects.create(
            merchant=self.merchant,
            device=self.device,
            provider=MFSProvider.BKASH,
            sender="bKash",
            trx_id="BL89A1B2C3",
            amount=Decimal("1500.00"),
            counterpart_number="01800000000",
            raw_sms="You have received Tk 1,500.00 from 01800000000. TrxID BL89A1B2C3."
        )
        self.assertIsInstance(sms.id, uuid.UUID)
        self.assertEqual(sms.status, SMSTransactionStatus.UNUSED)
        self.assertEqual(sms.trx_id, "BL89A1B2C3")

        # Query using the composite indexed fields (merchant, trx_id)
        fetched = SMSTransaction.objects.filter(merchant=self.merchant, trx_id="BL89A1B2C3").first()
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, sms.id)

    def test_admin_registration(self):
        for model in [Merchant, PaymentMethod, Device, Invoice, SMSTransaction]:
            self.assertIn(model, admin.site._registry)


class GatewayAPITests(APITestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(
            name="Apex Commerce",
            email="billing@apex.com",
            webhook_url="https://apex.com/webhook/payment-ipn/",
            return_url="https://apex.com/checkout/success/"
        )

        self.payment_method = PaymentMethod.objects.create(
            merchant=self.merchant,
            provider=MFSProvider.BKASH,
            account_number="01912345678",
            instructions="Send Money to 01912345678"
        )

        self.device = Device.objects.create(
            merchant=self.merchant,
            device_name="Gateway Android Forwarder 1",
            battery_percentage=90
        )

    # 1. Checkout Create API Tests (POST /api/v1/checkout/create/)
    def test_checkout_create_success(self):
        url = '/api/v1/checkout/create/'
        payload = {
            "amount": "1250.00",
            "order_id": "APX-9988",
            "customer_name": "Rahim Khan",
            "customer_phone": "01700000000",
            "customer_email": "rahim@example.com",
            "metadata": {"cart_id": 42}
        }
        response = self.client.post(
            url,
            payload,
            format='json',
            HTTP_X_API_KEY=self.merchant.api_key
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("reference_id", data)
        self.assertIn("checkout_url", data)
        self.assertEqual(data["amount"], "1250.00")

        # Ensure invoice persisted in DB
        invoice = Invoice.objects.get(reference_id=data["reference_id"])
        self.assertEqual(invoice.merchant, self.merchant)
        self.assertEqual(invoice.amount, Decimal("1250.00"))
        self.assertEqual(invoice.status, InvoiceStatus.PENDING)

    def test_checkout_create_unauthorized(self):
        url = '/api/v1/checkout/create/'
        payload = {"amount": "500.00"}
        # Without header
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # With invalid API key
        response = self.client.post(
            url, payload, format='json', HTTP_X_API_KEY="invalid_key"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # 2. Device Sync SMS API Tests (POST /api/v1/device/sync-sms/)
    def test_device_sync_sms_success_and_duplicate_handling(self):
        url = '/api/v1/device/sync-sms/'
        payload = {
            "battery_percentage": 78,
            "messages": [
                {
                    "sender": "bKash",
                    "trx_id": "9B01XYZ123",
                    "amount": "1250.00",
                    "counterpart_number": "01700000000",
                    "raw_sms": "You have received Tk 1,250.00 from 01700000000. TrxID 9B01XYZ123",
                    "provider": "BKASH"
                },
                {
                    "sender": "NAGAD",
                    "trx_id": "7N99ABC888",
                    "amount": "800.00",
                    "counterpart_number": "01800000000",
                    "raw_sms": "Nagad: Tk 800.00 received from 01800000000. TxnID 7N99ABC888",
                    "provider": "NAGAD"
                }
            ]
        }

        # First sync call
        response = self.client.post(
            url,
            payload,
            format='json',
            HTTP_X_DEVICE_TOKEN=self.device.device_token
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["synced_count"], 2)
        self.assertEqual(data["duplicates_count"], 0)

        # Verify device telemetry updated
        self.device.refresh_from_db()
        self.assertEqual(self.device.battery_percentage, 78)
        self.assertIsNotNone(self.device.last_synced_at)

        # Second sync call with duplicate TrxIDs
        duplicate_payload = {
            "battery_percentage": 75,
            "messages": [
                {
                    "sender": "bKash",
                    "trx_id": "9B01XYZ123",  # duplicate
                    "amount": "1250.00",
                },
                {
                    "sender": "bKash",
                    "trx_id": "NEW_TRX_456",  # new
                    "amount": "300.00",
                }
            ]
        }

        dup_response = self.client.post(
            url,
            duplicate_payload,
            format='json',
            HTTP_X_DEVICE_TOKEN=self.device.device_token
        )
        self.assertEqual(dup_response.status_code, status.HTTP_200_OK)
        dup_data = dup_response.json()
        self.assertEqual(dup_data["synced_count"], 1)
        self.assertEqual(dup_data["duplicates_count"], 1)
        self.assertIn("9B01XYZ123", dup_data["duplicate_trx_ids"])
        self.assertIn("NEW_TRX_456", dup_data["synced_trx_ids"])

    def test_device_sync_unauthorized(self):
        url = '/api/v1/device/sync-sms/'
        response = self.client.post(url, {"messages": []}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # 3. Checkout Verify API Tests (POST /api/v1/checkout/<uuid>/verify/)
    @patch('gateway.services.requests.post')
    def test_checkout_verify_success_and_webhook_dispatch(self, mock_requests_post):
        # Mock external webhook endpoint response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests_post.return_value = mock_resp

        # Create invoice
        invoice = Invoice.objects.create(
            merchant=self.merchant,
            order_id="ORD-VERIFY-1",
            amount=Decimal("1250.00"),
            currency="BDT"
        )

        # Create matching incoming SMS transaction
        sms = SMSTransaction.objects.create(
            merchant=self.merchant,
            device=self.device,
            provider=MFSProvider.BKASH,
            sender="bKash",
            trx_id="TRXVERIFY123",
            amount=Decimal("1250.00"),
            counterpart_number="01711223344",
            raw_sms="Received Tk 1250.00. TrxID TRXVERIFY123",
            status=SMSTransactionStatus.UNUSED
        )

        verify_url = f"/api/v1/checkout/{invoice.reference_id}/verify/"
        response = self.client.post(
            verify_url,
            {"trx_id": "TRXVERIFY123", "sender_number": "01711223344"},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["trx_id"], "TRXVERIFY123")
        self.assertEqual(data["invoice_status"], InvoiceStatus.COMPLETED)

        # Verify DB states
        invoice.refresh_from_db()
        sms.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.COMPLETED)
        self.assertEqual(invoice.trx_id, "TRXVERIFY123")
        self.assertIsNotNone(invoice.paid_at)
        self.assertEqual(sms.status, SMSTransactionStatus.MATCHED)
        self.assertEqual(sms.matched_invoice, invoice)

    def test_checkout_verify_prevents_double_spending(self):
        # Create two invoices for the same merchant
        inv1 = Invoice.objects.create(
            merchant=self.merchant,
            order_id="ORD-1",
            amount=Decimal("500.00")
        )
        inv2 = Invoice.objects.create(
            merchant=self.merchant,
            order_id="ORD-2",
            amount=Decimal("500.00")
        )

        # Single SMS transaction with Tk 500
        sms = SMSTransaction.objects.create(
            merchant=self.merchant,
            device=self.device,
            trx_id="DOUBLESPEND99",
            amount=Decimal("500.00"),
            sender="bKash",
            status=SMSTransactionStatus.UNUSED
        )

        # First verification succeeds
        with patch('gateway.services.requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            resp1 = self.client.post(
                f"/api/v1/checkout/{inv1.reference_id}/verify/",
                {"trx_id": "DOUBLESPEND99"},
                format='json'
            )
            self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        # Second verification with the same TrxID must fail with 400 (Double spending prevented)
        resp2 = self.client.post(
            f"/api/v1/checkout/{inv2.reference_id}/verify/",
            {"trx_id": "DOUBLESPEND99"},
            format='json'
        )
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("TRX_ALREADY_USED", str(resp2.content))

        # Check inv2 is still PENDING
        inv2.refresh_from_db()
        self.assertEqual(inv2.status, InvoiceStatus.PENDING)

    def test_checkout_verify_amount_mismatch(self):
        inv = Invoice.objects.create(
            merchant=self.merchant,
            amount=Decimal("1000.00")
        )
        SMSTransaction.objects.create(
            merchant=self.merchant,
            trx_id="MISMATCH123",
            amount=Decimal("500.00"),  # Less than invoice
            sender="bKash",
            status=SMSTransactionStatus.UNUSED
        )

        resp = self.client.post(
            f"/api/v1/checkout/{inv.reference_id}/verify/",
            {"trx_id": "MISMATCH123"},
            format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("AMOUNT_MISMATCH", str(resp.content))

    def test_checkout_verify_expired_invoice(self):
        inv = Invoice.objects.create(
            merchant=self.merchant,
            amount=Decimal("200.00"),
            expires_at=timezone.now() - timedelta(minutes=5)  # Expired
        )
        SMSTransaction.objects.create(
            merchant=self.merchant,
            trx_id="EXPIREDTRX",
            amount=Decimal("200.00"),
            sender="bKash",
            status=SMSTransactionStatus.UNUSED
        )

        resp = self.client.post(
            f"/api/v1/checkout/{inv.reference_id}/verify/",
            {"trx_id": "EXPIREDTRX"},
            format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.EXPIRED)

    # 4. Hosted Checkout Page UI Tests (GET /checkout/<uuid>/)
    def test_hosted_checkout_page_renders(self):
        invoice = Invoice.objects.create(
            merchant=self.merchant,
            order_id="ORD-UI-77",
            amount=Decimal("2500.00"),
            currency="BDT",
            customer_name="Sabbir Ahmed"
        )

        url = f"/checkout/{invoice.reference_id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, 'checkout.html')
        content = response.content.decode('utf-8')

        # Check merchant details rendered
        self.assertIn("Apex Commerce", content)
        # Check amount rendered
        self.assertIn("2500.00", content)
        # Check active payment method rendered
        self.assertIn("01912345678", content)
        self.assertIn("bKash", content)
        # Check countdown display element rendered
        self.assertIn("countdown-display", content)
        # Check TrxID verification field rendered
        self.assertIn("trx_id_input", content)

    # 5. PWA & Merchant Dashboard Tests
    def test_pwa_manifest_endpoint(self):
        response = self.client.get('/manifest.json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('application/manifest+json', response.headers.get('Content-Type', ''))
        data = response.json()
        self.assertEqual(data["short_name"], "MFS Gateway")
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["start_url"], "/dashboard/")
        self.assertTrue(len(data["icons"]) >= 3)

    def test_pwa_serviceworker_endpoint(self):
        response = self.client.get('/serviceworker.js')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('application/javascript', response.headers.get('Content-Type', ''))
        self.assertEqual(response.headers.get('Service-Worker-Allowed'), '/')
        content = response.content.decode('utf-8')
        self.assertIn('CACHE_VERSION', content)
        self.assertIn('self.addEventListener', content)

    def test_merchant_dashboard_renders(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, 'dashboard.html')
        content = response.content.decode('utf-8')
        self.assertIn('MFS Gateway', content)
        self.assertIn('Install App', content)
        self.assertIn('manifest.json', content)
        self.assertIn('serviceworker.js', content)
        self.assertIn('Apex Commerce', content)

    def test_root_redirects_to_dashboard(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, '/admin-dashboard/')

    def test_admin_dashboard_renders_successfully(self):
        response = self.client.get('/admin-dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode('utf-8')
        self.assertIn('Admin Control Center', content)
        self.assertIn('Dashboard Overview', content)
        self.assertIn('Merchants', content)
        self.assertIn('Invoices', content)
        self.assertIn('SMS Logs', content)
        self.assertIn('API Sandbox', content)


class AdminDashboardActionAPITests(APITestCase):
    """
    Test cases verifying complete direct management from Admin Dashboard:
    Merchants, Payment Methods, Devices, Invoices, and SMS logs CRUD.
    """
    def setUp(self):
        self.merchant = Merchant.objects.create(
            name="Control Test Merchant",
            email="control@test.com"
        )

    def test_create_and_manage_merchant(self):
        # 1. Create Merchant
        create_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'create_merchant', 'name': 'New Tenant Co', 'email': 'new@tenant.com'},
            format='json'
        )
        self.assertEqual(create_res.status_code, status.HTTP_200_OK)
        m_id = create_res.json()['merchant']['id']

        # 2. Toggle Status
        toggle_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'toggle_merchant', 'id': m_id},
            format='json'
        )
        self.assertEqual(toggle_res.status_code, status.HTTP_200_OK)
        self.assertFalse(toggle_res.json()['is_active'])

        # 3. Regenerate Keys
        old_key = create_res.json()['merchant']['api_key']
        regen_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'regenerate_merchant_keys', 'id': m_id},
            format='json'
        )
        self.assertEqual(regen_res.status_code, status.HTTP_200_OK)
        self.assertNotEqual(old_key, regen_res.json()['api_key'])

        # 4. Delete Merchant
        del_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'delete_merchant', 'id': m_id},
            format='json'
        )
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(Merchant.objects.filter(id=m_id).exists())

    def test_payment_method_actions(self):
        # Create PM
        create_res = self.client.post(
            '/api/v1/admin/action/',
            {
                'action': 'create_payment_method',
                'merchant_id': str(self.merchant.id),
                'provider': 'BKASH',
                'account_number': '01899999999',
                'account_type': 'PERSONAL'
            },
            format='json'
        )
        self.assertEqual(create_res.status_code, status.HTTP_200_OK)
        pm_id = create_res.json()['id']

        # Toggle PM
        toggle_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'toggle_payment_method', 'id': pm_id},
            format='json'
        )
        self.assertEqual(toggle_res.status_code, status.HTTP_200_OK)
        self.assertFalse(toggle_res.json()['is_active'])

        # Delete PM
        del_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'delete_payment_method', 'id': pm_id},
            format='json'
        )
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(PaymentMethod.objects.filter(id=pm_id).exists())

    def test_device_actions(self):
        # Create Device
        create_res = self.client.post(
            '/api/v1/admin/action/',
            {
                'action': 'create_device',
                'merchant_id': str(self.merchant.id),
                'device_name': 'Test Android Phone'
            },
            format='json'
        )
        self.assertEqual(create_res.status_code, status.HTTP_200_OK)
        dev_id = create_res.json()['id']
        old_token = create_res.json()['device_token']

        # Regenerate Token
        regen_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'regenerate_device_token', 'id': dev_id},
            format='json'
        )
        self.assertEqual(regen_res.status_code, status.HTTP_200_OK)
        self.assertNotEqual(old_token, regen_res.json()['device_token'])

        # Delete Device
        del_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'delete_device', 'id': dev_id},
            format='json'
        )
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(Device.objects.filter(id=dev_id).exists())

    def test_invoice_actions(self):
        # Create Invoice
        create_res = self.client.post(
            '/api/v1/admin/action/',
            {
                'action': 'create_invoice',
                'merchant_id': str(self.merchant.id),
                'amount': '750.00',
                'order_id': 'ADMIN-ORD-1'
            },
            format='json'
        )
        self.assertEqual(create_res.status_code, status.HTTP_200_OK)
        inv_id = create_res.json()['invoice_id']

        # Mark Paid
        mark_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'mark_invoice_paid', 'id': inv_id, 'trx_id': 'MANUALTRX123'},
            format='json'
        )
        self.assertEqual(mark_res.status_code, status.HTTP_200_OK)
        inv = Invoice.objects.get(id=inv_id)
        self.assertEqual(inv.status, InvoiceStatus.COMPLETED)
        self.assertEqual(inv.trx_id, 'MANUALTRX123')

        # Cancel / Delete
        del_res = self.client.post(
            '/api/v1/admin/action/',
            {'action': 'delete_invoice', 'id': inv_id},
            format='json'
        )
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(Invoice.objects.filter(id=inv_id).exists())


class MultiTenantInvoiceCreationTests(APITestCase):
    """
    Tests covering multi-tenant invoice creation with valid and invalid API keys,
    tenant data isolation, and unauthorized access controls.
    """
    def setUp(self):
        # Tenant A
        self.merchant_a = Merchant.objects.create(
            name="Alpha Corp",
            email="billing@alpha.com",
            is_active=True
        )
        self.pm_a = PaymentMethod.objects.create(
            merchant=self.merchant_a,
            provider=MFSProvider.BKASH,
            account_number="01700000001"
        )

        # Tenant B
        self.merchant_b = Merchant.objects.create(
            name="Beta Ltd",
            email="billing@beta.com",
            is_active=True
        )
        self.pm_b = PaymentMethod.objects.create(
            merchant=self.merchant_b,
            provider=MFSProvider.NAGAD,
            account_number="01800000002"
        )

    def test_multitenant_invoice_creation_valid_key(self):
        url = '/api/v1/checkout/create/'

        # 1. Merchant A creates invoice
        resp_a = self.client.post(
            url,
            {"amount": "750.00", "order_id": "ORD-ALPHA-1"},
            format='json',
            HTTP_X_API_KEY=self.merchant_a.api_key
        )
        self.assertEqual(resp_a.status_code, status.HTTP_201_CREATED)
        data_a = resp_a.json()

        inv_a = Invoice.objects.get(reference_id=data_a["reference_id"])
        self.assertEqual(inv_a.merchant, self.merchant_a)
        self.assertEqual(inv_a.amount, Decimal("750.00"))

        # 2. Merchant B creates invoice
        resp_b = self.client.post(
            url,
            {"amount": "1200.00", "order_id": "ORD-BETA-1"},
            format='json',
            HTTP_X_API_KEY=self.merchant_b.api_key
        )
        self.assertEqual(resp_b.status_code, status.HTTP_201_CREATED)
        data_b = resp_b.json()

        inv_b = Invoice.objects.get(reference_id=data_b["reference_id"])
        self.assertEqual(inv_b.merchant, self.merchant_b)
        self.assertEqual(inv_b.amount, Decimal("1200.00"))

        # 3. Verify tenant isolation in database
        self.assertEqual(self.merchant_a.invoices.count(), 1)
        self.assertEqual(self.merchant_b.invoices.count(), 1)
        self.assertFalse(self.merchant_a.invoices.filter(id=inv_b.id).exists())
        self.assertFalse(self.merchant_b.invoices.filter(id=inv_a.id).exists())

    def test_invoice_creation_invalid_and_missing_api_keys(self):
        url = '/api/v1/checkout/create/'
        payload = {"amount": "500.00"}

        # Missing header
        resp_missing = self.client.post(url, payload, format='json')
        self.assertEqual(resp_missing.status_code, status.HTTP_401_UNAUTHORIZED)

        # Invalid/random key
        resp_invalid = self.client.post(
            url, payload, format='json', HTTP_X_API_KEY="mfs_live_non_existent_key_12345"
        )
        self.assertEqual(resp_invalid.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invoice_creation_inactive_merchant_rejected(self):
        url = '/api/v1/checkout/create/'
        # Deactivate Merchant A
        self.merchant_a.is_active = False
        self.merchant_a.save()

        response = self.client.post(
            url,
            {"amount": "500.00"},
            format='json',
            HTTP_X_API_KEY=self.merchant_a.api_key
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tenant_cannot_use_another_merchant_payment_method(self):
        url = '/api/v1/checkout/create/'
        # Merchant A attempts to bind Merchant B's payment method ID
        response = self.client.post(
            url,
            {
                "amount": "500.00",
                "payment_method_id": str(self.pm_b.id)
            },
            format='json',
            HTTP_X_API_KEY=self.merchant_a.api_key
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("payment_method_id", response.json())


class SMSSyncAndIdempotencyTests(APITestCase):
    """
    Tests covering Android forwarder SMS sync idempotency, safe deduplication,
    and cross-tenant isolation.
    """
    def setUp(self):
        self.merchant = Merchant.objects.create(name="Delta Store", is_active=True)
        self.device = Device.objects.create(
            merchant=self.merchant,
            device_name="SIM Forwarder Delta",
            is_active=True
        )

        self.other_merchant = Merchant.objects.create(name="Gamma Store", is_active=True)
        self.other_device = Device.objects.create(
            merchant=self.other_merchant,
            device_name="SIM Forwarder Gamma",
            is_active=True
        )

    def test_sms_sync_idempotency_single_message_repeated(self):
        url = '/api/v1/device/sync-sms/'
        payload = {
            "battery_percentage": 88,
            "sender": "bKash",
            "trx_id": "REPEAT_TRX_999",
            "amount": "500.00",
            "counterpart_number": "01711223344",
            "raw_sms": "Received Tk 500.00. TrxID REPEAT_TRX_999"
        }

        # First synchronization
        resp1 = self.client.post(
            url, payload, format='json', HTTP_X_DEVICE_TOKEN=self.device.device_token
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp1.json()["synced_count"], 1)
        self.assertEqual(resp1.json()["duplicates_count"], 0)
        self.assertEqual(SMSTransaction.objects.filter(trx_id="REPEAT_TRX_999").count(), 1)

        # Subsequent 4 identical calls must not fail and must not duplicate records
        for i in range(4):
            resp_repeat = self.client.post(
                url, payload, format='json', HTTP_X_DEVICE_TOKEN=self.device.device_token
            )
            self.assertEqual(resp_repeat.status_code, status.HTTP_200_OK)
            self.assertEqual(resp_repeat.json()["synced_count"], 0)
            self.assertEqual(resp_repeat.json()["duplicates_count"], 1)
            self.assertIn("REPEAT_TRX_999", resp_repeat.json()["duplicate_trx_ids"])

        # Exactly 1 record should exist in the database
        self.assertEqual(
            SMSTransaction.objects.filter(merchant=self.merchant, trx_id="REPEAT_TRX_999").count(),
            1
        )

    def test_sms_sync_batch_with_internal_and_external_duplicates(self):
        url = '/api/v1/device/sync-sms/'
        # First ingest one record
        SMSTransaction.objects.create(
            merchant=self.merchant,
            device=self.device,
            trx_id="PRE_EXISTING_1",
            amount=Decimal("100.00"),
            sender="bKash"
        )

        batch_payload = {
            "battery_percentage": 82,
            "messages": [
                {"sender": "bKash", "trx_id": "PRE_EXISTING_1", "amount": "100.00"},  # duplicate of existing DB record
                {"sender": "bKash", "trx_id": "BATCH_NEW_2", "amount": "200.00"},     # new
                {"sender": "bKash", "trx_id": "BATCH_NEW_3", "amount": "300.00"},     # new
                {"sender": "bKash", "trx_id": "BATCH_NEW_2", "amount": "200.00"},     # duplicate within same batch
            ]
        }

        response = self.client.post(
            url, batch_payload, format='json', HTTP_X_DEVICE_TOKEN=self.device.device_token
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["synced_count"], 2)
        self.assertEqual(data["duplicates_count"], 2)
        self.assertIn("BATCH_NEW_2", data["synced_trx_ids"])
        self.assertIn("BATCH_NEW_3", data["synced_trx_ids"])
        self.assertIn("PRE_EXISTING_1", data["duplicate_trx_ids"])

        # Total in DB for this merchant must be 3
        self.assertEqual(self.merchant.sms_transactions.count(), 3)

    def test_cross_merchant_trx_id_independence(self):
        url = '/api/v1/device/sync-sms/'
        common_trx = "SHARED_TRX_777"

        # Merchant Delta syncs SHARED_TRX_777
        resp_delta = self.client.post(
            url,
            {"sender": "bKash", "trx_id": common_trx, "amount": "1000.00"},
            format='json',
            HTTP_X_DEVICE_TOKEN=self.device.device_token
        )
        self.assertEqual(resp_delta.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_delta.json()["synced_count"], 1)

        # Merchant Gamma also syncs SHARED_TRX_777 via its own forwarder
        resp_gamma = self.client.post(
            url,
            {"sender": "bKash", "trx_id": common_trx, "amount": "1000.00"},
            format='json',
            HTTP_X_DEVICE_TOKEN=self.other_device.device_token
        )
        self.assertEqual(resp_gamma.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_gamma.json()["synced_count"], 1)

        # Both records co-exist safely without collision because uniqueness is scoped per merchant
        self.assertTrue(
            SMSTransaction.objects.filter(merchant=self.merchant, trx_id=common_trx).exists()
        )
        self.assertTrue(
            SMSTransaction.objects.filter(merchant=self.other_merchant, trx_id=common_trx).exists()
        )

    def test_sms_sync_invalid_or_inactive_device_token(self):
        url = '/api/v1/device/sync-sms/'

        # Invalid token
        resp_invalid = self.client.post(
            url, {"messages": []}, format='json', HTTP_X_DEVICE_TOKEN="dev_invalid_token"
        )
        self.assertEqual(resp_invalid.status_code, status.HTTP_401_UNAUTHORIZED)

        # Inactive device
        self.device.is_active = False
        self.device.save()
        resp_inactive = self.client.post(
            url, {"messages": []}, format='json', HTTP_X_DEVICE_TOKEN=self.device.device_token
        )
        self.assertEqual(resp_inactive.status_code, status.HTTP_401_UNAUTHORIZED)


from django.test import TransactionTestCase
from concurrent.futures import ThreadPoolExecutor
from django.db import connection
from rest_framework.exceptions import ValidationError


class RaceConditionAndConcurrencyTests(TransactionTestCase):
    """
    Tests covering race condition prevention and atomic pessimistic locking (select_for_update)
    when the same TrxID is submitted simultaneously by concurrent threads.
    """
    def setUp(self):
        self.merchant = Merchant.objects.create(
            name="Concurrency Testing Corp",
            webhook_url="",  # No external webhook lookup during concurrency test
            is_active=True
        )
        self.device = Device.objects.create(
            merchant=self.merchant,
            device_name="Bridge Phone 1",
            is_active=True
        )

    def test_simultaneous_trx_id_submission_prevents_double_spending(self):
        """
        Simulate two concurrent threads attempting to verify two separate invoices
        using the EXACT same TrxID at the exact same moment.
        Pessimistic locking must ensure only ONE succeeds, and the other is rejected.
        """
        import time
        from django.db import OperationalError
        from gateway.services import verify_and_settle_invoice

        trx_code = "CONCURRENT_TRX_999"
        amount = Decimal("500.00")

        # 1. Create single unused SMS transaction
        sms = SMSTransaction.objects.create(
            merchant=self.merchant,
            device=self.device,
            trx_id=trx_code,
            amount=amount,
            sender="bKash",
            status=SMSTransactionStatus.UNUSED
        )

        # 2. Create two separate pending invoices for the same merchant and amount
        inv1 = Invoice.objects.create(
            merchant=self.merchant,
            order_id="ORD-CONCUR-1",
            amount=amount,
            currency="BDT"
        )
        inv2 = Invoice.objects.create(
            merchant=self.merchant,
            order_id="ORD-CONCUR-2",
            amount=amount,
            currency="BDT"
        )

        def worker_verify(reference_id):
            connection.close()  # Ensure thread gets its own fresh database connection
            for _ in range(10):
                try:
                    invoice = verify_and_settle_invoice(
                        reference_id=reference_id,
                        trx_id=trx_code
                    )
                    return ("SUCCESS", invoice.id)
                except ValidationError as exc:
                    return ("REJECTED", exc.detail)
                except OperationalError:
                    # In SQLite, concurrent file write attempts serialize with a brief lock; retry cleanly
                    time.sleep(0.04)
                    connection.close()
                    continue
                except Exception as exc:
                    return ("ERROR", str(exc))
                finally:
                    connection.close()
            return ("REJECTED", "Lock timeout")

        # Execute both workers simultaneously using ThreadPoolExecutor
        with patch('gateway.services.requests.post'):
            with ThreadPoolExecutor(max_workers=2) as executor:
                future1 = executor.submit(worker_verify, inv1.reference_id)
                future2 = executor.submit(worker_verify, inv2.reference_id)
                res1 = future1.result()
                res2 = future2.result()

        results = [res1, res2]
        statuses = [r[0] for r in results]

        # Exactly ONE must succeed, and exactly ONE must be rejected
        self.assertEqual(statuses.count("SUCCESS"), 1)
        self.assertEqual(statuses.count("REJECTED"), 1)

        # Verify database integrity: only one invoice completed
        inv1.refresh_from_db()
        inv2.refresh_from_db()
        sms.refresh_from_db()

        completed_invoices = [inv for inv in [inv1, inv2] if inv.status == InvoiceStatus.COMPLETED]
        pending_invoices = [inv for inv in [inv1, inv2] if inv.status == InvoiceStatus.PENDING]

        self.assertEqual(len(completed_invoices), 1)
        self.assertEqual(len(pending_invoices), 1)

        # SMS must be MATCHED to the single completed invoice
        winning_invoice = completed_invoices[0]
        self.assertEqual(sms.status, SMSTransactionStatus.MATCHED)
        self.assertEqual(sms.matched_invoice, winning_invoice)
        self.assertEqual(winning_invoice.trx_id, trx_code)

    def test_simultaneous_verification_on_same_invoice(self):
        """
        Simulate double-click / concurrent requests verifying the SAME invoice.
        Pessimistic locking must ensure the first marks COMPLETED and the second
        cleanly receives 'already completed' error.
        """
        import time
        from django.db import OperationalError
        from gateway.services import verify_and_settle_invoice

        trx_code = "SAME_INV_TRX_555"
        amount = Decimal("350.00")

        SMSTransaction.objects.create(
            merchant=self.merchant,
            device=self.device,
            trx_id=trx_code,
            amount=amount,
            sender="Nagad",
            status=SMSTransactionStatus.UNUSED
        )

        inv = Invoice.objects.create(
            merchant=self.merchant,
            order_id="ORD-DOUBLE-CLICK",
            amount=amount,
            currency="BDT"
        )

        def worker_same_invoice():
            connection.close()
            for _ in range(10):
                try:
                    invoice = verify_and_settle_invoice(
                        reference_id=inv.reference_id,
                        trx_id=trx_code
                    )
                    return ("SUCCESS", invoice.id)
                except ValidationError as exc:
                    return ("REJECTED", exc.detail)
                except OperationalError:
                    time.sleep(0.04)
                    connection.close()
                    continue
                except Exception as exc:
                    return ("ERROR", str(exc))
                finally:
                    connection.close()
            return ("REJECTED", "Lock timeout")

        with patch('gateway.services.requests.post'):
            with ThreadPoolExecutor(max_workers=2) as executor:
                fut1 = executor.submit(worker_same_invoice)
                fut2 = executor.submit(worker_same_invoice)
                res1 = fut1.result()
                res2 = fut2.result()

        results = [res1, res2]
        statuses = [r[0] for r in results]

        self.assertEqual(statuses.count("SUCCESS"), 1)
        self.assertEqual(statuses.count("REJECTED"), 1)

        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.COMPLETED)
        self.assertEqual(inv.trx_id, trx_code)

