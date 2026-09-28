"""Confirm-before-execute flow for any tool that touches money, calls, or
smart-home actuation. A pending action is stored in Supabase, the caller
renders a Telegram inline-keyboard prompt, and only `resolve()` (wired to the
Confirm/Reject button callback) actually runs the tool's `executor`.
"""
from __future__ import annotations

import logging
from typing import Any

from src.core.tool_registry import PendingConfirmation, get_tool
from src.core.user_config import set_current_chat
from src.db import supabase_client as db

log = logging.getLogger(__name__)


def create(chat_id: int, pending: PendingConfirmation) -> dict[str, Any]:
    action = db.create_pending_action(chat_id, pending.action_type, pending.summary, pending.payload)
    db.log_audit_event(chat_id, "pending_action_created", {"action_id": action["id"], "action_type": pending.action_type})
    return action


def resolve(action_id: str, approved: bool) -> dict[str, Any]:
    action = db.get_pending_action(action_id)
    if action is None:
        return {"ok": False, "message": "This confirmation no longer exists."}
    if action["status"] != "pending":
        return {"ok": False, "message": f"This action was already {action['status']}."}

    if not approved:
        db.resolve_pending_action(action_id, "rejected")
        db.log_audit_event(action["chat_id"], "confirmation_rejected", {"action_id": action_id})
        return {"ok": True, "message": "Cancelled. Nothing was done."}

    tool = get_tool(action["action_type"])
    if tool is None or tool.executor is None:
        db.resolve_pending_action(action_id, "failed")
        return {"ok": False, "message": f"No executor registered for '{action['action_type']}'."}

    db.log_audit_event(action["chat_id"], "confirmation_approved", {"action_id": action_id})
    try:
        with set_current_chat(action["chat_id"]):
            result = tool.executor(action["payload"])
        db.resolve_pending_action(action_id, "executed")
        db.log_audit_event(action["chat_id"], "action_executed", {"action_id": action_id, "result": str(result)[:2000]})
        return {"ok": True, "message": result if isinstance(result, str) else "Done.", "result": result}
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, then re-raised in logs
        log.exception("Executor failed for action %s", action_id)
        db.resolve_pending_action(action_id, "failed")
        db.log_audit_event(action["chat_id"], "action_failed", {"action_id": action_id, "error": str(exc)})
        return {"ok": False, "message": f"Action failed: {exc}"}
