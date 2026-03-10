# Generated manually for Instructor Quiz Builder MVP

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0011_rename_catalogue_module_course_order_idx_catalogue_m_course__fe6513_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="Quiz",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("settings", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quiz",
                        to="catalogue.session",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="QuizQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "question_type",
                    models.CharField(
                        choices=[
                            ("multiple-choice", "Multiple Choice"),
                            ("true-false", "True/False"),
                            ("short-answer", "Short Answer"),
                            ("essay", "Essay"),
                            ("matching", "Matching"),
                            ("fill-blank", "Fill in the Blank"),
                        ],
                        max_length=32,
                    ),
                ),
                ("question_text", models.TextField()),
                ("points", models.PositiveIntegerField(default=10)),
                ("answer_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "quiz",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="questions",
                        to="catalogue.quiz",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
    ]
