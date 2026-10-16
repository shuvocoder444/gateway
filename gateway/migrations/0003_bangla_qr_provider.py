from django.db import migrations, models


PAYMENT_CHOICES = [
    ('BKASH', 'bKash'),
    ('NAGAD', 'Nagad'),
    ('ROCKET', 'Rocket'),
    ('CELLFIN', 'Cellfin'),
    ('UPAY', 'Upay'),
    ('BANGLA_QR', 'Bangla QR'),
    ('OTHER', 'Other'),
]


class Migration(migrations.Migration):
    dependencies = [
        ('gateway', '0002_merchant_owner'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymentmethod',
            name='provider',
            field=models.CharField(
                choices=PAYMENT_CHOICES,
                db_index=True,
                default='BKASH',
                help_text='MFS Provider brand',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='paymentmethod',
            name='account_number',
            field=models.CharField(
                blank=True,
                help_text='Receiving wallet/phone number; optional for Bangla QR',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='smstransaction',
            name='provider',
            field=models.CharField(
                choices=PAYMENT_CHOICES,
                db_index=True,
                default='BKASH',
                help_text='Detected MFS provider',
                max_length=20,
            ),
        ),
    ]
