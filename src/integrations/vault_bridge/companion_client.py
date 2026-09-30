"""Low-level client for personal-key-vault's "Companion apps API".

That API is a loopback-only (127.0.0.1), token-authenticated TCP socket -
never exposed to the network, never Supabase directly. Protocol: connect,
send ONE line of JSON, read ONE line of JSON back, then the connection
closes. See personal-key-vault's README ("Companion apps API" section) for
the full action list and trust model.

This module only speaks the wire protocol - it doesn't know about chats,
tools, or confirmation flows. See `personal_key_vault_client.py` for the
actual registered `Tool`s that use it.
"""
from __future__ import annotations

import json
import socket
from typing import Any

from src.core.settings import get_settings

# The vault now relays every request through its own server to Supabase
# (2+ round trips per action) and gives up itself after 20s, so wait a
# little longer than that rather than timing out first.
_TIMEOUT_SECONDS = 25.0


class CompanionApiError(RuntimeError):
    """The socket itself couldn't be reached/used (vault app not running,
    wrong host/port, connection dropped, bad JSON back). Distinct from an
    application-level `{"error": "..."}` response, which the vault returns
    deliberately (e.g. `user_not_found`) and callers should check for."""


def call(action: str, **params: Any) -> dict[str, Any]:
    """Send one companion-API request and return its parsed JSON response.

    Raises `CompanionApiError` if the socket can't be reached at all; an
    application-level error (e.g. `user_not_found`, bad token) comes back
    as a normal dict with an `"error"` key instead, per the protocol.
    """
    settings = get_settings()
    host = settings.vault_companion_host
    port = settings.vault_companion_port
    if not port:
        raise CompanionApiError(
            "VAULT_COMPANION_PORT isn't set - copy the port from this machine's "
            "companion.json (see personal-key-vault's Security tab -> 'Enable "
            "companion API') and have the admin set VAULT_COMPANION_PORT for this "
            "chat on the admin console's Users page first."
        )
    request: dict[str, Any] = {
        "app": settings.vault_app_name,
        "token": settings.vault_companion_token,
        "action": action,
    }
    request.update(params)
    payload = (json.dumps(request) + "\n").encode("utf-8")

    try:
        with socket.create_connection((host, port), timeout=_TIMEOUT_SECONDS) as sock:
            sock.sendall(payload)
            sock.settimeout(_TIMEOUT_SECONDS)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
    except OSError as exc:
        raise CompanionApiError(
            f"Couldn't reach personal-key-vault's companion API at {host}:{port} - "
            f"is the desktop app running with the companion API enabled? ({exc})"
        ) from exc

    if not buf:
        raise CompanionApiError("Companion API closed the connection without a response.")
    try:
        return json.loads(buf.decode("utf-8"))
    except ValueError as exc:
        raise CompanionApiError(f"Companion API returned invalid JSON: {exc}") from exc
