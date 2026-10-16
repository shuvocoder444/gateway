from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('gateway', '0003_bangla_qr_provider'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='checkout_display_name',
            field=models.CharField(blank=True, help_text='Name shown to customers on hosted checkout', max_length=255),
        ),
        migrations.AddField(
            model_name='merchant',
            name='logo',
            field=models.ImageField(blank=True, help_text='Merchant logo shown on hosted checkout', null=True, upload_to='merchant_logos/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='checkout_copyright',
            field=models.CharField(blank=True, help_text='Optional merchant copyright/footer text on hosted checkout', max_length=180),
        ),
        migrations.AddField(
            model_name='merchant',
            name='support_email',
            field=models.EmailField(blank=True, help_text='Customer support email shown on hosted checkout', max_length=254),
        ),
        migrations.AddField(
            model_name='merchant',
            name='support_phone',
            field=models.CharField(blank=True, help_text='Customer support phone shown on hosted checkout', max_length=32),
        ),
    ]
