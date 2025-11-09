# unicorn_project/training/google_oauth.py
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pathlib

SCOPES = ["https://www.googleapis.com/auth/drive"]

def get_drive_service(client_secret_path: str, token_path: str):
    token_file = pathlib.Path(token_path)
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
        else:
            # Do this once in each environment, then token.json is reused
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)
