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

# Keys a user may set for themselves (Telegram /set, desktop Settings).
# Anything touching shared infrastructure (Telegram bot token, Supabase
# service key, the allow-list itself, webhook secrets, LLM provider) stays in
# the root .env only - a single user could otherwise repoint shared infra.
ALLOWED_OVERRIDE_KEYS = {
    "MS_CLIENT_ID", "MS_TENANT_ID",
    "SMARTTHINGS_PAT",
    "NEST_PROJECT_ID", "NEST_CLIENT_ID", "NEST_CLIENT_SECRET", "NEST_REFRESH_TOKEN",
    "WYZE_EMAIL", "WYZE_PASSWORD", "WYZE_KEY_ID", "WYZE_API_KEY",
    "HOMEBRIDGE_USERNAME", "HOMEBRIDGE_PASSWORD",
    "CLAREHOME_API_KEY",
    "ALADDIN_EMAIL", "ALADDIN_PASSWORD",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER",
    "TWITTER_BEARER_TOKEN", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET",
    "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN_SECRET", "TWITTER_FOLLOWED_HANDLES",
    "YOUTUBE_API_KEY",
    "SEARCH_API_KEY", "SEARCH_PROVIDER",
    "GROQ_MODEL",
    "JOB_SEARCH_PORTALS", "JOB_SEARCH_DEFAULT_LOCATION",
    "WISHLIST_CHECK_INTERVAL_HOURS",
    "FOOD_DEALS_ZIP_CODE", "FOOD_DEALS_CITY",
    "BRIEFING_LATITUDE", "BRIEFING_LONGITUDE",
}

# Per-user keys only an admin may set (admin console). Each of these either
# selects SHARED server-side credentials by label (Google/MS token files and
# iCloud/Yahoo passwords are keyed by account label), points the server at a
# filesystem path it will execute (FINANCE_BOT_PATH/PERSONAL_KEY_VAULT_PATH -
# a UNC path would be remote code execution), makes the server connect to an
# arbitrary host (SSRF), or picks whose vault records to read (the vault
# companion token is per-app, so VAULT_ACCOUNT_EMAIL is trusted as-is).
ADMIN_ONLY_OVERRIDE_KEYS = {
    "GOOGLE_ACCOUNTS", "GOOGLE_OAUTH_CLIENT_SECRETS_FILE",
    "MS_ACCOUNTS", "ICLOUD_ACCOUNTS", "YAHOO_ACCOUNTS",
    "HOMEBRIDGE_URL", "CLAREHOME_BASE_URL", "IROBOT_ROBOT_IPS",
    "FINANCE_BOT_PATH", "PERSONAL_KEY_VAULT_PATH",
    "VAULT_ACCOUNT_EMAIL", "VAULT_API_ENABLED",
    "VAULT_COMPANION_HOST", "VAULT_COMPANION_PORT", "VAULT_COMPANION_TOKEN",
    # Notification-only link from a desktop account to a Telegram chat. Only
    # ever set through the verified one-time-code flow (core/telegram_link.py,
    # Telegram `/link CODE`) or by an admin - never typed in by the user.
    "LINKED_TELEGRAM_CHAT_ID",
}

ALL_OVERRIDE_KEYS = ALLOWED_OVERRIDE_KEYS | ADMIN_ONLY_OVERRIDE_KEYS

_SECRET_KEY_MARKERS = ("PASSWORD", "TOKEN", "SECRET", "API_KEY", "PAT", "KEY_ID", "ACCOUNT_SID")

_ISOLATED_MARKER = ".isolated"
_isolated_chats: set[int] = set()

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
    # Only ever honor known per-user keys, even if the file was hand-edited.
    return {k: v for k, v in dotenv_values(path).items() if v is not None and k in ALL_OVERRIDE_KEYS}


def set_user_override(chat_id: "int | str", key: str, value: str, *, admin: bool = False) -> None:
    key = key.strip().upper()
    allowed = ALL_OVERRIDE_KEYS if admin else ALLOWED_OVERRIDE_KEYS
    if key not in allowed:
        if key in ADMIN_ONLY_OVERRIDE_KEYS:
            raise ValueError(f"'{key}' can only be set by an admin (admin console).")
        raise ValueError(
            f"'{key}' can't be set per-user. Allowed keys: {', '.join(sorted(ALLOWED_OVERRIDE_KEYS))}"
        )
    # Values are written unquoted into a dotenv file - a newline would let a
    # user inject arbitrary extra KEY=VALUE lines.
    if any(c in value for c in ("\r", "\n", "\x00")):
        raise ValueError("Value must be a single line.")
    if len(value) > 2000:
        raise ValueError("Value is too long.")
    path = _user_env_path(chat_id)
    path.touch(exist_ok=True)
    set_key(str(path), key, value, quote_mode="never")


def unset_user_override(chat_id: "int | str", key: str, *, admin: bool = False) -> None:
    key = key.strip().upper()
    if not admin and key not in ALLOWED_OVERRIDE_KEYS:
        raise ValueError(f"'{key}' can only be changed by an admin (admin console).")
    path = _user_env_path(chat_id)
    if path.exists():
        unset_key(str(path), key)


def _is_secret_key(key: str) -> bool:
    return any(marker in key for marker in _SECRET_KEY_MARKERS)


def _mask(value: str) -> str:
    return (value[:2] + "…" + value[-2:]) if len(value) > 6 else "•••"


def list_user_overrides_masked(chat_id: "int | str") -> dict[str, str]:
    """Values masked (safe to echo back over Telegram)."""
    return {k: _mask(v) for k, v in load_user_overrides(chat_id).items()}


def list_user_overrides_for_display(chat_id: "int | str") -> dict[str, str]:
    """Secrets masked, non-secret values (ids, locations, model) shown as-is.
    Used by the desktop client API so a stolen session token can't be used to
    read back every third-party password/token the user has saved."""
    return {k: (_mask(v) if _is_secret_key(k) else v) for k, v in load_user_overrides(chat_id).items()}


def mark_isolated_chat(chat_id: int) -> None:
    """Mark a chat (open self-signup desktop account) as isolated: its
    settings never inherit per-user credentials from the shared root .env.
    Persisted as a marker file so every process sees it."""
    if chat_id in _isolated_chats:
        return
    marker = _user_env_path(chat_id).parent / _ISOLATED_MARKER
    marker.touch(exist_ok=True)
    _isolated_chats.add(chat_id)


def is_isolated_chat(chat_id: "int | str") -> bool:
    try:
        cid = int(chat_id)
    except (TypeError, ValueError):
        return False
    if cid in _isolated_chats:
        return True
    safe = "".join(c for c in str(cid) if c.isalnum() or c in ("-", "_"))
    if (USERS_DIR / safe / _ISOLATED_MARKER).exists():
        _isolated_chats.add(cid)
        return True
    return False
