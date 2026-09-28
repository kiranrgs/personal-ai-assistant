"""Household presence tracking for geofencing automation.

Each household member's phone reports "home"/"away" via a Shortcuts
automation hitting the webhook server's `POST /presence/<chat_id>` endpoint
(see webhook_server.py) when it crosses a geofence around the house. When
EVERY member of a household is away, the house is put into "Away" mode via
Clare Home; when anyone is back home, it's put back to "Home" mode.

This is the one place in the whole app that actuates smart-home devices
WITHOUT a Telegram confirm step - by design, since the entire point of
geofencing is to run unattended while nobody's home to tap Confirm. It only
ever fires from the authenticated presence webhook (a shared secret, see
PRESENCE_WEBHOOK_SECRET), never from chat conversation, and every trigger is
still fully audit-logged (event types `household_auto_away`/
`household_auto_home`). See README.md's "Security model" section for the
explicit callout of this exception.
"""
from __future__ import annotations

import logging
from typing import Any

from src.core.tool_registry import Tool, register
from src.core.user_config import get_current_chat
from src.db import supabase_client as db
from src.integrations.smart_home import clare_home

log = logging.getLogger(__name__)


def report_presence(chat_id: int, state: str) -> dict[str, Any]:
    if state not in ("home", "away"):
        return {"error": "state must be 'home' or 'away'"}
    db.upsert_presence(chat_id, state)
    user = db.get_user(chat_id)
    household = user.get("household") if user else None
    if not household:
        return {"status": "presence_recorded", "household_action": "none", "household": None}

    action_taken = "none"
    if db.household_all_away(household):
        result = clare_home.trigger_scene_by_label_for_household("Away")
        db.log_audit_event(None, "household_auto_away", {"household": household, "result": result})
        action_taken = "set_away"
    elif state == "home":
        result = clare_home.trigger_scene_by_label_for_household("Home")
        db.log_audit_event(None, "household_auto_home", {"household": household, "result": result})
        action_taken = "set_home"
    return {"status": "presence_recorded", "household_action": action_taken, "household": household}


def report_my_presence(state: str) -> dict[str, Any]:
    """Convenience LLM tool: lets a user say "mark me as away" in chat
    instead of only via the geofencing webhook. This is the user reporting
    their OWN status directly (not the LLM deciding to actuate a device), so
    it's fine to expose conversationally - any resulting device actuation
    still only happens through the same auto-away/auto-home logic above."""
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "Couldn't determine which chat this is."}
    return report_presence(chat_id, state)


def list_household_presence(household: str) -> dict[str, Any]:
    members = db.list_household_members(household)
    return {"household": household, "member_chat_ids": [m["chat_id"] for m in members]}


register(Tool(
    name="report_my_presence",
    description="Manually tell the assistant you're now home or away (normally reported automatically via geofencing).",
    parameters={"type": "object", "properties": {"state": {"type": "string", "enum": ["home", "away"]}}, "required": ["state"]},
    handler=report_my_presence,
))

register(Tool(
    name="list_household_presence",
    description="List a household's members and note whether the household is currently tracked as away/home.",
    parameters={"type": "object", "properties": {"household": {"type": "string"}}, "required": ["household"]},
    handler=list_household_presence,
))
