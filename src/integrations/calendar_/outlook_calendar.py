"""Microsoft 365/Outlook Calendar via Microsoft Graph, reusing the device-code
token flow from `integrations.email.outlook`.
"""
from __future__ import annotations

from typing import Any

import requests

from src.core.tool_registry import Tool, register
from src.integrations.email.outlook import GRAPH_BASE, _get_token, _is_configured


def list_outlook_events(account: str, days_ahead: int = 7) -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Outlook isn't configured yet. Set MS_CLIENT_ID in .env."}
    import datetime as dt

    token = _get_token(account)
    now = dt.datetime.utcnow()
    end = now + dt.timedelta(days=days_ahead)
    resp = requests.get(
        f"{GRAPH_BASE}/me/calendarview",
        headers={"Authorization": f"Bearer {token}"},
        params={"startDateTime": now.isoformat() + "Z", "endDateTime": end.isoformat() + "Z", "$select": "subject,start,end,location"},
        timeout=30,
    )
    resp.raise_for_status()
    events = [
        {"summary": e.get("subject", ""), "start": e["start"]["dateTime"], "end": e["end"]["dateTime"], "location": e.get("location", {}).get("displayName", "")}
        for e in resp.json().get("value", [])
    ]
    return {"count": len(events), "events": events}


register(Tool(
    name="list_outlook_calendar_events",
    description="List upcoming Microsoft 365/Outlook Calendar events for the given account label.",
    parameters={
        "type": "object",
        "properties": {"account": {"type": "string"}, "days_ahead": {"type": "integer"}},
        "required": ["account"],
    },
    handler=list_outlook_events,
))
