"""
Create learning_quizsubmission and learning_quizanswer tables.

Migration 0004 was --fake applied on both local and staging, so these tables
were never actually created even though Django's state believes they exist.
This migration uses SeparateDatabaseAndState with empty state_operations
(state is already correct) and creates only the missing tables via
schema_editor.create_model(), which generates correct DDL for both SQLite
and PostgreSQL.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    existing = set(schema_editor.connection.introspection.table_names())

    QuizSubmission = apps.get_model("learning", "QuizSubmission")
    QuizAnswer = apps.get_model("learning", "QuizAnswer")

    if QuizSubmission._meta.db_table not in existing:
        schema_editor.create_model(QuizSubmission)

    if QuizAnswer._meta.db_table not in existing:
        schema_editor.create_model(QuizAnswer)


def backwards(apps, schema_editor):
    existing = set(schema_editor.connection.introspection.table_names())

    QuizAnswer = apps.get_model("learning", "QuizAnswer")
    QuizSubmission = apps.get_model("learning", "QuizSubmission")

    if QuizAnswer._meta.db_table in existing:
        schema_editor.delete_model(QuizAnswer)

    if QuizSubmission._meta.db_table in existing:
        schema_editor.delete_model(QuizSubmission)


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0008_workshop"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(forwards, backwards),
            ],
        ),
    ]
