"""Shared Google OAuth helper, reused by Gmail, Google Calendar, Drive, and
Sheets. Supports multiple accounts via a `label` (e.g. "personal", "work"),
each with its own cached token file under GOOGLE_TOKEN_DIR.

One-time setup: create an OAuth client (type "Desktop app") in Google Cloud
Console, enable the Gmail/Calendar/Drive/Sheets APIs, download the client
secret JSON to the path in GOOGLE_OAUTH_CLIENT_SECRETS_FILE. The first call
per label opens a browser consent window; the resulting token is cached and
refreshed automatically after that.
"""
from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.core.settings import get_settings

log = logging.getLogger(__name__)


def get_google_credentials(label: str, scopes: list[str]) -> Credentials:
    settings = get_settings()
    token_dir = Path(settings.google_token_dir)
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / f"{label}.json"

    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        return creds

    secrets_file = Path(settings.google_oauth_client_secrets_file)
    if not secrets_file.exists():
        raise RuntimeError(
            f"Google OAuth client secrets file not found at {secrets_file}. "
            "Create an OAuth client in Google Cloud Console and set "
            "GOOGLE_OAUTH_CLIENT_SECRETS_FILE in .env."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), scopes)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    log.info("Stored new Google token for label '%s' at %s", label, token_path)
    return creds
