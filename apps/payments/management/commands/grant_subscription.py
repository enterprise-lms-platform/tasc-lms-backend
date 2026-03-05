"""
Grant a UserSubscription to a user for local testing without Flutterwave.

Usage:
  python manage.py grant_subscription --email learner@example.com --days 180
  python manage.py grant_subscription --email learner@example.com --months 6
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from apps.payments.models import Subscription, UserSubscription

User = get_user_model()


class Command(BaseCommand):
    help = "Grant an active subscription to a user (for local testing without payments)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            required=True,
            help="User email to grant subscription to",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--days", type=int, help="Subscription duration in days")
        group.add_argument("--months", type=int, help="Subscription duration in months")

    def handle(self, *args, **options):
        email = options["email"].strip()
        if not email:
            raise CommandError("--email is required")

        if options.get("months"):
            days = options["months"] * 30
        else:
            days = options["days"]

        if days <= 0:
            raise CommandError("Duration must be positive")

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f"User with email '{email}' not found")

        # Get or create a default subscription plan
        plan = Subscription.objects.filter(status=Subscription.Status.ACTIVE).first()
        if not plan:
            plan = Subscription.objects.create(
                name="6-Month Access (Test)",
                description="Default plan for local testing. Grants 6 months access to all courses.",
                price=Decimal("0.00"),
                currency="USD",
                billing_cycle="yearly",
                status=Subscription.Status.ACTIVE,
            )
            self.stdout.write(
                self.style.WARNING(
                    f"Created default plan '{plan.name}' (id={plan.id}). No active plans existed."
                )
            )

        now = timezone.now()
        end_date = now + timedelta(days=days)

        us, created = UserSubscription.objects.update_or_create(
            user=user,
            subscription=plan,
            organization=None,
            defaults={
                "status": UserSubscription.Status.ACTIVE,
                "start_date": now,
                "end_date": end_date,
                "price": plan.price,
                "currency": plan.currency,
                "auto_renew": False,
                "cancelled_at": None,
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Granted subscription to {user.email} until {end_date.date()} ({days} days)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated subscription for {user.email} until {end_date.date()} ({days} days)"
                )
            )
