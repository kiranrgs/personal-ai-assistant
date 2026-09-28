"""Morning briefing: fuses today's email digest, upcoming calendar events,
and (if configured) local weather into a single message instead of separate
pings for each. Weather uses Open-Meteo (no API key needed, just
coordinates) given BRIEFING_LATITUDE/BRIEFING_LONGITUDE.
"""
from __future__ import annotations

from typing import Any

import requests

from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.integrations.calendar_.google_calendar import list_upcoming_events
from src.integrations.email.gmail import summarize_todays_emails


def _weather_line() -> str:
    settings = get_settings()
    if not (settings.briefing_latitude and settings.briefing_longitude):
        return ""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": settings.briefing_latitude,
                "longitude": settings.briefing_longitude,
                "current": "temperature_2m,weather_code",
                "temperature_unit": "fahrenheit",
            },
            timeout=10,
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})
        if "temperature_2m" not in current:
            return ""
        return f"{current['temperature_2m']}°F (weather code {current.get('weather_code')})"
    except Exception:  # noqa: BLE001
        return ""


def generate_daily_briefing() -> dict[str, Any]:
    sections: list[str] = []

    try:
        email = summarize_todays_emails()
        if email.get("summary"):
            sections.append(f"📧 Email:\n{email['summary']}")
    except Exception:  # noqa: BLE001
        pass

    try:
        events = list_upcoming_events(days_ahead=1)
        if events.get("count"):
            lines = "\n".join(f"- {e['start']}: {e['summary']}" for e in events["events"])
            sections.append(f"📅 Today's calendar:\n{lines}")
        else:
            sections.append("📅 Today's calendar: nothing scheduled.")
    except Exception:  # noqa: BLE001
        pass

    weather = _weather_line()
    if weather:
        sections.append(f"☀️ Weather: {weather}")

    if not sections:
        return {"briefing": "Nothing to report - no integrations configured yet for the daily briefing."}
    return {"briefing": "\n\n".join(sections)}


register(Tool(
    name="generate_daily_briefing",
    description="Generate a combined morning briefing: today's email summary, today's calendar events, and weather if configured.",
    parameters={"type": "object", "properties": {}},
    handler=generate_daily_briefing,
))
