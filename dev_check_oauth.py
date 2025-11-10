from django.conf import settings
from unicorn_project.training.google_oauth import get_drive_service

print("CLIENT:", settings.GOOGLE_OAUTH_CLIENT_SECRET)
print("TOKEN :", settings.GOOGLE_OAUTH_TOKEN)

svc = get_drive_service(
    settings.GOOGLE_OAUTH_CLIENT_SECRET,
    settings.GOOGLE_OAUTH_TOKEN
)
print("OK, service built.")
