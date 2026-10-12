from decimal import Decimal
from django.core.management.base import BaseCommand
from gateway.models import Merchant, PaymentMethod, Device, Invoice, MFSProvider, AccountType


class Command(BaseCommand):
    help = "Seed demo merchant, payment methods, and sample invoice for instant testing."

    def handle(self, *args, **options):
        merchant, created = Merchant.objects.get_or_create(
            name="Apex Mart BD",
            defaults={
                "email": "contact@apexmart.com.bd",
                "webhook_url": "https://webhook.site/sample",
                "return_url": "https://apexmart.com.bd/orders/success/",
                "cancel_url": "https://apexmart.com.bd/orders/cancel/"
            }
        )

        PaymentMethod.objects.get_or_create(
            merchant=merchant,
            provider=MFSProvider.BKASH,
            defaults={
                "account_number": "01711223344",
                "account_type": AccountType.PERSONAL,
                "instructions": "Go to bKash App -> Send Money to this personal number.",
                "display_order": 1
            }
        )

        PaymentMethod.objects.get_or_create(
            merchant=merchant,
            provider=MFSProvider.NAGAD,
            defaults={
                "account_number": "01811556677",
                "account_type": AccountType.PERSONAL,
                "instructions": "Go to Nagad App -> Send Money to this personal number.",
                "display_order": 2
            }
        )

        PaymentMethod.objects.get_or_create(
            merchant=merchant,
            provider=MFSProvider.ROCKET,
            defaults={
                "account_number": "019118899001",
                "account_type": AccountType.PERSONAL,
                "instructions": "Dial *322# or Rocket App -> Send Money.",
                "display_order": 3
            }
        )

        PaymentMethod.objects.get_or_create(
            merchant=merchant,
            provider=MFSProvider.CELLFIN,
            defaults={
                "account_number": "01611002233",
                "account_type": AccountType.PERSONAL,
                "instructions": "Open Cellfin -> Fund Transfer / Direct Pay.",
                "display_order": 4
            }
        )

        device, _ = Device.objects.get_or_create(
            merchant=merchant,
            device_name="Samsung Galaxy A12 (SIM 1)",
            defaults={
                "battery_percentage": 92,
                "sim_slot": "SIM 1"
            }
        )

        invoice = Invoice.objects.create(
            merchant=merchant,
            order_id="DEMO-ORD-101",
            amount=Decimal("1250.00"),
            currency="BDT",
            customer_name="Sabbir Ahmed",
            customer_phone="01799887766"
        )

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded demo data!"))
        self.stdout.write(f"Merchant: {merchant.name}")
        self.stdout.write(f"API Key: {merchant.api_key}")
        self.stdout.write(f"Device Token: {device.device_token}")
        self.stdout.write(f"Sample Checkout URL: http://127.0.0.1:8000/checkout/{invoice.reference_id}/")
