from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0005_subscription_duration_days"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="success_email_sent",
            field=models.BooleanField(default=False),
        ),
    ]
