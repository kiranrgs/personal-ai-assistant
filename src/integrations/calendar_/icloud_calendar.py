"""iCloud Calendar via CalDAV, using the same app-specific password as
icloud_yahoo_imap.py (appleid.apple.com -> Sign-In and Security ->
App-Specific Passwords). No official REST API exists for iCloud Calendar;
CalDAV is Apple's own supported protocol for this.
"""
from __future__ import annotations

import os
from typing import Any

import caldav

from src.core.tool_registry import Tool, register

ICLOUD_CALDAV_URL = "https://caldav.icloud.com"


def _client(account: str) -> caldav.DAVClient:
    email_addr = os.environ.get(f"ICLOUD_{account.upper()}_EMAIL", "")
    password = os.environ.get(f"ICLOUD_{account.upper()}_APP_PASSWORD", "")
    if not email_addr or not password:
        raise RuntimeError(f"Missing ICLOUD_{account.upper()}_EMAIL/APP_PASSWORD in .env")
    return caldav.DAVClient(url=ICLOUD_CALDAV_URL, username=email_addr, password=password)


def list_icloud_events(account: str, days_ahead: int = 7) -> dict[str, Any]:
    import datetime as dt

    client = _client(account)
    principal = client.principal()
    events: list[dict[str, str]] = []
    start = dt.datetime.now()
    end = start + dt.timedelta(days=days_ahead)
    for calendar in principal.calendars():
        for event in calendar.date_search(start=start, end=end):
            vevent = event.vobject_instance.vevent
            events.append({
                "summary": str(getattr(vevent, "summary", "(no title)").value) if hasattr(vevent, "summary") else "(no title)",
                "start": str(vevent.dtstart.value) if hasattr(vevent, "dtstart") else "",
                "calendar": calendar.name,
            })
    return {"count": len(events), "events": events}


register(Tool(
    name="list_icloud_calendar_events",
    description="List upcoming iCloud Calendar events for the given account label within the next N days.",
    parameters={
        "type": "object",
        "properties": {
            "account": {"type": "string", "description": "The account label from ICLOUD_ACCOUNTS"},
            "days_ahead": {"type": "integer"},
        },
        "required": ["account"],
    },
    handler=list_icloud_events,
))
