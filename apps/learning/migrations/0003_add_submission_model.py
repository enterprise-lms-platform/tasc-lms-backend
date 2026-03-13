# Generated for Submission V1

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0014_add_assignment_model"),
        ("learning", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Submission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("submitted", "Submitted"), ("graded", "Graded")],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("submitted_text", models.TextField(blank=True, default="")),
                ("submitted_file_url", models.URLField(blank=True, max_length=2048, null=True)),
                ("submitted_file_name", models.CharField(blank=True, max_length=255, null=True)),
                ("grade", models.PositiveIntegerField(blank=True, null=True)),
                ("feedback", models.TextField(blank=True, default="")),
                ("internal_notes", models.TextField(blank=True, default="")),
                ("graded_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to="catalogue.assignment",
                    ),
                ),
                (
                    "enrollment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to="learning.enrollment",
                    ),
                ),
                (
                    "graded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="graded_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("enrollment", "assignment")},
            },
        ),
        migrations.AddIndex(
            model_name="submission",
            index=models.Index(
                fields=["enrollment", "assignment"],
                name="learning_su_enrollm_a4d3a6_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="submission",
            index=models.Index(
                fields=["assignment", "status"],
                name="learning_su_assignm_c8f2b1_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="submission",
            index=models.Index(fields=["status"], name="learning_su_status_2e8a9c_idx"),
        ),
    ]
