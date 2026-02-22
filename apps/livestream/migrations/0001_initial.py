"""
State-only migration: register the three livestream models with Django's
migration framework without touching the database.  The physical tables
(catalogue_livestreamsession, catalogue_livestreamattendance,
catalogue_livestreamrecording) already exist courtesy of catalogue 0002
and are preserved via Meta.db_table on each model.
"""

import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalogue", "0002_livestreamsession_livestreamrecording_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="LivestreamSession",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=uuid.uuid4,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("title", models.CharField(max_length=255)),
                        ("description", models.TextField(blank=True)),
                        ("start_time", models.DateTimeField()),
                        ("end_time", models.DateTimeField()),
                        (
                            "duration_minutes",
                            models.PositiveIntegerField(
                                help_text="Duration in minutes",
                                validators=[
                                    django.core.validators.MinValueValidator(15),
                                    django.core.validators.MaxValueValidator(480),
                                ],
                            ),
                        ),
                        ("timezone", models.CharField(default="UTC", max_length=50)),
                        ("is_recurring", models.BooleanField(default=False)),
                        (
                            "recurrence_pattern",
                            models.CharField(
                                choices=[
                                    ("none", "No Recurrence"),
                                    ("daily", "Daily"),
                                    ("weekly", "Weekly"),
                                    ("biweekly", "Bi-Weekly"),
                                    ("monthly", "Monthly"),
                                ],
                                default="none",
                                max_length=20,
                            ),
                        ),
                        ("recurrence_end_date", models.DateTimeField(blank=True, null=True)),
                        (
                            "recurrence_days",
                            models.JSONField(
                                blank=True,
                                default=list,
                                help_text="Days of week for weekly recurrence",
                            ),
                        ),
                        ("recurrence_order", models.PositiveIntegerField(default=0)),
                        (
                            "platform",
                            models.CharField(
                                choices=[("zoom", "Zoom"), ("custom", "Custom RTMP")],
                                default="zoom",
                                max_length=20,
                            ),
                        ),
                        (
                            "zoom_meeting_id",
                            models.CharField(
                                blank=True,
                                help_text="Zoom Meeting ID",
                                max_length=255,
                            ),
                        ),
                        (
                            "zoom_meeting_uuid",
                            models.CharField(
                                blank=True,
                                help_text="Zoom Meeting UUID",
                                max_length=255,
                            ),
                        ),
                        (
                            "zoom_host_id",
                            models.CharField(
                                blank=True,
                                help_text="Zoom Host ID",
                                max_length=255,
                            ),
                        ),
                        ("zoom_topic", models.CharField(blank=True, max_length=255)),
                        (
                            "join_url",
                            models.URLField(
                                blank=True,
                                help_text="URL for learners to join",
                            ),
                        ),
                        (
                            "start_url",
                            models.URLField(
                                blank=True,
                                help_text="URL for instructor to start (contains auth)",
                            ),
                        ),
                        (
                            "instructor_join_url",
                            models.URLField(
                                blank=True,
                                help_text="Alternative join URL for instructor",
                            ),
                        ),
                        (
                            "password",
                            models.CharField(
                                blank=True,
                                help_text="Meeting password",
                                max_length=50,
                            ),
                        ),
                        ("encrypted_password", models.CharField(blank=True, max_length=255)),
                        (
                            "auto_recording",
                            models.BooleanField(
                                default=True,
                                help_text="Automatically record the session",
                            ),
                        ),
                        (
                            "recording_url",
                            models.URLField(
                                blank=True,
                                help_text="URL of recorded session",
                            ),
                        ),
                        ("recording_start_time", models.DateTimeField(blank=True, null=True)),
                        ("recording_end_time", models.DateTimeField(blank=True, null=True)),
                        (
                            "recording_duration",
                            models.PositiveIntegerField(
                                default=0,
                                help_text="Recording duration in seconds",
                            ),
                        ),
                        (
                            "recording_file_size",
                            models.PositiveIntegerField(
                                default=0,
                                help_text="Recording file size in bytes",
                            ),
                        ),
                        (
                            "recording_download_url",
                            models.URLField(
                                blank=True,
                                help_text="Download URL for recording",
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("scheduled", "Scheduled"),
                                    ("live", "Live"),
                                    ("ended", "Ended"),
                                    ("cancelled", "Cancelled"),
                                ],
                                default="scheduled",
                                max_length=20,
                            ),
                        ),
                        ("max_attendees", models.PositiveIntegerField(blank=True, null=True)),
                        (
                            "waiting_room",
                            models.BooleanField(
                                default=True,
                                help_text="Enable waiting room",
                            ),
                        ),
                        ("mute_on_entry", models.BooleanField(default=True)),
                        ("allow_chat", models.BooleanField(default=True)),
                        ("allow_questions", models.BooleanField(default=True)),
                        ("host_video", models.BooleanField(default=True)),
                        ("participant_video", models.BooleanField(default=False)),
                        ("calendar_event_id", models.CharField(blank=True, max_length=255)),
                        (
                            "calendar_provider",
                            models.CharField(blank=True, default="google", max_length=50),
                        ),
                        ("calendar_etag", models.CharField(blank=True, max_length=255)),
                        ("total_attendees", models.PositiveIntegerField(default=0)),
                        ("peak_attendees", models.PositiveIntegerField(default=0)),
                        ("reminder_sent_24h", models.BooleanField(default=False)),
                        ("reminder_sent_1h", models.BooleanField(default=False)),
                        ("reminder_sent_15m", models.BooleanField(default=False)),
                        ("webhook_secret", models.CharField(blank=True, max_length=255)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("zoom_webhook_received", models.BooleanField(default=False)),
                        ("zoom_webhook_data", models.JSONField(blank=True, default=dict)),
                        (
                            "course",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="livestream_sessions",
                                to="catalogue.course",
                            ),
                        ),
                        (
                            "created_by",
                            models.ForeignKey(
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="created_livestreams",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "instructor",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="instructed_livestreams",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "parent_session",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="child_sessions",
                                to="livestream.livestreamsession",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Livestream Session",
                        "verbose_name_plural": "Livestream Sessions",
                        "db_table": "catalogue_livestreamsession",
                        "ordering": ["-start_time"],
                    },
                ),
                migrations.CreateModel(
                    name="LivestreamRecording",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=uuid.uuid4,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("zoom_recording_id", models.CharField(max_length=255, unique=True)),
                        ("zoom_meeting_id", models.CharField(max_length=255)),
                        ("recording_type", models.CharField(max_length=50)),
                        ("file_url", models.URLField()),
                        ("download_url", models.URLField(blank=True)),
                        ("file_size", models.PositiveIntegerField(default=0)),
                        ("file_extension", models.CharField(default="mp4", max_length=10)),
                        ("recording_start", models.DateTimeField()),
                        ("recording_end", models.DateTimeField()),
                        ("duration_seconds", models.PositiveIntegerField()),
                        ("is_processed", models.BooleanField(default=False)),
                        ("is_published", models.BooleanField(default=True)),
                        ("storage_path", models.CharField(blank=True, max_length=500)),
                        ("thumbnail_url", models.URLField(blank=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "session",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="recordings",
                                to="livestream.livestreamsession",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Livestream Recording",
                        "verbose_name_plural": "Livestream Recordings",
                        "db_table": "catalogue_livestreamrecording",
                        "ordering": ["-recording_start"],
                    },
                ),
                migrations.CreateModel(
                    name="LivestreamAttendance",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=uuid.uuid4,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("zoom_participant_id", models.CharField(blank=True, max_length=255)),
                        ("zoom_user_id", models.CharField(blank=True, max_length=255)),
                        ("joined_at", models.DateTimeField(blank=True, null=True)),
                        ("left_at", models.DateTimeField(blank=True, null=True)),
                        ("duration_seconds", models.PositiveIntegerField(default=0)),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("registered", "Registered"),
                                    ("joined", "Joined"),
                                    ("left", "Left"),
                                    ("completed", "Completed"),
                                    ("no_show", "No Show"),
                                ],
                                default="registered",
                                max_length=20,
                            ),
                        ),
                        ("questions_asked", models.PositiveIntegerField(default=0)),
                        ("chat_messages", models.PositiveIntegerField(default=0)),
                        ("raised_hand", models.BooleanField(default=False)),
                        ("device_info", models.CharField(blank=True, max_length=255)),
                        ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                        ("certificate_issued", models.BooleanField(default=False)),
                        ("certificate_url", models.URLField(blank=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "learner",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="livestream_attendances",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "session",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="attendances",
                                to="livestream.livestreamsession",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Livestream Attendance",
                        "verbose_name_plural": "Livestream Attendances",
                        "db_table": "catalogue_livestreamattendance",
                    },
                ),
                migrations.AddIndex(
                    model_name="livestreamsession",
                    index=models.Index(
                        fields=["course", "status"],
                        name="catalogue_l_course__4f30b9_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="livestreamsession",
                    index=models.Index(
                        fields=["instructor", "start_time"],
                        name="catalogue_l_instruc_fc4011_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="livestreamsession",
                    index=models.Index(
                        fields=["start_time", "status"],
                        name="catalogue_l_start_t_d8583b_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="livestreamsession",
                    index=models.Index(
                        fields=["zoom_meeting_id"],
                        name="catalogue_l_zoom_me_8c54b8_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="livestreamattendance",
                    index=models.Index(
                        fields=["session", "status"],
                        name="catalogue_l_session_1f16e6_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="livestreamattendance",
                    index=models.Index(
                        fields=["learner", "joined_at"],
                        name="catalogue_l_learner_14e3f5_idx",
                    ),
                ),
                migrations.AlterUniqueTogether(
                    name="livestreamattendance",
                    unique_together={("session", "learner")},
                ),
            ],
            database_operations=[],
        ),
    ]
