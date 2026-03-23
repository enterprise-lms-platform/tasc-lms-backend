# Generated manually for Phase 2 approval workflow

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0016_add_course_approval_request'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='rejection_reason',
            field=models.TextField(
                blank=True,
                help_text='Reason provided by reviewer when course was rejected; cleared on resubmit.',
            ),
        ),
    ]
