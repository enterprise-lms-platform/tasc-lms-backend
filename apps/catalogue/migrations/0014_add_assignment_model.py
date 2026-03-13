# Generated for Assignments V1 - instructor assignment authoring

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0013_add_question_bank_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="Assignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "assignment_type",
                    models.CharField(
                        choices=[
                            ("project", "Project"),
                            ("essay", "Essay"),
                            ("code", "Code Submission"),
                            ("presentation", "Presentation"),
                            ("research", "Research"),
                        ],
                        default="project",
                        max_length=20,
                    ),
                ),
                ("instructions", models.TextField(blank=True, default="")),
                ("max_points", models.PositiveIntegerField(default=100)),
                ("due_date", models.DateTimeField(blank=True, null=True)),
                ("available_from", models.DateTimeField(blank=True, null=True)),
                ("allow_late", models.BooleanField(default=False)),
                ("late_cutoff_date", models.DateTimeField(blank=True, null=True)),
                (
                    "penalty_type",
                    models.CharField(
                        choices=[
                            ("percentage", "Percentage per day"),
                            ("fixed", "Fixed percentage"),
                            ("none", "No penalty"),
                        ],
                        default="none",
                        max_length=20,
                    ),
                ),
                ("penalty_percent", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("allowed_file_types", models.JSONField(blank=True, default=list)),
                ("max_file_size_mb", models.PositiveIntegerField(blank=True, null=True)),
                ("rubric_criteria", models.JSONField(blank=True, default=list)),
                ("settings", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignment",
                        to="catalogue.session",
                    ),
                ),
            ],
            options={
                "verbose_name": "Assignment",
                "verbose_name_plural": "Assignments",
            },
        ),
    ]
