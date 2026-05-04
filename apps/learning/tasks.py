"""
Celery tasks for learning app.
"""
import csv
import io
import logging
from django.db import models
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def generate_report(self, report_id):
    """
    Generate report asynchronously.
    """
    from apps.learning.models import Report, Enrollment, SessionProgress, Certificate
    from apps.payments.models import Transaction, Invoice

    try:
        report = Report.objects.get(id=report_id)
    except Report.DoesNotExist:
        logger.error(f"Report {report_id} not found")
        return

    report_type = report.report_type
    parameters = report.parameters or {}

    try:
        csv_data = _generate_csv_data(report_type, parameters)
        
        buffer = io.StringIO()
        buffer.write(csv_data)
        buffer.seek(0)

        from django.core.files.base import ContentFile
        report.file.save(
            f"report_{report.id}_{report_type}.csv",
            ContentFile(buffer.read().encode('utf-8')),
            save=True
        )
        
        if report.file:
            report.file_size = f"{report.file.size / 1024:.1f} KB"
        
        report.status = Report.Status.READY
        report.save()
        
        logger.info(f"Report {report_id} generated successfully")
        
    except Exception as e:
        logger.error(f"Error generating report {report_id}: {str(e)}")
        report.status = Report.Status.FAILED
        report.save()


