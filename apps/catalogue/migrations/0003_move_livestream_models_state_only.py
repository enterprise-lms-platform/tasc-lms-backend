"""
State-only migration: remove LivestreamSession, LivestreamAttendance, and
LivestreamRecording from catalogue's migration state.  No DDL is executed;
the physical tables are retained and are now owned by apps.livestream.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0002_livestreamsession_livestreamrecording_and_more"),
        ("livestream", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="LivestreamAttendance"),
                migrations.DeleteModel(name="LivestreamRecording"),
                migrations.DeleteModel(name="LivestreamSession"),
            ],
            database_operations=[],
        ),
    ]
