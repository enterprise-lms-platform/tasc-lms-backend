from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta
from .models import (
    Enrollment, SessionProgress, Certificate, Discussion, DiscussionReply, Report, Submission,
    QuizSubmission, QuizAnswer, SavedCourse
)
from apps.catalogue.models import Quiz, QuizQuestion
from apps.catalogue.models import Course, Session
from apps.accounts.rbac import is_admin_like, is_instructor
from apps.payments.permissions import user_has_active_subscription


class EnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for Enrollment model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    course_thumbnail = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    time_remaining_days = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'user', 'user_name', 'user_email',
            'course', 'course_title', 'course_thumbnail',
            'organization', 'organization_name',
            'status', 'enrolled_at', 'completed_at', 'expires_at',
            'progress_percentage', 'last_accessed_at', 'last_accessed_session',
            'paid_amount', 'currency',
            'certificate_issued', 'certificate_issued_at',
            'time_remaining_days'
        ]
        read_only_fields = ['id', 'enrolled_at', 'progress_percentage', 'last_accessed_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_course_title(self, obj):
        return obj.course.title
    
    def get_course_thumbnail(self, obj):
        return obj.course.thumbnail
    
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    def get_time_remaining_days(self, obj):
        if obj.expires_at:
            remaining = obj.expires_at - timezone.now()
            return max(remaining.days, 0)
        return None


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating enrollments."""

    class Meta:
        model = Enrollment
        fields = [
            'course', 'organization', 'paid_amount', 'currency'
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context['request'].user
        # Bypass for admin-like and instructors
        if is_admin_like(user) or is_instructor(user):
            return attrs
        if not user_has_active_subscription(user):
            raise PermissionDenied('An active subscription is required to enroll in courses.')
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        course = validated_data['course']
        defaults = {
            'organization': validated_data.get('organization'),
            'paid_amount': validated_data.get('paid_amount', 0),
            'currency': validated_data.get('currency', 'USD'),
        }
        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults=defaults,
        )
        self._created = created
        return enrollment


class BulkEnrollmentSerializer(serializers.Serializer):
    """Serializer for bulk enrolling users."""
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all())
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )


class SessionProgressSerializer(serializers.ModelSerializer):
    """Serializer for SessionProgress model."""
    session_title = serializers.SerializerMethodField()
    session_type = serializers.SerializerMethodField()
    duration_minutes = serializers.SerializerMethodField()
    time_spent_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = SessionProgress
        fields = [
            'id', 'enrollment', 'session', 'session_title', 'session_type',
            'is_started', 'started_at', 'is_completed', 'completed_at',
            'time_spent_seconds', 'time_spent_minutes', 'last_accessed_at',
            'notes', 'duration_minutes'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'last_accessed_at']
    
    def get_session_title(self, obj):
        return obj.session.title
    
    def get_session_type(self, obj):
        return obj.session.session_type
    
    def get_duration_minutes(self, obj):
        return obj.session.video_duration_seconds // 60 if obj.session.video_duration_seconds else 0
    
    def get_time_spent_minutes(self, obj):
        return obj.time_spent_seconds // 60


class SessionProgressCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating session progress."""
    
    class Meta:
        model = SessionProgress
        fields = [
            'session', 'is_started', 'is_completed',
            'time_spent_seconds', 'notes'
        ]


class CertificateSerializer(serializers.ModelSerializer):
    """Serializer for Certificate model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = Certificate
        fields = [
            'id', 'enrollment',
            'user_name', 'user_email', 'course_title',
            'certificate_number', 'issued_at', 'expiry_date',
            'is_valid', 'is_expired',
            'pdf_url', 'verification_url'
        ]
        read_only_fields = ['id', 'certificate_number', 'issued_at']
    
    def get_user_name(self, obj):
        return obj.enrollment.user.get_full_name() or obj.enrollment.user.email
    
    def get_user_email(self, obj):
        return obj.enrollment.user.email
    
    def get_course_title(self, obj):
        return obj.enrollment.course.title


class CertificateCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating certificates."""
    
    class Meta:
        model = Certificate
        fields = ['expiry_date']


class DiscussionSerializer(serializers.ModelSerializer):
    """Serializer for Discussion model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    session_title = serializers.SerializerMethodField()
    reply_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Discussion
        fields = [
            'id', 'user', 'user_name', 'user_email', 'user_avatar',
            'course', 'course_title', 'session', 'session_title',
            'title', 'content',
            'is_pinned', 'is_locked', 'is_deleted',
            'reply_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_user_avatar(self, obj):
        return obj.user.avatar
    
    def get_course_title(self, obj):
        return obj.course.title if obj.course else None
    
    def get_session_title(self, obj):
        return obj.session.title if obj.session else None


class DiscussionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating discussions."""
    
    class Meta:
        model = Discussion
        fields = [
            'course', 'session', 'title', 'content'
        ]


class DiscussionReplySerializer(serializers.ModelSerializer):
    """Serializer for DiscussionReply model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = DiscussionReply
        fields = [
            'id', 'discussion', 'user', 'user_name', 'user_email', 'user_avatar',
            'parent', 'content', 'is_deleted',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_user_avatar(self, obj):
        return obj.user.avatar


class DiscussionReplyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating discussion replies."""
    
    class Meta:
        model = DiscussionReply
        fields = [
            'discussion', 'parent', 'content'
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        discussion = attrs.get('discussion')
        if discussion and discussion.is_locked:
            raise serializers.ValidationError(
                {'discussion': 'This discussion is locked and cannot receive new replies.'}
            )
        return attrs


class SessionProgressUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating session progress."""
    
    class Meta:
        model = SessionProgress
        fields = [
            'is_completed', 'time_spent_seconds'
        ]


class ReportSerializer(serializers.ModelSerializer):
    """Serializer for Report model."""
    
    class Meta:
        model = Report
        fields = [
            'id', 'report_type', 'name', 'generated_by',
            'generated_at', 'status', 'file', 'file_size', 'parameters'
        ]
        read_only_fields = ['id', 'generated_by', 'generated_at', 'status']


class ReportGenerateSerializer(serializers.Serializer):
    """Serializer for generating a new report."""
    
    report_type = serializers.ChoiceField(choices=Report.Type.choices)
    parameters = serializers.JSONField(required=False, default=dict)


class SubmissionSerializer(serializers.ModelSerializer):
    """Read serializer for Submission (V1: assignment-based)."""
    assignment_title = serializers.SerializerMethodField()
    session_title = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    graded_by_name = serializers.SerializerMethodField()
    max_points = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            'id', 'enrollment', 'assignment',
            'assignment_title', 'session_title', 'max_points',
            'status', 'submitted_at', 'attempt_number',
            'submitted_text', 'submitted_file_url', 'submitted_file_name',
            'grade', 'feedback', 'internal_notes',
            'graded_at', 'graded_by', 'graded_by_name',
            'user_name', 'user_email',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_assignment_title(self, obj):
        return obj.assignment.session.title if obj.assignment and obj.assignment.session else None

    def get_session_title(self, obj):
        return obj.assignment.session.title if obj.assignment and obj.assignment.session else None

    def get_user_name(self, obj):
        return obj.enrollment.user.get_full_name() or obj.enrollment.user.email

    def get_user_email(self, obj):
        return obj.enrollment.user.email

    def get_graded_by_name(self, obj):
        return (obj.graded_by.get_full_name() or obj.graded_by.email) if obj.graded_by else None

    def get_max_points(self, obj):
        return obj.assignment.max_points if obj.assignment else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            role = getattr(request.user, 'role', None)
            if role not in (User.Role.INSTRUCTOR, User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
                data.pop('internal_notes', None)
        return data


class SubmissionCreateSerializer(serializers.ModelSerializer):
    """Create serializer for Submission (V1)."""

    class Meta:
        model = Submission
        fields = ['enrollment', 'assignment', 'status', 'submitted_text', 'submitted_file_url', 'submitted_file_name']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError('Authentication required.')

        enrollment = attrs.get('enrollment')
        assignment = attrs.get('assignment')
        if not enrollment or not assignment:
            return attrs

        if enrollment.user_id != request.user.id:
            raise serializers.ValidationError(
                {'enrollment': 'You can only create submissions for your own enrollments.'}
            )

        if assignment.session.course_id != enrollment.course_id:
            raise serializers.ValidationError(
                {'assignment': "Assignment does not belong to this enrollment's course."}
            )

        # Check attempts
        existing_attempts = Submission.objects.filter(enrollment=enrollment, assignment=assignment).count()
        if assignment.max_attempts and existing_attempts >= assignment.max_attempts:
            raise serializers.ValidationError(
                {'non_field_errors': [f'Maximum attempts ({assignment.max_attempts}) reached for this assignment.']}
            )
            
        attrs['attempt_number'] = existing_attempts + 1

        status_val = attrs.get('status', Submission.Status.DRAFT)
        if status_val == Submission.Status.GRADED:
            raise serializers.ValidationError(
                {'status': 'Learners cannot set status to graded.'}
            )

        if status_val == Submission.Status.SUBMITTED:
            text = (attrs.get('submitted_text') or '').strip()
            file_url = attrs.get('submitted_file_url')
            file_name = attrs.get('submitted_file_name')
            
            if not text and not file_url:
                raise serializers.ValidationError(
                    {'non_field_errors': ['Submitted text or file URL is required when submitting.']}
                )
                
            if file_url and file_name and assignment.allowed_file_types:
                import os
                ext = os.path.splitext(file_name)[1].lower()
                allowed_exts = [e.lower() if e.startswith('.') else f'.{e.lower()}' for e in assignment.allowed_file_types]
                if ext not in allowed_exts:
                    raise serializers.ValidationError(
                        {'submitted_file_name': f'File type {ext} is not allowed. Allowed types: {", ".join(allowed_exts)}'}
                    )

        return attrs

    def create(self, validated_data):
        status_val = validated_data.get('status', Submission.Status.DRAFT)
        submitted_at = timezone.now() if status_val == Submission.Status.SUBMITTED else None
        return Submission.objects.create(submitted_at=submitted_at, **validated_data)


class SubmissionUpdateSerializer(serializers.ModelSerializer):
    """Update serializer for Submission (V1: PATCH draft only)."""

    class Meta:
        model = Submission
        fields = ['status', 'submitted_text', 'submitted_file_url', 'submitted_file_name']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        if instance.status != Submission.Status.DRAFT:
            raise serializers.ValidationError(
                {'non_field_errors': ['Only draft submissions can be edited.']}
            )

        status_val = attrs.get('status', instance.status)
        if status_val == Submission.Status.GRADED:
            raise serializers.ValidationError(
                {'status': 'Learners cannot set status to graded.'}
            )

        if status_val == Submission.Status.SUBMITTED:
            text = (attrs.get('submitted_text', instance.submitted_text) or '').strip()
            file_url = attrs.get('submitted_file_url', instance.submitted_file_url)
            file_name = attrs.get('submitted_file_name', instance.submitted_file_name)
            
            if not text and not file_url:
                raise serializers.ValidationError(
                    {'non_field_errors': ['Submitted text or file URL is required when submitting.']}
                )
                
            if file_url and file_name and instance.assignment.allowed_file_types:
                import os
                ext = os.path.splitext(file_name)[1].lower()
                allowed_exts = [e.lower() if e.startswith('.') else f'.{e.lower()}' for e in instance.assignment.allowed_file_types]
                if ext not in allowed_exts:
                    raise serializers.ValidationError(
                        {'submitted_file_name': f'File type {ext} is not allowed. Allowed types: {", ".join(allowed_exts)}'}
                    )

        return attrs

    def update(self, instance, validated_data):
        status_val = validated_data.get('status', instance.status)
        if status_val == Submission.Status.SUBMITTED:
            validated_data['submitted_at'] = timezone.now()
        return super().update(instance, validated_data)


class GradeSubmissionSerializer(serializers.Serializer):
    """Serializer for grading submissions (V1)."""
    grade = serializers.IntegerField(min_value=0, required=True)
    feedback = serializers.CharField(required=False, allow_blank=True, default='')
    internal_notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        submission = self.context.get('submission')
        if submission:
            if submission.status != Submission.Status.SUBMITTED:
                raise serializers.ValidationError(
                    {'non_field_errors': ['Only submitted submissions can be graded.']}
                )
            max_points = submission.assignment.max_points
            if attrs['grade'] > max_points:
                raise serializers.ValidationError(
                    {'grade': f'Grade must be between 0 and {max_points}.'}
                )
        return attrs


class QuizAnswerSerializer(serializers.ModelSerializer):
    """Serializer for QuizAnswer model."""

    class Meta:
        model = QuizAnswer
        fields = ['id', 'question', 'selected_answer', 'is_correct', 'points_awarded']
        read_only_fields = ['id', 'is_correct', 'points_awarded']


class QuizSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for QuizSubmission model (list/retrieve)."""
    answers = QuizAnswerSerializer(many=True, read_only=True)
    quiz_title = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()

    class Meta:
        model = QuizSubmission
        fields = [
            'id', 'enrollment', 'quiz', 'quiz_title', 'course_title',
            'attempt_number', 'score', 'max_score', 'passed',
            'time_spent_seconds', 'submitted_at', 'answers'
        ]
        read_only_fields = ['id', 'attempt_number', 'score', 'max_score', 'passed', 'submitted_at']

    def get_quiz_title(self, obj):
        return obj.quiz.session.title if obj.quiz.session else None

    def get_course_title(self, obj):
        return obj.quiz.session.course.title if obj.quiz.session and obj.quiz.session.course else None


class QuizAnswerCreateSerializer(serializers.Serializer):
    """Serializer for a single answer in submission creation."""
    question = serializers.IntegerField()
    selected_answer = serializers.JSONField()


class QuizSubmissionCreateSerializer(serializers.Serializer):
    """Serializer for creating a quiz submission with answers."""
    enrollment = serializers.IntegerField()
    quiz = serializers.IntegerField()
    time_spent_seconds = serializers.IntegerField(required=False, default=0)
    answers = QuizAnswerCreateSerializer(many=True)

    def validate_enrollment(self, value):
        try:
            return Enrollment.objects.get(id=value)
        except Enrollment.DoesNotExist:
            raise serializers.ValidationError("Enrollment not found.")

    def validate_quiz(self, value):
        try:
            return Quiz.objects.get(id=value)
        except Quiz.DoesNotExist:
            raise serializers.ValidationError("Quiz not found.")

    def validate(self, attrs):
        enrollment = attrs.get('enrollment')
        quiz = attrs.get('quiz')

        if quiz.session.course_id != enrollment.course_id:
            raise serializers.ValidationError(
                {"quiz": "The quiz does not belong to the enrollment's course."}
            )

        existing_attempts = QuizSubmission.objects.filter(
            enrollment=enrollment,
            quiz=quiz
        ).count()
        attrs['attempt_number'] = existing_attempts + 1

        return attrs

    def _grade_answer(self, question, selected_answer):
        """
        Grade a single answer based on question type.
        Returns (is_correct, points_awarded).
        """
        answer_payload = question.answer_payload or {}
        question_type = question.question_type
        points = question.points

        if question_type == QuizQuestion.QuestionType.MULTIPLE_CHOICE:
            selected_option = selected_answer.get('selected_option')
            options = answer_payload.get('options', [])
            if selected_option is not None and selected_option < len(options):
                is_correct = options[selected_option].get('is_correct', False)
                return is_correct, points if is_correct else 0
            return False, 0

        elif question_type == QuizQuestion.QuestionType.TRUE_FALSE:
            correct_answer = answer_payload.get('correct_answer')
            is_correct = selected_answer.get('value') == correct_answer
            return is_correct, points if is_correct else 0

        elif question_type == QuizQuestion.QuestionType.SHORT_ANSWER:
            sample_answer = answer_payload.get('sample_answer', '').lower().strip()
            user_answer = selected_answer.get('text', '').lower().strip()
            is_correct = user_answer == sample_answer or sample_answer in user_answer
            return is_correct, points if is_correct else 0

        elif question_type == QuizQuestion.QuestionType.FILL_BLANK:
            blanks = answer_payload.get('blanks', [])
            user_blanks = selected_answer.get('blanks', [])
            if len(user_blanks) != len(blanks):
                return False, 0
            correct_count = 0
            for i, blank in enumerate(blanks):
                if i < len(user_blanks):
                    if user_blanks[i].lower().strip() == blank.get('answer', '').lower().strip():
                        correct_count += 1
            total_blanks = len(blanks)
            if total_blanks > 0:
                is_correct = correct_count == total_blanks
                points_awarded = (points * correct_count) // total_blanks
                return is_correct, points_awarded
            return False, 0

        elif question_type == QuizQuestion.QuestionType.MATCHING:
            correct_pairs = answer_payload.get('pairs', [])
            user_pairs = selected_answer.get('pairs', [])
            correct_count = 0
            for pair in correct_pairs:
                for user_pair in user_pairs:
                    if pair.get('key') == user_pair.get('key'):
                        if pair.get('value') == user_pair.get('value'):
                            correct_count += 1
            total_pairs = len(correct_pairs)
            if total_pairs > 0:
                is_correct = correct_count == total_pairs
                points_awarded = (points * correct_count) // total_pairs
                return is_correct, points_awarded
            return False, 0

        elif question_type == QuizQuestion.QuestionType.ESSAY:
            return None, 0

        return False, 0

    def create(self, validated_data):
        enrollment = validated_data['enrollment']
        quiz = validated_data['quiz']
        time_spent_seconds = validated_data.get('time_spent_seconds', 0)
        answers_data = validated_data['answers']
        attempt_number = validated_data['attempt_number']

        questions = {q.id: q for q in quiz.questions.all()}
        total_points = sum(q.points for q in questions.values())
        total_score = 0

        submission = QuizSubmission.objects.create(
            enrollment=enrollment,
            quiz=quiz,
            attempt_number=attempt_number,
            max_score=total_points,
            time_spent_seconds=time_spent_seconds,
        )

        settings = quiz.settings or {}
        passing_score_percent = settings.get('passing_score_percent', 70)

        for answer_data in answers_data:
            question_id = answer_data['question']
            selected_answer = answer_data['selected_answer']

            question = questions.get(question_id)
            if not question:
                continue

            is_correct, points_awarded = self._grade_answer(question, selected_answer)

            QuizAnswer.objects.create(
                submission=submission,
                question=question,
                selected_answer=selected_answer,
                is_correct=is_correct,
                points_awarded=points_awarded
            )

            total_score += points_awarded

        submission.score = total_score
        submission.passed = (total_score / total_points * 100) >= passing_score_percent if total_points > 0 else False
        submission.save()

        return submission


class SavedCourseSerializer(serializers.ModelSerializer):
    """Serializer for SavedCourse model — used in saved courses list."""
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_thumbnail = serializers.CharField(source='course.thumbnail', read_only=True)
    course_slug = serializers.CharField(source='course.slug', read_only=True)
    course_price = serializers.DecimalField(source='course.price', max_digits=10, decimal_places=2, read_only=True)
    course_level = serializers.CharField(source='course.level', read_only=True)
    instructor_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = SavedCourse
        fields = [
            'id', 'user', 'course', 'course_title', 'course_thumbnail',
            'course_slug', 'course_price', 'course_level',
            'instructor_name', 'category_name', 'created_at',
        ]
        read_only_fields = ['id', 'user', 'created_at']

    def get_instructor_name(self, obj):
        inst = obj.course.instructor
        return inst.get_full_name() or inst.email if inst else None

    def get_category_name(self, obj):
        return obj.course.category.name if obj.course.category else None
