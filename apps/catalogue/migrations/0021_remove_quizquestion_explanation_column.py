# Corrective migration: drop stray catalogue_quizquestion.explanation
#
# Some local DBs applied phantom migrations (files not in repo) that added
# explanation NOT NULL while QuizQuestion model has no such field — causing
# IntegrityError on insert. This migration removes the column if present only.
#
# Drifted DBs that have django_migrations rows for missing 0019/0020 may need:
#   DELETE FROM django_migrations WHERE app='catalogue' AND name IN (
#     '0019_quizquestion_explanation', '0020_sessionattachment');
# before running migrate, if `manage.py migrate` errors about missing nodes.

from django.db import migrations


def _drop_explanation_if_present(apps, schema_editor):
    conn = schema_editor.connection
    table = "catalogue_quizquestion"
    col = "explanation"

    with conn.cursor() as cursor:
        if conn.vendor == "sqlite":
            cursor.execute(f'PRAGMA table_info("{table}")')
            columns = [row[1] for row in cursor.fetchall()]
            if col not in columns:
                return
            # SQLite 3.35+ (DROP COLUMN)
            cursor.execute(f'ALTER TABLE "{table}" DROP COLUMN "{col}"')
            return

        if conn.vendor == "postgresql":
            # Idempotent on Postgres 9.1+
            cursor.execute(
                f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "{col}"'
            )
            return

        if conn.vendor == "mysql":
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = %s
                  AND column_name = %s
                """,
                [table, col],
            )
            if not cursor.fetchone():
                return
            cursor.execute(f"ALTER TABLE `{table}` DROP COLUMN `{col}`")


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        (
            "catalogue",
            "0018_rename_catalogue_c_status_9a8f2c_idx_catalogue_c_status_9b807a_idx_and_more",
        ),
    ]

    # No model state change — QuizQuestion never had explanation in Django state.
    operations = [
        migrations.RunPython(_drop_explanation_if_present, _noop),
    ]
