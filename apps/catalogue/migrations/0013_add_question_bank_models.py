# Generated for Instructor Question Bank MVP

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalogue", "0012_add_quiz_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuestionCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="question_categories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["order", "name", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="questioncategory",
            constraint=models.UniqueConstraint(
                fields=("owner", "name"),
                name="catalogue_questioncategory_owner_name_unique",
            ),
        ),
        migrations.CreateModel(
            name="BankQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
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
                ("difficulty", models.CharField(blank=True, default="", max_length=16)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("explanation", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="questions",
                        to="catalogue.questioncategory",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bank_questions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="quizquestion",
            name="source_bank_question",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quiz_question_copies",
                to="catalogue.bankquestion",
            ),
        ),
    ]
