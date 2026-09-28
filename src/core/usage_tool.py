"""LLM usage visibility: reports how many tokens this chat has used
recently. This is a usage gauge, not a precise dollar-cost audit (provider
pricing changes and Groq's free tier terms can shift) - treat the numbers as
relative/trend indicators.
"""
from __future__ import annotations

from typing import Any

from src.core.tool_registry import Tool, register
from src.core.user_config import get_current_chat
from src.db import supabase_client as db


def get_llm_usage_summary(days: int = 30) -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "Couldn't determine which chat this is."}
    return db.get_llm_usage_summary(chat_id, days)


register(Tool(
    name="get_llm_usage_summary",
    description="Show this chat's LLM token usage over the last N days, broken down by provider/model.",
    parameters={"type": "object", "properties": {"days": {"type": "integer"}}},
    handler=get_llm_usage_summary,
))
