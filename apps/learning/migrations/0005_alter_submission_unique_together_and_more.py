# Bridges DB drift: legacy learning_submission(session_id, unique on enrollment+session)
# vs migration state after 0004 (assignment_id, unique on enrollment+assignment).
# Database work is done explicitly; Django state is updated via state_operations only.

from django.db import migrations, models


SUBMISSION_TABLE = "learning_submission"
ASSIGNMENT_TABLE = "catalogue_assignment"


def _table_columns(schema_editor, table_name):
    with schema_editor.connection.cursor() as cursor:
        desc = schema_editor.connection.introspection.get_table_description(
            cursor, table_name
        )
    out = []
    for c in desc:
        out.append(getattr(c, "name", c[0]))
    return out


def _drop_submission_unique_constraints(schema_editor):
    """Remove all UNIQUE constraints / unique indexes on learning_submission (not the PK)."""
    connection = schema_editor.connection
    qn = connection.ops.quote_name
    table = SUBMISSION_TABLE
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)
    for name, details in constraints.items():
        if details.get("primary_key"):
            continue
        if not details.get("unique"):
            continue
        cols = details.get("columns") or []
        if not cols:
            continue
        if connection.vendor == "postgresql":
            schema_editor.execute(
                f"ALTER TABLE {qn(table)} DROP CONSTRAINT IF EXISTS {qn(name)}"
            )
        elif connection.vendor == "sqlite":
            # Unique from Meta.unique_together is typically a unique index on SQLite.
            schema_editor.execute(f"DROP INDEX IF EXISTS {qn(name)}")
        else:
            # MySQL / others: Django uses ALTER TABLE DROP INDEX for unique indexes in many cases.
            try:
                schema_editor.execute(
                    f"ALTER TABLE {qn(table)} DROP INDEX {qn(name)}"
                )
            except Exception:
                schema_editor.execute(
                    f"ALTER TABLE {qn(table)} DROP CONSTRAINT {qn(name)}"
                )


def _repair_legacy_session_based_postgresql(schema_editor):
    """
    Staging drift: table has session_id and unique(enrollment,session), no assignment_id.
    """
    qn = schema_editor.connection.ops.quote_name
    table = SUBMISSION_TABLE
    _drop_submission_unique_constraints(schema_editor)

    schema_editor.execute(
        f"""
        ALTER TABLE {qn(table)}
        ADD COLUMN IF NOT EXISTS {qn("assignment_id")} bigint NULL
        """
    )
    schema_editor.execute(
        f"""
        UPDATE {qn(table)} AS ls
        SET {qn("assignment_id")} = ca.{qn("id")}
        FROM {qn(ASSIGNMENT_TABLE)} AS ca
        WHERE ca.{qn("session_id")} = ls.{qn("session_id")}
        """
    )
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM {qn(table)}
            WHERE {qn("assignment_id")} IS NULL
            """
        )
        orphan = cursor.fetchone()[0]
    if orphan:
        raise ValueError(
            f"{SUBMISSION_TABLE} has {orphan} row(s) with no matching "
            f"{ASSIGNMENT_TABLE} row for session_id; fix or delete before migrating."
        )

    schema_editor.execute(
        f"""
        ALTER TABLE {qn(table)}
        ALTER COLUMN {qn("assignment_id")} SET NOT NULL
        """
    )
    schema_editor.execute(
        f"ALTER TABLE {qn(table)} DROP CONSTRAINT IF EXISTS "
        f"{qn('learning_submission_assignment_id_fkey')}"
    )
    schema_editor.execute(
        f"""
        ALTER TABLE {qn(table)}
        ADD CONSTRAINT {qn("learning_submission_assignment_id_fkey")}
        FOREIGN KEY ({qn("assignment_id")})
        REFERENCES {qn(ASSIGNMENT_TABLE)} ({qn("id")})
        ON DELETE CASCADE
        """
    )
    schema_editor.execute(
        f"ALTER TABLE {qn(table)} DROP COLUMN IF EXISTS {qn('session_id')}"
    )


def _add_attempt_number_if_missing(schema_editor):
    cols = _table_columns(schema_editor, SUBMISSION_TABLE)
    if "attempt_number" in cols:
        return
    qn = schema_editor.connection.ops.quote_name
    table = SUBMISSION_TABLE
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f"""
            ALTER TABLE {qn(table)}
            ADD COLUMN {qn("attempt_number")} integer NOT NULL DEFAULT 1
            """
        )
        schema_editor.execute(
            f"""
            ALTER TABLE {qn(table)}
            ALTER COLUMN {qn("attempt_number")} DROP DEFAULT
            """
        )
    else:
        schema_editor.execute(
            f"""
            ALTER TABLE {qn(table)}
            ADD COLUMN {qn("attempt_number")} integer NOT NULL DEFAULT 1
            """
        )


def _add_unique_triple(schema_editor):
    qn = schema_editor.connection.ops.quote_name
    table = SUBMISSION_TABLE
    name = "learning_submission_enrollment_id_assignment_id_attempt_number_uniq"
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f"ALTER TABLE {qn(table)} DROP CONSTRAINT IF EXISTS {qn(name)}"
        )
        schema_editor.execute(
            f"""
            ALTER TABLE {qn(table)}
            ADD CONSTRAINT {qn(name)}
            UNIQUE ({qn("enrollment_id")}, {qn("assignment_id")}, {qn("attempt_number")})
            """
        )
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {qn(name)}
            ON {qn(table)} ({qn("enrollment_id")}, {qn("assignment_id")}, {qn("attempt_number")})
            """
        )
    else:
        schema_editor.execute(
            f"""
            ALTER TABLE {qn(table)}
            ADD CONSTRAINT {qn(name)}
            UNIQUE ({qn("enrollment_id")}, {qn("assignment_id")}, {qn("attempt_number")})
            """
        )


