from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Show available 2FA recovery commands and usage'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('2FA Recovery Commands')
        )
        self.stdout.write('=' * 50)
        self.stdout.write('')
        
        self.stdout.write(
            self.style.WARNING('DISABLE 2FA FOR A USER:')
        )
        self.stdout.write('python manage.py disable_2fa <username_or_email>')
        self.stdout.write('Example: python manage.py disable_2fa admin@example.com')
        self.stdout.write('This removes the 2FA requirement so the user can log in normally.')
        self.stdout.write('')
        
        self.stdout.write(
            self.style.WARNING('RESET PASSWORD FOR A USER:')
        )
        self.stdout.write('python manage.py reset_password <username_or_email>')
        self.stdout.write('Example: python manage.py reset_password admin@example.com')
        self.stdout.write('This generates a new temporary password and emails it to the user.')
        self.stdout.write('The user will be required to change the password on first login.')
        self.stdout.write('')
        
        self.stdout.write(
            self.style.WARNING('WHEN TO USE:')
        )
        self.stdout.write('- disable_2fa: When a user has lost access to their authenticator app')
        self.stdout.write('- reset_password: When a user has forgotten their password')
        self.stdout.write('- Both can be used together if needed')
        self.stdout.write('')
        
        self.stdout.write(
            self.style.WARNING('SECURITY NOTES:')
        )
        self.stdout.write('- These commands should only be run by trusted administrators')
        self.stdout.write('- Always verify the user identity before running these commands')
        self.stdout.write('- Check server logs for command usage')
        self.stdout.write('')
        
        self.stdout.write(
            self.style.SUCCESS('For admin UI access, use the Django admin interface at /admin/')
        )