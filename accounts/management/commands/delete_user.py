"""
Management command to delete users by username or email.

Usage:
    python manage.py delete_user --username <username>
    python manage.py delete_user --email <email>
    python manage.py delete_user --username <username> --no-input  # Skip confirmation
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = 'Delete a user by username or email'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Delete user by username',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Delete user by email',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        email = options.get('email')
        no_input = options.get('no_input', False)

        if not username and not email:
            raise CommandError('You must provide either --username or --email')

        if username and email:
            raise CommandError('Provide either --username or --email, not both')

        try:
            if username:
                user = User.objects.get(username=username)
            else:
                user = User.objects.get(email=email.lower())

            # Show user info
            self.stdout.write(f'\nUser found:')
            self.stdout.write(f'  Username: {user.username}')
            self.stdout.write(f'  Email: {user.email}')
            self.stdout.write(f'  Is Superuser: {user.is_superuser}')
            self.stdout.write(f'  Is Staff: {user.is_staff}')
            self.stdout.write(f'  Is Active: {user.is_active}')
            self.stdout.write(f'  Date Joined: {user.date_joined}')

            # Confirmation
            if not no_input:
                confirm = input(f'\nDelete this user? [y/N]: ')
                if confirm.lower() != 'y':
                    self.stdout.write(self.style.WARNING('Cancelled.'))
                    return

            # Delete user (CASCADE will handle related objects)
            with transaction.atomic():
                user_email = user.email
                user_username = user.username
                user.delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully deleted user: {user_username} ({user_email})'
                )
            )

        except User.DoesNotExist:
            identifier = username or email
            raise CommandError(f'User with {"username" if username else "email"} "{identifier}" not found.')
