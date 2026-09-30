"""Thin Supabase wrapper for chat memory, context snapshots, pending
confirmations, the audit log, integration-status reporting, and (as of
migration 0002) multi-user/household presence, preferences, wishlist
tracking, and LLM usage.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from supabase import Client, ClientOptions, create_client

from src.core.settings import get_settings

log = logging.getLogger(__name__)

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in .env (see supabase/migrations/0001_init.sql)."
            )
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def get_auth_client() -> Client:
    """A fresh, throwaway client for end-user Auth calls (sign up / sign in /
    refresh / get_user). Never run those on the shared `get_client()`
    instance: supabase-py swaps that client's DB Authorization header to the
    signed-in user's JWT on SIGNED_IN/TOKEN_REFRESHED, which would make every
    later server-side query (for every user) run as whoever logged in last.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.")
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )


def get_or_create_chat(
    channel: str, external_chat_id: str, display_name: str | None = None, tenant_id: int = 0
) -> dict[str, Any]:
    """`tenant_id` scopes multi-tenant Telegram bots (see src/bot.py, 0003_tenants.sql) -
    0 is always the default bot from .env; other channels (WhatsApp/Discord) don't use
    multiple tenants today and can leave this at the default."""
    db = get_client()
    existing = (
        db.table("chats")
        .select("*")
        .eq("channel", channel)
        .eq("external_chat_id", external_chat_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]
    created = (
        db.table("chats")
        .insert({
            "channel": channel, "external_chat_id": external_chat_id,
            "display_name": display_name, "tenant_id": tenant_id,
        })
        .execute()
    )
    return created.data[0]


def list_chats() -> list[dict[str, Any]]:
    """Every known chat across every tenant/channel - used by the admin console."""
    return get_client().table("chats").select("*").order("id").execute().data


def get_chat_by_internal_id(chat_id: int) -> Optional[dict[str, Any]]:
    """Reverse lookup: internal `chats.id` -> the row with its external
    (Telegram/WhatsApp/Discord) chat id, so scheduled jobs/webhooks that only
    have the internal id (e.g. from a wishlist_items row) can push a message
    back to the right external chat."""
    result = get_client().table("chats").select("*").eq("id", chat_id).limit(1).execute()
    return result.data[0] if result.data else None


def add_message(chat_id: int, role: str, content: str, tool_name: str | None = None) -> None:
    get_client().table("messages").insert(
        {"chat_id": chat_id, "role": role, "content": content, "tool_name": tool_name}
    ).execute()


def recent_messages(chat_id: int, limit: int = 20) -> list[dict[str, Any]]:
    result = (
        get_client()
        .table("messages")
        .select("*")
        .eq("chat_id", chat_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(result.data))


def save_context_snapshot(chat_id: int, kind: str, payload: dict[str, Any], label: str | None = None) -> None:
    get_client().table("context_snapshots").insert(
        {"chat_id": chat_id, "kind": kind, "label": label, "payload": payload}
    ).execute()


def latest_context_snapshot(chat_id: int, kind: str) -> Optional[dict[str, Any]]:
    result = (
        get_client()
        .table("context_snapshots")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("kind", kind)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_context_snapshot_by_label(chat_id: int, kind: str, label: str) -> Optional[dict[str, Any]]:
    result = (
        get_client()
        .table("context_snapshots")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("kind", kind)
        .eq("label", label)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def create_pending_action(chat_id: int, action_type: str, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = (
        get_client()
        .table("pending_actions")
        .insert({"chat_id": chat_id, "action_type": action_type, "summary": summary, "payload": payload})
        .execute()
    )
    return result.data[0]


def get_pending_action(action_id: str) -> Optional[dict[str, Any]]:
    result = get_client().table("pending_actions").select("*").eq("id", action_id).limit(1).execute()
    return result.data[0] if result.data else None


def latest_pending_action_for_chat(chat_id: int) -> Optional[dict[str, Any]]:
    result = (
        get_client()
        .table("pending_actions")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def claim_pending_action(action_id: str) -> Optional[dict[str, Any]]:
    """Atomically move a pending action to 'confirmed'. Returns the row only
    for the single caller that won the race (prevents double execution from
    double-clicks / replayed callbacks)."""
    result = (
        get_client()
        .table("pending_actions")
        .update({"status": "confirmed"})
        .eq("id", action_id)
        .eq("status", "pending")
        .execute()
    )
    return result.data[0] if result.data else None


def resolve_pending_action(action_id: str, status: str) -> None:
    get_client().table("pending_actions").update(
        {"status": status, "resolved_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", action_id).execute()


def log_audit_event(chat_id: int | None, event_type: str, detail: dict[str, Any]) -> None:
    try:
        get_client().table("audit_log").insert(
            {"chat_id": chat_id, "event_type": event_type, "detail": detail}
        ).execute()
    except Exception:
        log.exception("Failed to write audit log event %s", event_type)


def count_recent_tool_calls(chat_id: int, tool_name: str, minutes: int) -> int:
    """Used for anomaly detection - counts how many times `tool_name` was
    invoked for this chat in the last `minutes` (see core/orchestrator.py)."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    result = (
        get_client()
        .table("audit_log")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("event_type", "tool_call")
        .gte("created_at", since)
        .execute()
    )
    return sum(1 for row in result.data if (row.get("detail") or {}).get("tool") == tool_name)


def set_integration_status(integration: str, connected: bool, detail: str = "") -> None:
    get_client().table("integration_status").upsert(
        {
            "integration": integration,
            "connected": connected,
            "detail": detail,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


def search_messages(chat_id: int, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Full-text search over this chat's message history (see
    core/memory_search.py and migration 0002's `content_tsv` column)."""
    result = (
        get_client()
        .table("messages")
        .select("*")
        .eq("chat_id", chat_id)
        .text_search("content_tsv", query, options={"type": "websearch"})
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


# --- Multi-user / households (see core/user_config.py, integrations/smart_home/household_presence.py) ---

def get_or_create_user(chat_id: int, household: str | None = None) -> dict[str, Any]:
    db = get_client()
    existing = db.table("users").select("*").eq("chat_id", chat_id).limit(1).execute()
    if existing.data:
        return existing.data[0]
    created = db.table("users").insert({"chat_id": chat_id, "household": household}).execute()
    return created.data[0]


def get_user(chat_id: int) -> Optional[dict[str, Any]]:
    result = get_client().table("users").select("*").eq("chat_id", chat_id).limit(1).execute()
    return result.data[0] if result.data else None


def set_user_household(chat_id: int, household: str) -> dict[str, Any]:
    get_or_create_user(chat_id)
    result = get_client().table("users").update({"household": household}).eq("chat_id", chat_id).execute()
    return result.data[0]


def list_household_members(household: str) -> list[dict[str, Any]]:
    result = get_client().table("users").select("*").eq("household", household).execute()
    return result.data


# --- Presence / geofencing ---

def upsert_presence(chat_id: int, state: str) -> dict[str, Any]:
    get_or_create_user(chat_id)
    result = (
        get_client()
        .table("presence")
        .upsert({"chat_id": chat_id, "state": state, "updated_at": datetime.now(timezone.utc).isoformat()})
        .execute()
    )
    return result.data[0]


def household_all_away(household: str) -> bool:
    members = list_household_members(household)
    if not members:
        return False
    chat_ids = [m["chat_id"] for m in members]
    result = get_client().table("presence").select("*").in_("chat_id", chat_ids).execute()
    states = {row["chat_id"]: row["state"] for row in result.data}
    if len(states) < len(chat_ids):
        return False  # someone in the household hasn't reported presence yet - don't guess
    return all(s == "away" for s in states.values())


# --- Preferences ---

def set_preference(chat_id: int, key: str, value: str) -> None:
    get_client().table("preferences").upsert({"chat_id": chat_id, "key": key, "value": value}).execute()


def get_preferences(chat_id: int) -> dict[str, str]:
    result = get_client().table("preferences").select("*").eq("chat_id", chat_id).execute()
    return {row["key"]: row["value"] for row in result.data}


# --- Wishlist price monitoring ---

def add_wishlist_item(
    chat_id: int, title: str, url: str, target_price: float | None, current_price: float | None, currency: str = "USD"
) -> dict[str, Any]:
    result = (
        get_client()
        .table("wishlist_items")
        .insert({
            "chat_id": chat_id, "title": title, "url": url,
            "target_price": target_price, "current_price": current_price,
            "currency": currency, "status": "active",
        })
        .execute()
    )
    return result.data[0]


def list_wishlist_items(chat_id: int, status: str = "active") -> list[dict[str, Any]]:
    result = get_client().table("wishlist_items").select("*").eq("chat_id", chat_id).eq("status", status).execute()
    return result.data


def get_wishlist_item(item_id: int) -> Optional[dict[str, Any]]:
    result = get_client().table("wishlist_items").select("*").eq("id", item_id).limit(1).execute()
    return result.data[0] if result.data else None


def update_wishlist_price(item_id: int, current_price: float) -> None:
    get_client().table("wishlist_items").update(
        {"current_price": current_price, "last_checked_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", item_id).execute()


def set_wishlist_status(item_id: int, status: str) -> None:
    get_client().table("wishlist_items").update({"status": status}).eq("id", item_id).execute()


def list_all_active_wishlist_items() -> list[dict[str, Any]]:
    result = get_client().table("wishlist_items").select("*").eq("status", "active").execute()
    return result.data


# --- LLM usage ---

def log_llm_usage(chat_id: Optional[int], provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    try:
        get_client().table("llm_usage").insert({
            "chat_id": chat_id, "provider": provider, "model": model,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        }).execute()
    except Exception:
        log.exception("Failed to log LLM usage")


def get_llm_usage_summary(chat_id: int, days: int = 30) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = get_client().table("llm_usage").select("*").eq("chat_id", chat_id).gte("created_at", since).execute()
    totals: dict[str, Any] = {}
    for row in result.data:
        key = f"{row['provider']}:{row['model']}"
        bucket = totals.setdefault(key, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0})
        bucket["prompt_tokens"] += row.get("prompt_tokens") or 0
        bucket["completion_tokens"] += row.get("completion_tokens") or 0
        bucket["calls"] += 1
    return {"since_days": days, "by_model": totals}


# --- Tenants (multi-bot-token support - see src/bot.py, src/admin_server.py) ---

def list_tenants(active_only: bool = True) -> list[dict[str, Any]]:
    query = get_client().table("tenants").select("*").order("id")
    if active_only:
        query = query.eq("active", True)
    return query.execute().data


def get_tenant(tenant_id: int) -> Optional[dict[str, Any]]:
    result = get_client().table("tenants").select("*").eq("id", tenant_id).limit(1).execute()
    return result.data[0] if result.data else None


def create_tenant(name: str, telegram_bot_token: str, telegram_allowed_chat_ids: str) -> dict[str, Any]:
    result = (
        get_client()
        .table("tenants")
        .insert({
            "name": name,
            "telegram_bot_token": telegram_bot_token,
            "telegram_allowed_chat_ids": telegram_allowed_chat_ids,
        })
        .execute()
    )
    return result.data[0]


def set_tenant_active(tenant_id: int, active: bool) -> dict[str, Any]:
    result = get_client().table("tenants").update({"active": active}).eq("id", tenant_id).execute()
    return result.data[0]


# --- Message bookmarks (desktop client's chat window - see client_api_server.py) ---

def get_message(message_id: int) -> Optional[dict[str, Any]]:
    result = get_client().table("messages").select("*").eq("id", message_id).limit(1).execute()
    return result.data[0] if result.data else None


def add_bookmark(chat_id: int, message_id: int, note: str | None = None) -> dict[str, Any]:
    result = (
        get_client()
        .table("chat_bookmarks")
        .upsert({"chat_id": chat_id, "message_id": message_id, "note": note}, on_conflict="chat_id,message_id")
        .execute()
    )
    return result.data[0]


def list_bookmarks(chat_id: int) -> list[dict[str, Any]]:
    result = (
        get_client()
        .table("chat_bookmarks")
        .select("*, messages(*)")
        .eq("chat_id", chat_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_bookmark(bookmark_id: int) -> Optional[dict[str, Any]]:
    result = get_client().table("chat_bookmarks").select("*").eq("id", bookmark_id).limit(1).execute()
    return result.data[0] if result.data else None


def remove_bookmark(bookmark_id: int) -> None:
    get_client().table("chat_bookmarks").delete().eq("id", bookmark_id).execute()
