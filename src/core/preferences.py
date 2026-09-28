"""Per-chat preference storage - purely used to shape tone/proactivity
(e.g. "keep replies brief", "default Google account is work"). This can
NEVER be used to bypass the hard confirm-before-execute rule for
money/calls/smart-home actuation - that's enforced in code (see
core/tool_registry.py, core/confirmation.py), not by LLM-honored preference
text, so a preference asking to skip confirmation is simply not something
any tool here is capable of doing.
"""
from __future__ import annotations

from typing import Any

from src.core.tool_registry import Tool, register
from src.core.user_config import get_current_chat
from src.db import supabase_client as db


def set_preference(key: str, value: str) -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "Couldn't determine which chat this is."}
    db.set_preference(chat_id, key, value)
    return {"status": "saved", "key": key, "value": value}


def get_preferences() -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "Couldn't determine which chat this is."}
    return {"preferences": db.get_preferences(chat_id)}


register(Tool(
    name="set_preference",
    description=(
        "Remember a personal preference for this chat for future replies (e.g. tone, default account, "
        "recurring instructions). Cannot be used to skip a required confirmation step."
    ),
    parameters={
        "type": "object",
        "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
        "required": ["key", "value"],
    },
    handler=set_preference,
))

register(Tool(
    name="get_preferences",
    description="List all saved preferences for this chat.",
    parameters={"type": "object", "properties": {}},
    handler=get_preferences,
))
