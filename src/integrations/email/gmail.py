"""Gmail integration: list/search messages and produce LLM summaries. Works
across every label configured in GOOGLE_ACCOUNTS (e.g. "personal,work"),
sharing OAuth plumbing with Calendar/Drive/Sheets via `core.google_oauth`.

Registers tools:
  - list_todays_emails(account: str | None) -> today's inbox as plain text
  - summarize_todays_emails(account: str | None) -> LLM digest, saved as a
    context snapshot so Telegram follow-up questions can refer back to it
  - search_emails(query: str, account: str | None) -> Gmail search results
"""
from __future__ import annotations

import base64
import datetime as dt
from typing import Any, Optional

from googleapiclient.discovery import build

from src.core.google_oauth import get_google_credentials
from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _service(account: Optional[str]):
    settings = get_settings()
    labels = settings.google_account_labels
    label = account or (labels[0] if labels else "default")
    creds = get_google_credentials(f"gmail_{label}", SCOPES)
    return build("gmail", "v1", credentials=creds)


def _decode_snippet(message: dict[str, Any]) -> str:
    return message.get("snippet", "")


def _header(message: dict[str, Any], name: str) -> str:
    for h in message.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _fetch_today(account: Optional[str]) -> list[dict[str, str]]:
    service = _service(account)
    today = dt.date.today()
    query = f"after:{today.strftime('%Y/%m/%d')}"
    result = service.users().messages().list(userId="me", q=query, maxResults=50).execute()
    ids = [m["id"] for m in result.get("messages", [])]
    emails = []
    for msg_id in ids:
        msg = service.users().messages().get(userId="me", id=msg_id, format="metadata",
                                               metadataHeaders=["From", "Subject"]).execute()
        emails.append({
            "id": msg_id,
            "from": _header(msg, "From"),
            "subject": _header(msg, "Subject"),
            "snippet": _decode_snippet(msg),
        })
    return emails


def list_todays_emails(account: Optional[str] = None) -> dict[str, Any]:
    emails = _fetch_today(account)
    if not emails:
        return {"count": 0, "emails": []}
    return {"count": len(emails), "emails": emails}


def summarize_todays_emails(account: Optional[str] = None) -> dict[str, Any]:
    emails = _fetch_today(account)
    if not emails:
        return {"summary": "No emails today."}
    items_text = "\n".join(f"- From: {e['from']} | Subject: {e['subject']} | {e['snippet']}" for e in emails)
    summary = summarize_items("emails", items_text, instructions="Group by sender/topic where sensible.")
    return {"summary": summary, "count": len(emails)}


def search_emails(query: str, account: Optional[str] = None, max_results: int = 10) -> dict[str, Any]:
    service = _service(account)
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    ids = [m["id"] for m in result.get("messages", [])]
    emails = []
    for msg_id in ids:
        msg = service.users().messages().get(userId="me", id=msg_id, format="metadata",
                                               metadataHeaders=["From", "Subject"]).execute()
        emails.append({"from": _header(msg, "From"), "subject": _header(msg, "Subject"), "snippet": _decode_snippet(msg)})
    return {"count": len(emails), "emails": emails}


register(Tool(
    name="list_todays_emails",
    description="List today's Gmail messages (sender, subject, snippet) for a given account label, or the default account if omitted.",
    parameters={
        "type": "object",
        "properties": {"account": {"type": "string", "description": "Google account label, e.g. 'personal' or 'work'"}},
    },
    handler=list_todays_emails,
))

register(Tool(
    name="summarize_todays_emails",
    description="Fetch and LLM-summarize all of today's Gmail messages for a given account label (or the default account).",
    parameters={
        "type": "object",
        "properties": {"account": {"type": "string", "description": "Google account label, e.g. 'personal' or 'work'"}},
    },
    handler=summarize_todays_emails,
))

register(Tool(
    name="search_emails",
    description="Search Gmail with a query string (Gmail search syntax) and return matching messages.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail search query, e.g. 'from:alice subject:invoice'"},
            "account": {"type": "string", "description": "Google account label"},
            "max_results": {"type": "integer", "description": "Max number of results (default 10)"},
        },
        "required": ["query"],
    },
    handler=search_emails,
))
