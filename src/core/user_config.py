"""Per-user configuration overlay for multi-user support.

Each allowed Telegram/WhatsApp/Discord chat can override a whitelisted
subset of settings (their own Google account labels, smart-home tokens,
wishlist search location, etc) without touching the shared root `.env` -
mirroring finance-bot's "each user configures their own thing" pattern, but
scoped per chat so one user's credentials/data are never visible to another.

Overrides are stored as a plain dotenv file per user under
`config/users/<chat_id>/user.env` (same KEY=VALUE format as `.env`, so it's
easy to inspect/edit by hand too, in addition to the `/set` bot command).

`set_current_chat()` is a context manager the orchestrator and confirmation
flow wrap around every user-triggered action. `get_settings()` in
`core.settings` checks this context and layers the current user's overrides
on top of the base process-wide `.env`. Tool handlers that need to know
"which chat is this" (without the LLM having to pass a chat_id argument,
which it can't be trusted to supply correctly) call `get_current_chat()`.
"""
from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from dotenv import dotenv_values, set_key, unset_key

log = logging.getLogger(__name__)

USERS_DIR = Path(__file__).resolve().parents[2] / "config" / "users"

# Only these env-var names may be overridden per-user. Anything touching
# shared infrastructure (Telegram bot token, Supabase service key, the
# allow-list itself, webhook secrets, LLM provider/model) stays admin-only in
# the root .env - a single user could otherwise repoint shared infra.
ALLOWED_OVERRIDE_KEYS = {
    "GOOGLE_ACCOUNTS", "GOOGLE_OAUTH_CLIENT_SECRETS_FILE",
    "MS_CLIENT_ID", "MS_TENANT_ID", "MS_ACCOUNTS",
    "ICLOUD_ACCOUNTS", "YAHOO_ACCOUNTS",
    "SMARTTHINGS_PAT",
    "NEST_PROJECT_ID", "NEST_CLIENT_ID", "NEST_CLIENT_SECRET", "NEST_REFRESH_TOKEN",
    "WYZE_EMAIL", "WYZE_PASSWORD", "WYZE_KEY_ID", "WYZE_API_KEY",
    "HOMEBRIDGE_URL", "HOMEBRIDGE_USERNAME", "HOMEBRIDGE_PASSWORD",
    "CLAREHOME_BASE_URL", "CLAREHOME_API_KEY",
    "ALADDIN_EMAIL", "ALADDIN_PASSWORD",
    "IROBOT_ROBOT_IPS",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER",
    "TWITTER_BEARER_TOKEN", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET",
    "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN_SECRET", "TWITTER_FOLLOWED_HANDLES",
    "YOUTUBE_API_KEY",
    "SEARCH_API_KEY", "SEARCH_PROVIDER",
    "WISHLIST_CHECK_INTERVAL_HOURS",
    "FOOD_DEALS_ZIP_CODE", "FOOD_DEALS_CITY",
    "BRIEFING_LATITUDE", "BRIEFING_LONGITUDE",
    "FINANCE_BOT_PATH", "PERSONAL_KEY_VAULT_PATH",
}

_current_chat: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("current_chat", default=None)


def get_current_chat() -> Optional[int]:
    """The internal `chats.id` for whoever triggered the code currently
    executing, or None if no user context is active (e.g. at import time, or
    in code paths not yet wrapped by `set_current_chat`)."""
    return _current_chat.get()


@contextmanager
def set_current_chat(chat_id: Optional[int]) -> Iterator[None]:
    token = _current_chat.set(chat_id)
    try:
        yield
    finally:
        _current_chat.reset(token)


def _user_env_path(chat_id: "int | str") -> Path:
    safe = "".join(c for c in str(chat_id) if c.isalnum() or c in ("-", "_")) or "unknown"
    d = USERS_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d / "user.env"


def load_user_overrides(chat_id: "int | str") -> dict[str, str]:
    path = _user_env_path(chat_id)
    if not path.exists():
        return {}
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def set_user_override(chat_id: "int | str", key: str, value: str) -> None:
    key = key.strip().upper()
    if key not in ALLOWED_OVERRIDE_KEYS:
        raise ValueError(
            f"'{key}' can't be set per-user. Allowed keys: {', '.join(sorted(ALLOWED_OVERRIDE_KEYS))}"
        )
    path = _user_env_path(chat_id)
    path.touch(exist_ok=True)
    set_key(str(path), key, value, quote_mode="never")


def unset_user_override(chat_id: "int | str", key: str) -> None:
    path = _user_env_path(chat_id)
    if path.exists():
        unset_key(str(path), key.strip().upper())


def list_user_overrides_masked(chat_id: "int | str") -> dict[str, str]:
    """Values masked (safe to echo back over Telegram)."""
    overrides = load_user_overrides(chat_id)
    masked = {}
    for k, v in overrides.items():
        masked[k] = (v[:2] + "…" + v[-2:]) if len(v) > 6 else "•••"
    return masked
