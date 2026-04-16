from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0009_create_missing_quiz_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkshopAttendance",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("present", "Present"),
                            ("absent", "Absent"),
                            ("late", "Late"),
                        ],
                        default="present",
                        max_length=20,
                    ),
                ),
                ("grade", models.PositiveIntegerField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("marked_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workshop_attendances",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workshop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendances",
                        to="learning.workshop",
                    ),
                ),
            ],
            options={
                "unique_together": {("workshop", "user")},
                "ordering": ["-marked_at"],
            },
        ),
    ]
