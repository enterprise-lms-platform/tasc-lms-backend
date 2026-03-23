# Generated manually for Phase 1 approval workflow

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0015_coursereview'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('pending_approval', 'Pending Approval'),
                    ('published', 'Published'),
                    ('rejected', 'Rejected'),
                    ('archived', 'Archived'),
                ],
                default='draft',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='CourseApprovalRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_type', models.CharField(
                    choices=[('create', 'Create'), ('edit', 'Edit'), ('delete', 'Delete')],
                    default='create',
                    max_length=20,
                )),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                    default='pending',
                    max_length=20,
                )),
                ('reviewer_comments', models.TextField(blank=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='approval_requests',
                    to='catalogue.course',
                )),
                ('requested_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='course_approval_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('reviewed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reviewed_approval_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='courseapprovalrequest',
            index=models.Index(fields=['status'], name='catalogue_c_status_9a8f2c_idx'),
        ),
        migrations.AddIndex(
            model_name='courseapprovalrequest',
            index=models.Index(fields=['course', 'status'], name='catalogue_c_course__e7d5a3_idx'),
        ),
    ]
