"""
Management command to cleanup old email verification logs for GDPR compliance.
Run this command periodically (e.g., via cron) to enforce data retention policy.
"""
from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError
from accounts.models import EmailVerificationLog


class Command(BaseCommand):
    help = 'Delete email verification logs older than 365 days (GDPR data retention)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Number of days to retain logs (default: 365)',
        )

    def handle(self, *args, **options):
        days = options['days']
        
        try:
            deleted_count = EmailVerificationLog.cleanup_old_logs(days=days)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully deleted {deleted_count} verification log(s) older than {days} days.'
                )
            )
        except (OperationalError, ProgrammingError) as e:
            # Check if it's a database table doesn't exist error
            error_msg = str(e)
            if 'does not exist' in error_msg or 'relation' in error_msg.lower():
                self.stdout.write(
                    self.style.ERROR(
                        f'Database tables do not exist. Please run migrations first:\n'
                        f'  python manage.py migrate'
                    )
                )
            else:
                # Re-raise other database errors
                raise
