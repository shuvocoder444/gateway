from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('gateway', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='owner',
            field=models.OneToOneField(
                blank=True,
                help_text='Login account that owns this merchant workspace',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='merchant_profile',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
