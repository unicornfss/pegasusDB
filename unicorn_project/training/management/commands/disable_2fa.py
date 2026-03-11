from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from unicorn_project.training.models import Personnel

class Command(BaseCommand):
    help = 'Disable 2FA for a specific user'

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
        
        # Check if 2FA is enabled
        if not personnel.totp_secret:
            self.stdout.write(
                self.style.WARNING(f'2FA is already disabled for user "{user.username}".')
            )
            return
        
        # Disable 2FA
        personnel.totp_secret = None
        personnel.save(update_fields=['totp_secret'])
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully disabled 2FA for user "{user.username}" ({personnel.email}).')
        )