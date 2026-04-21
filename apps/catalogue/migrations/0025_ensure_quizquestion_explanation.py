from django.db import migrations, models


def _ensure_explanation_column(apps, schema_editor):
    conn = schema_editor.connection
    table = "catalogue_quizquestion"
    col = "explanation"

    with conn.cursor() as cursor:
        if conn.vendor == "sqlite":
            cursor.execute(f'PRAGMA table_info("{table}")')
            columns = [row[1] for row in cursor.fetchall()]
            if col in columns:
                return
        elif conn.vendor == "postgresql":
            cursor.execute(
                """SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s AND column_name = %s""",
                [table, col],
            )
            if cursor.fetchone():
                return
        elif conn.vendor == "mysql":
            cursor.execute(
                """SELECT 1 FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = %s AND column_name = %s""",
                [table, col],
            )
            if cursor.fetchone():
                return

    with conn.cursor() as cursor:
        if conn.vendor == "sqlite":
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT ''"
            )
        elif conn.vendor == "postgresql":
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN "{col}" text NOT NULL DEFAULT %s',
                [""],
            )
        elif conn.vendor == "mysql":
            cursor.execute(
                f"ALTER TABLE `{table}` ADD COLUMN `{col}` longtext NOT NULL"
            )
            cursor.execute(
                f"ALTER TABLE `{table}` ALTER COLUMN `{col}` SET DEFAULT %s",
                [""],
            )


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0024_review_add_is_featured_is_rejected_change_default"),
    ]

    operations = [
        migrations.RunPython(_ensure_explanation_column, _noop),
    ]
