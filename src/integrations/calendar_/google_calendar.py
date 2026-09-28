"""Google Calendar integration: list/create events, across every account
label in GOOGLE_ACCOUNTS. Shares OAuth plumbing with Gmail/Drive/Sheets.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from googleapiclient.discovery import build

from src.core.google_oauth import get_google_credentials
from src.core.settings import get_settings
from src.core.tool_registry import Tool, register

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _service(account: Optional[str]):
    settings = get_settings()
    labels = settings.google_account_labels
    label = account or (labels[0] if labels else "default")
    creds = get_google_credentials(f"calendar_{label}", SCOPES)
    return build("calendar", "v3", credentials=creds)


def list_upcoming_events(account: Optional[str] = None, days_ahead: int = 7) -> dict[str, Any]:
    service = _service(account)
    now = dt.datetime.utcnow().isoformat() + "Z"
    end = (dt.datetime.utcnow() + dt.timedelta(days=days_ahead)).isoformat() + "Z"
    result = service.events().list(
        calendarId="primary", timeMin=now, timeMax=end, singleEvents=True, orderBy="startTime", maxResults=50
    ).execute()
    events = [
        {
            "id": e["id"],
            "summary": e.get("summary", "(no title)"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "location": e.get("location", ""),
        }
        for e in result.get("items", [])
    ]
    return {"count": len(events), "events": events}


def create_event(
    title: str,
    start_iso: str,
    end_iso: str,
    account: Optional[str] = None,
    location: str = "",
    description: str = "",
) -> dict[str, Any]:
    service = _service(account)
    body = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    created = service.events().insert(calendarId="primary", body=body).execute()
    return {"id": created["id"], "htmlLink": created.get("htmlLink", "")}


register(Tool(
    name="list_upcoming_calendar_events",
    description="List upcoming Google Calendar events for an account label within the next N days.",
    parameters={
        "type": "object",
        "properties": {
            "account": {"type": "string", "description": "Google account label"},
            "days_ahead": {"type": "integer", "description": "How many days ahead to look (default 7)"},
        },
    },
    handler=list_upcoming_events,
))

register(Tool(
    name="create_calendar_event",
    description="Create a Google Calendar event (direct action, not a purchase/payment, so no confirmation needed).",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start_iso": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-10-01T09:00:00-07:00"},
            "end_iso": {"type": "string", "description": "ISO 8601 datetime"},
            "account": {"type": "string", "description": "Google account label"},
            "location": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["title", "start_iso", "end_iso"],
    },
    handler=create_event,
))
