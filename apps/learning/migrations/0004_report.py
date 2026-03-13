# Report model - created separately to avoid Submission conflict

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0003_add_submission_model"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Report",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "report_type",
                    models.CharField(
                        choices=[
                            ("user_activity", "User Activity"),
                            ("course_performance", "Course Performance"),
                            ("enrollment", "Enrollment"),
                            ("completion", "Completion"),
                            ("assessment", "Assessment"),
                            ("revenue", "Revenue"),
                        ],
                        max_length=30,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("processing", "Processing"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                        ],
                        default="processing",
                        max_length=20,
                    ),
                ),
                ("file", models.FileField(blank=True, null=True, upload_to="reports/")),
                ("file_size", models.CharField(blank=True, max_length=50, null=True)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                (
                    "generated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="generated_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at"],
            },
        ),
    ]
