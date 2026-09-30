"""Confirm-before-execute flow for any tool that touches money, calls, or
smart-home actuation. A pending action is stored in Supabase, the caller
renders a Telegram inline-keyboard prompt, and only `resolve()` (wired to the
Confirm/Reject button callback) actually runs the tool's `executor`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, get_tool
from src.core.user_config import set_current_chat
from src.db import supabase_client as db

log = logging.getLogger(__name__)


def create(chat_id: int, pending: PendingConfirmation) -> dict[str, Any]:
    action = db.create_pending_action(chat_id, pending.action_type, pending.summary, pending.payload)
    db.log_audit_event(chat_id, "pending_action_created", {"action_id": action["id"], "action_type": pending.action_type})
    return action


def _is_expired(action: dict[str, Any]) -> bool:
    ttl = get_settings().pending_action_ttl_minutes
    created_raw = action.get("created_at")
    if ttl <= 0 or not created_raw:
        return False
    created = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created > timedelta(minutes=ttl)


def resolve(action_id: str, approved: bool) -> dict[str, Any]:
    action = db.get_pending_action(action_id)
    if action is None:
        return {"ok": False, "message": "This confirmation no longer exists."}
    if action["status"] != "pending":
        return {"ok": False, "message": f"This action was already {action['status']}."}

    # Atomically claim it so two concurrent Confirm clicks can't both execute.
    if db.claim_pending_action(action_id) is None:
        return {"ok": False, "message": "This action was already handled."}

    # An old, forgotten prompt shouldn't be approvable days later (prices,
    # context and intent may all have changed).
    if _is_expired(action):
        db.resolve_pending_action(action_id, "expired")
        db.log_audit_event(action["chat_id"], "confirmation_expired", {"action_id": action_id})
        return {"ok": False, "message": "This request has expired - please ask again."}

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
