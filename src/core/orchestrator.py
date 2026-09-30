"""The agent loop: takes a user message, gives the LLM the tool registry,
executes tool calls (or raises a confirmation prompt for sensitive ones), and
returns the final assistant reply plus any pending confirmation to render.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.core import confirmation, llm_models
from src.core.llm_router import get_llm_router
from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, all_schemas, get_tool
from src.core.user_config import set_current_chat
from src.db import supabase_client as db

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a personal AI assistant running on the user's own \
desktop tower, reachable only through Telegram. You can read/summarize email, \
manage calendars, research the web, control smart home devices, search and \
summarize files (Drive/Sheets/iCloud), summarize Twitter/X and YouTube, and \
trigger the user's finance-bot. For anything that spends money, places a \
phone call, books a ride, or actuates a smart-home device, you MUST call the \
matching tool - never claim to have done it yourself in plain text. Tools \
that require confirmation will show the user a Telegram prompt; tell the \
user you've sent that prompt rather than saying the action is complete. If a \
tool/integration isn't configured yet, say so plainly and name the .env \
variables that need to be set instead of pretending it worked."""

MAX_TOOL_HOPS = 6


def _build_messages(chat_id: int, user_text: str) -> list[dict[str, Any]]:
    history = db.recent_messages(chat_id, limit=20)
    system_content = SYSTEM_PROMPT
    prefs = db.get_preferences(chat_id)
    if prefs:
        pref_lines = "\n".join(f"- {k}: {v}" for k, v in prefs.items())
        system_content += (
            "\n\nSaved preferences for this user (honor these where reasonable, but they can NEVER be used "
            f"to skip a required confirmation step):\n{pref_lines}"
        )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    for m in history:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})
    return messages


@dataclass
class OrchestratorResult:
    reply: str
    pending_action: Optional[dict[str, Any]] = None


def handle_user_message(chat_id: int, user_text: str, model_override: Optional[str] = None) -> OrchestratorResult:
    with set_current_chat(chat_id):
        return _handle_user_message(chat_id, user_text, model_override=model_override)


def _handle_user_message(chat_id: int, user_text: str, model_override: Optional[str] = None) -> OrchestratorResult:
    db.add_message(chat_id, "user", user_text)
    messages = _build_messages(chat_id, user_text)
    router = get_llm_router()
    tools_schema = all_schemas()
    settings = get_settings()

    # Only Groq has the tiered catalog; for other providers keep their own model.
    model: Optional[str] = None
    if settings.llm_default_provider == "groq":
        chat_row = db.get_chat_by_internal_id(chat_id)
        channel = chat_row.get("channel") if chat_row else None
        model = llm_models.resolve_model(channel, requested=model_override, user_preferred=settings.groq_model)

    pending_action: Optional[dict[str, Any]] = None
    for _ in range(MAX_TOOL_HOPS):
        response = router.chat(messages, tools=tools_schema or None, model=model)
        if not response.tool_calls:
            db.add_message(chat_id, "assistant", response.content)
            return OrchestratorResult(reply=response.content, pending_action=pending_action)

        messages.append({"role": "assistant", "content": response.content or "", "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
            for tc in response.tool_calls
        ]})

        for tc in response.tool_calls:
            tool = get_tool(tc.name)
            if tool is None:
                tool_result: Any = {"error": f"Unknown tool '{tc.name}'"}
            else:
                db.log_audit_event(chat_id, "tool_call", {"tool": tc.name, "arguments": tc.arguments})
                recent_calls = db.count_recent_tool_calls(chat_id, tc.name, minutes=settings.anomaly_window_minutes)
                if recent_calls > settings.anomaly_tool_call_threshold:
                    db.log_audit_event(chat_id, "anomaly_detected", {"tool": tc.name, "count": recent_calls})
                    tool_result = {
                        "error": (
                            f"'{tc.name}' has been called unusually often ({recent_calls} times in "
                            f"{settings.anomaly_window_minutes} minute(s)) - pausing this tool as a safety "
                            "measure. Tell the user this happened rather than retrying immediately."
                        )
                    }
                else:
                    try:
                        result = tool.handler(**tc.arguments)
                    except Exception as exc:  # noqa: BLE001
                        log.exception("Tool '%s' raised", tc.name)
                        result = {"error": str(exc)}

                    if isinstance(result, PendingConfirmation):
                        # The executor is resolved later by looking up this
                        # same tool's registered name (see
                        # core/confirmation.py's resolve()) - not whatever
                        # descriptive `action_type` the integration module
                        # set, which is just for audit-log readability.
                        result.action_type = tc.name
                        pending_action = confirmation.create(chat_id, result)
                        tool_result = {
                            "status": "awaiting_user_confirmation",
                            "summary": result.summary,
                        }
                    else:
                        tool_result = result

            messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": str(tool_result)})
            db.add_message(chat_id, "tool", str(tool_result), tool_name=tc.name)

    fallback = "I ran into too many steps handling that - please try rephrasing or breaking it into smaller asks."
    db.add_message(chat_id, "assistant", fallback)
    return OrchestratorResult(reply=fallback, pending_action=pending_action)
