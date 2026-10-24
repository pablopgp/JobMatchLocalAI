import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from jobmatch.config import home

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def save_token(credentials):
    import win32crypt

    protected = win32crypt.CryptProtectData(
        credentials.to_json().encode(), "JobMatch Gmail", None, None, None, 0
    )
    path = home() / "token.dpapi"
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(protected)
    temporary.replace(path)


def credentials():
    import win32crypt

    path = home() / "token.dpapi"
    if not path.exists():
        raise RuntimeError("Gmail authorization is missing. Run: jobmatch authorize")
    raw = win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 0)[1]
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_token(creds)
    if not creds.valid:
        raise RuntimeError("Gmail authorization expired. Run: jobmatch authorize")
    return creds


def authorize():
    path = home() / "credentials.json"
    if not path.exists():
        raise RuntimeError(f"Place your Desktop OAuth client JSON at {path}")
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    save_token(
        flow.run_local_server(
            host="127.0.0.1", port=0, access_type="offline", prompt="consent"
        )
    )


def service():
    return build("gmail", "v1", credentials=credentials(), cache_discovery=False)


def message_ids(api, query):
    token = None
    while True:
        result = (
            api.users()
            .messages()
            .list(userId="me", q=query, pageToken=token, maxResults=500)
            .execute(num_retries=3)
        )
        yield from (item["id"] for item in result.get("messages", []))
        token = result.get("nextPageToken")
        if not token:
            break