def _generate_csv_data(report_type, parameters):
    """
    Generate CSV data based on report type.
    """
    from apps.learning.models import Enrollment, SessionProgress, Certificate
    from apps.payments.models import Transaction, Invoice
    from django.db.models import Count, Avg, F
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    date_from = parameters.get('date_from')
    date_to = parameters.get('date_to')
    
    if report_type == Report.Type.USER_ACTIVITY:
        writer.writerow(['User Name', 'Email', 'Course', 'Session', 'Time Spent (min)', 'Last Accessed', 'Completion %'])
        
        enrollments = Enrollment.objects.select_related('user', 'course').all()
        
        progress_data = SessionProgress.objects.select_related(
            'enrollment__user', 'enrollment__course', 'session'
        ).all()
        
        user_sessions = {}
        for sp in progress_data:
            user_email = sp.enrollment.user.email
            user_name = sp.enrollment.user.get_full_name() or user_email
            course_title = sp.enrollment.course.title
            session_title = sp.session.title if sp.session else 'N/A'
            time_spent = (sp.time_spent_seconds or 0) / 60
            last_accessed = sp.last_accessed_at.strftime('%Y-%m-%d %H:%M') if sp.last_accessed_at else 'N/A'
            completion = sp.progress_percentage or 0
            
            key = (user_email, course_title, session_title)
            if key not in user_sessions:
                user_sessions[key] = {
                    'user_name': user_name,
                    'course': course_title,
                    'session': session_title,
                    'time_spent': time_spent,
                    'last_accessed': last_accessed,
                    'completion': completion
                }
        
        for (user_email, course, session), data in user_sessions.items():
            writer.writerow([
                data['user_name'],
                user_email,
                data['course'],
                data['session'],
                f"{data['time_spent']:.1f}",
                data['last_accessed'],
                f"{data['completion']:.1f}%"
            ])
    
    elif report_type == Report.Type.COURSE_PERFORMANCE:
        writer.writerow(['Course Name', 'Enrolled Count', 'Completed Count', 'Avg Score', 'Avg Completion %'])
        
        from apps.catalogue.models import Course
        courses = Course.objects.annotate(
            enrolled_count=Count('enrollments'),
            completed_count=Count('enrollments', filter=models.Q(enrollments__status=Enrollment.Status.COMPLETED)),
            avg_score=Avg('enrollments__progress_percentage')
        )
        
        for course in courses:
            writer.writerow([
                course.title,
                course.enrolled_count,
                course.completed_count,
                f"{course.avg_score or 0:.1f}%",
                f"{course.avg_score or 0:.1f}%"
            ])
    
    elif report_type == Report.Type.ENROLLMENT:
        writer.writerow(['Learner Name', 'Email', 'Course', 'Enrolled At', 'Status', 'Completion %'])
        
        enrollments = Enrollment.objects.select_related('user', 'course').order_by('-enrolled_at')
        
        for e in enrollments:
            writer.writerow([
                e.user.get_full_name() or e.user.email,
                e.user.email,
                e.course.title,
                e.enrolled_at.strftime('%Y-%m-%d'),
                e.status,
                f"{e.progress_percentage}%"
            ])
    
    elif report_type == Report.Type.COMPLETION:
        writer.writerow(['Learner Name', 'Course', 'Completed At', 'Score', 'Certificate Issued'])
        
        enrollments = Enrollment.objects.filter(
            status=Enrollment.Status.COMPLETED
        ).select_related('user', 'course').order_by('-completed_at')
        
        for e in enrollments:
            writer.writerow([
                e.user.get_full_name() or e.user.email,
                e.course.title,
                e.completed_at.strftime('%Y-%m-%d') if e.completed_at else 'N/A',
                f"{e.progress_percentage}%",
                'Yes' if e.certificate_issued else 'No'
            ])
    
    elif report_type == Report.Type.ASSESSMENT:
        writer.writerow(['Learner Name', 'Assessment Title', 'Type', 'Score', 'Max Score', 'Submitted At', 'Status'])
        
        from apps.learning.models import Submission
        submissions = Submission.objects.select_related(
            'enrollment__user', 'assignment__session'
        ).order_by('-submitted_at')[:100]
        
        for s in submissions:
            assignment_title = s.assignment.session.title if s.assignment and s.assignment.session else 'N/A'
            writer.writerow([
                s.enrollment.user.get_full_name() or s.enrollment.user.email,
                assignment_title,
                'Assignment',
                s.grade or 'N/A',
                s.assignment.max_points if s.assignment else 'N/A',
                s.submitted_at.strftime('%Y-%m-%d %H:%M') if s.submitted_at else 'N/A',
                s.status
            ])
    
    elif report_type == Report.Type.REVENUE:
        writer.writerow(['Transaction ID', 'Learner', 'Course', 'Amount', 'Currency', 'Payment Method', 'Date', 'Status'])
        
        transactions = Transaction.objects.select_related('user').order_by('-created_at')[:100]
        
        for t in transactions:
            writer.writerow([
                t.transaction_id,
                t.user.email if t.user else 'N/A',
                'N/A',
                f"{t.amount}",
                t.currency,
                t.payment_method or 'N/A',
                t.created_at.strftime('%Y-%m-%d %H:%M'),
                t.status
            ])
    
    elif report_type == 'transactions':
        writer.writerow(['Transaction ID', 'User Email', 'Amount', 'Currency', 'Status', 'Payment Method', 'Provider Order ID', 'Created At', 'Completed At'])
        from apps.payments.models import Payment
        for t in Payment.objects.select_related('user').order_by('-created_at')[:2000]:
            writer.writerow([
                t.id, t.user.email if t.user else 'N/A', t.amount, t.currency,
                t.status, t.payment_method or 'N/A', t.provider_order_id or '',
                t.created_at.strftime('%Y-%m-%d %H:%M'), t.completed_at.strftime('%Y-%m-%d %H:%M') if t.completed_at else '',
            ])

    elif report_type == 'invoices':
        writer.writerow(['Invoice #', 'User', 'Total Amount', 'Currency', 'Status', 'Due Date', 'Issued At'])
        from apps.payments.models import Invoice
        for inv in Invoice.objects.select_related('user').order_by('-issued_at')[:2000]:
            writer.writerow([
                inv.invoice_number, inv.user.email if inv.user else 'N/A',
                inv.total_amount, inv.currency, inv.status,
                inv.due_date.strftime('%Y-%m-%d') if inv.due_date else '',
                inv.issued_at.strftime('%Y-%m-%d') if inv.issued_at else '',
            ])

    elif report_type == 'subscriptions':
        writer.writerow(['User', 'Plan', 'Status', 'Price', 'Currency', 'Start Date', 'End Date', 'Cancelled At'])
        from apps.payments.models import UserSubscription
        for sub in UserSubscription.objects.select_related('user', 'subscription').order_by('-created_at')[:2000]:
            writer.writerow([
                sub.user.email, sub.subscription.name if sub.subscription else 'N/A',
                sub.status, sub.price, sub.currency,
                sub.start_date.strftime('%Y-%m-%d') if sub.start_date else '',
                sub.end_date.strftime('%Y-%m-%d') if sub.end_date else '',
                sub.cancelled_at.strftime('%Y-%m-%d') if sub.cancelled_at else '',
            ])

    elif report_type == 'churn':
        writer.writerow(['User', 'Plan', 'Price', 'Start Date', 'Cancelled At', 'Duration (days)'])
        from apps.payments.models import UserSubscription
        from datetime import timedelta
        for sub in UserSubscription.objects.filter(status='cancelled').select_related('user', 'subscription').order_by('-cancelled_at')[:2000]:
            if sub.start_date and sub.cancelled_at:
                duration = (sub.cancelled_at.date() - sub.start_date).days
            else:
                duration = ''
            writer.writerow([
                sub.user.email, sub.subscription.name if sub.subscription else 'N/A',
                sub.price,
                sub.start_date.strftime('%Y-%m-%d') if sub.start_date else '',
                sub.cancelled_at.strftime('%Y-%m-%d') if sub.cancelled_at else '',
                duration,
            ])

    else:
        writer.writerow(['Error', f'Unknown report type: {report_type}'])

    return output.getvalue()
