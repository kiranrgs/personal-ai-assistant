"""Microsoft 365 (Outlook) mail via Microsoft Graph. Uses MSAL device-code
auth so it works headlessly on a tower without a local browser popup being
required in the same session (falls back to opening a browser if available).

One-time setup:
  1. portal.azure.com -> App registrations -> New registration
     (Redirect URI: leave blank for device code flow; supported account
     types: "Accounts in any organizational directory and personal Microsoft
     accounts").
  2. API permissions: Mail.Read, Calendars.ReadWrite (delegated), then grant.
  3. Set MS_CLIENT_ID in .env. MS_TENANT_ID=common works for personal +
     work/school accounts.

STATUS: structure is real (MSAL + Graph), but this needs your MS_CLIENT_ID
before it will run - tools report "not configured" until then.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Optional

import msal
import requests

from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items

GRAPH_SCOPES = ["Mail.Read", "Calendars.ReadWrite"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _is_configured() -> bool:
    return bool(get_settings().ms_client_id)


def _token_cache_path(label: str) -> Path:
    settings = get_settings()
    d = Path(settings.ms_token_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{label}.json"


def _get_token(label: str) -> str:
    settings = get_settings()
    if not settings.ms_client_id:
        raise RuntimeError("MS_CLIENT_ID is not set in .env - register an app in Azure AD first.")

    cache = msal.SerializableTokenCache()
    cache_path = _token_cache_path(label)
    if cache_path.exists():
        cache.deserialize(cache_path.read_text())

    app = msal.PublicClientApplication(
        settings.ms_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
        token_cache=cache,
    )

    accounts = app.get_accounts()
    result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0]) if accounts else None
    if not result:
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to start device flow: {flow}")
        raise RuntimeError(
            f"Microsoft 365 sign-in needed for account '{label}': {flow['message']} "
            "Run this once interactively, then it will stay cached."
        )

    cache_path.write_text(cache.serialize())
    return result["access_token"]


def list_todays_outlook_emails(account: str) -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Outlook isn't configured yet. Set MS_CLIENT_ID in .env (see module docstring)."}
    token = _get_token(account)
    today = dt.date.today().isoformat()
    resp = requests.get(
        f"{GRAPH_BASE}/me/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"$filter": f"receivedDateTime ge {today}T00:00:00Z", "$select": "from,subject,bodyPreview", "$top": 50},
        timeout=30,
    )
    resp.raise_for_status()
    messages = resp.json().get("value", [])
    emails = [
        {"from": m.get("from", {}).get("emailAddress", {}).get("address", ""), "subject": m.get("subject", ""), "snippet": m.get("bodyPreview", "")}
        for m in messages
    ]
    return {"count": len(emails), "emails": emails}


def summarize_todays_outlook_emails(account: str) -> dict[str, Any]:
    result = list_todays_outlook_emails(account)
    if "error" in result:
        return result
    emails = result["emails"]
    if not emails:
        return {"summary": "No Outlook emails today."}
    items_text = "\n".join(f"- From: {e['from']} | Subject: {e['subject']} | {e['snippet']}" for e in emails)
    return {"summary": summarize_items("Outlook emails", items_text), "count": len(emails)}


register(Tool(
    name="list_todays_outlook_emails",
    description="List today's Microsoft 365/Outlook messages for the given account label.",
    parameters={"type": "object", "properties": {"account": {"type": "string"}}, "required": ["account"]},
    handler=list_todays_outlook_emails,
))

register(Tool(
    name="summarize_todays_outlook_emails",
    description="LLM-summarize today's Microsoft 365/Outlook messages for the given account label.",
    parameters={"type": "object", "properties": {"account": {"type": "string"}}, "required": ["account"]},
    handler=summarize_todays_outlook_emails,
))
