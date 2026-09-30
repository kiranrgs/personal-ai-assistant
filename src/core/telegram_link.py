"""Verified linking of a desktop account to a Telegram chat.

A desktop user can't just type in a Telegram chat id (they could enter
someone else's and have that person's notifications/alerts routed to or
from them). Instead the desktop app asks for a short-lived one-time code,
and the user sends `/link CODE` to the Telegram bot from the chat they want
linked - proving they actually control it.

Codes are stored as files (hashed name) so the separate client API and
Telegram bot processes both see them.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Optional

from src.core import user_config

LINK_KEY = "LINKED_TELEGRAM_CHAT_ID"
CODE_TTL_SECONDS = 600
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I look-alikes
_CODE_LENGTH = 8


def _codes_dir() -> Path:
    d = user_config.USERS_DIR.parent / "link_codes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _code_path(code: str) -> Path:
    return _codes_dir() / hashlib.sha256(code.strip().upper().encode()).hexdigest()


def _purge(desktop_chat_id: Optional[int] = None) -> None:
    """Drop expired codes, plus any outstanding code for `desktop_chat_id`."""
    now = time.time()
    for path in _codes_dir().iterdir():
        try:
            data = json.loads(path.read_text())
            if data["expires"] < now or data["chat_id"] == desktop_chat_id:
                path.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError, TypeError):
            path.unlink(missing_ok=True)


def create_link_code(desktop_chat_id: int) -> str:
    _purge(desktop_chat_id)
    code = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    _code_path(code).write_text(json.dumps({"chat_id": desktop_chat_id, "expires": time.time() + CODE_TTL_SECONDS}))
    return code


def redeem_link_code(code: str, telegram_chat_id: int) -> Optional[int]:
    """Links the desktop chat that issued `code` to `telegram_chat_id`.
    Returns that desktop chat id, or None if the code is invalid/expired."""
    path = _code_path(code)
    try:
        data = json.loads(path.read_text())
        # Delete before use so a code can only ever be redeemed once.
        path.unlink()
    except (OSError, ValueError):
        return None
    if data.get("expires", 0) < time.time():
        return None
    desktop_chat_id = int(data["chat_id"])
    user_config.set_user_override(desktop_chat_id, LINK_KEY, str(telegram_chat_id), admin=True)
    return desktop_chat_id


def unlink(desktop_chat_id: int) -> None:
    user_config.unset_user_override(desktop_chat_id, LINK_KEY, admin=True)