def forwards(apps, schema_editor):
    cols = _table_columns(schema_editor, SUBMISSION_TABLE)

    if "attempt_number" in cols:
        # Idempotent re-run: ensure triple unique exists; state is still applied via state_operations.
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(
                cursor, SUBMISSION_TABLE
            )
        for _name, details in constraints.items():
            if not details.get("unique"):
                continue
            c = details.get("columns") or []
            if set(c) == {"enrollment_id", "assignment_id", "attempt_number"}:
                return
        _drop_submission_unique_constraints(schema_editor)
        _add_unique_triple(schema_editor)
        return

    if "session_id" in cols and "assignment_id" not in cols:
        if schema_editor.connection.vendor != "postgresql":
            raise RuntimeError(
                "learning_submission is session-based (no assignment_id). "
                "Run this migration on PostgreSQL first, or rebuild the DB from migrations."
            )
        _repair_legacy_session_based_postgresql(schema_editor)
    else:
        # Expected post-0004 schema: assignment_id present, unique on (enrollment, assignment).
        _drop_submission_unique_constraints(schema_editor)

    _add_attempt_number_if_missing(schema_editor)
    _add_unique_triple(schema_editor)


def backwards(apps, schema_editor):
    cols = _table_columns(schema_editor, SUBMISSION_TABLE)
    qn = schema_editor.connection.ops.quote_name
    table = SUBMISSION_TABLE
    name = "learning_submission_enrollment_id_assignment_id_attempt_number_uniq"

    _drop_submission_unique_constraints(schema_editor)

    if "attempt_number" in cols:
        if schema_editor.connection.vendor == "sqlite":
            schema_editor.execute(f"DROP INDEX IF EXISTS {qn(name)}")
        elif schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(
                f"ALTER TABLE {qn(table)} DROP CONSTRAINT IF EXISTS {qn(name)}"
            )

        schema_editor.execute(
            f"ALTER TABLE {qn(table)} DROP COLUMN IF EXISTS {qn('attempt_number')}"
        )

    if "assignment_id" in cols:
        schema_editor.execute(
            f"""
            ALTER TABLE {qn(table)}
            ADD CONSTRAINT {qn("learning_submission_enrollment_id_assignment_id_uniq")}
            UNIQUE ({qn("enrollment_id")}, {qn("assignment_id")})
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0019_quizquestion_explanation"),
        ("learning", "0004_quizanswer_quizsubmission_report_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, backwards),
            ],
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="submission",
                    unique_together=set(),
                ),
                migrations.AddField(
                    model_name="submission",
                    name="attempt_number",
                    field=models.PositiveIntegerField(default=1),
                ),
                migrations.AlterUniqueTogether(
                    name="submission",
                    unique_together={
                        ("enrollment", "assignment", "attempt_number"),
                    },
                ),
            ],
        ),
    ]
