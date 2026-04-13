from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('livestream', '0004_livestreamquestion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='livestreamattendance',
            name='status',
            field=models.CharField(
                choices=[
                    ('registered', 'Registered'),
                    ('joined', 'Joined'),
                    ('left', 'Left'),
                    ('attended', 'Attended'),
                    ('absent', 'Absent'),
                    ('completed', 'Completed'),
                    ('no_show', 'No Show'),
                ],
                default='registered',
                max_length=20,
            ),
        ),
    ]
