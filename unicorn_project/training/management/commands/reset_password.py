from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from unicorn_project.training.models import Personnel
from unicorn_project.training.utils.passwords import send_initial_password_email

class Command(BaseCommand):
    help = 'Reset password for a specific user and send email'

    def add_arguments(self, parser):
        parser.add_argument(
            'identifier',
            type=str,
            help='Username or email address of the user',
        )

    def handle(self, *args, **options):
        identifier = options['identifier']
        
        # Try to find user by username first, then by email
        User = get_user_model()
        try:
            user = User.objects.get(username=identifier)
        except User.DoesNotExist:
            try:
                personnel = Personnel.objects.select_related('user').get(email=identifier)
                user = personnel.user
            except Personnel.DoesNotExist:
                raise CommandError(f'User with username or email "{identifier}" not found.')
        
        # Get the personnel record
        try:
            personnel = user.personnel
        except Personnel.DoesNotExist:
            raise CommandError(f'No personnel record found for user "{user.username}".')
        
        # Generate new password
        temp_password = get_random_string(12)
        
        # Set the new password
        user.set_password(temp_password)
        user.is_active = True
        user.save(update_fields=['password', 'is_active'])
        
        # Set must_change_password flag
        personnel.must_change_password = True
        personnel.save(update_fields=['must_change_password'])
        
        # Send email
        send_initial_password_email(personnel, temp_password)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully reset password for user "{user.username}" ({personnel.email}). '
                f'A temporary password has been emailed to {personnel.email}.'
            )
        )