# unicorn_project/training/google_oauth.py
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pathlib, sys, logging

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

def get_drive_service(client_secret_path: str, token_path: str):
    token_file = pathlib.Path(token_path)
    token_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info(f"[Drive OAuth] Using client_secret={client_secret_path}")
    logging.info(f"[Drive OAuth] Using token file={token_file}")

    creds = None

    # 1) Load existing token if present
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as e:
            logging.exception(f"[Drive OAuth] Failed to load token.json, will re-auth: {e}")
            creds = None

    # 2) Refresh or run consent
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.info("[Drive OAuth] Refreshing token…")
            creds.refresh(Request())
            token_file.write_text(creds.to_json())   # <-- WRITE AFTER REFRESH
            logging.info("[Drive OAuth] Token refreshed and saved.")
        else:
            logging.info("[Drive OAuth] Running local OAuth flow to obtain token…")
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            try:
                creds = flow.run_local_server(port=0)  # opens browser (DEV)
            except Exception:
                # headless fallback (PROD)
                auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
                logging.error("Authorize this app by visiting this URL:\n%s", auth_url)
                if sys.stdin.isatty():
                    code = input("Enter the authorization code: ")
                    creds = flow.fetch_token(code=code)
                else:
                    raise Exception("Manual authorization required. Run locally once to generate token.json")

            token_file.write_text(creds.to_json())   # <-- WRITE AFTER FIRST AUTH
            logging.info("[Drive OAuth] Token created and saved.")

    return build("drive", "v3", credentials=creds, cache_discovery=False)
