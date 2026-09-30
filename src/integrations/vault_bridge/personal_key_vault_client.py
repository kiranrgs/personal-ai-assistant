"""Bridge to the sibling `personal-key-vault` app for payment/checkout flows.

Two integration modes, both **opt-in per chat** (never on by default):

1. **Manual (`open_key_vault_app`)** - the original, always-available mode.
   personal-key-vault's own vault data is zero-knowledge encrypted; this
   assistant never reads/decrypts/auto-pastes a real card number. It just
   brings the vault app to the foreground so the user unlocks it and copies/
   autofills a card themselves.
2. **Companion API (`vault_*` tools below)** - opt-in upgrade that talks to
   personal-key-vault's "Companion apps API" (loopback-only, token-
   authenticated socket - see its README's "Companion apps API" section).
   This lets the assistant create a companion-API user, fetch cards/
   credentials, and resolve/manage a default card per spend category so a
   transaction that doesn't specify a card can still pick a sensible one
   automatically. These "API-linked" records are a **separate concept**
   from the human's own zero-knowledge vault account - they're encrypted
   with a machine-local OS-keyring key on personal-key-vault's side, a
   deliberately weaker trade-off documented there. Because this mode CAN
   return real card numbers/CVVs (that's the point - "getting the card
   details/credentials" for automated use), it must be explicitly turned on
   per chat, in addition to VAULT_ACCOUNT_EMAIL below.

CROSS-USER SAFETY: in a multi-user/multi-tenant deployment, every chat must
first link its own vault account's email (the same email it signed up with
in personal-key-vault) via `/set VAULT_ACCOUNT_EMAIL you@example.com` (or the
admin console's Users page) - every function below refuses to run until
that's set for the requesting chat. That same email doubles as the
companion-API `userId`, so a chat can only ever create/read/manage its own
companion-API records, never another chat's. The companion API itself is
additionally opt-in per chat (`VAULT_API_ENABLED`, off by default) and
requires its own host/port/token (`VAULT_COMPANION_HOST`/`_PORT`/`_TOKEN`,
from personal-key-vault's Security tab), settable/editable at any time via
the same `/set` command (or the admin console) - never a shared, admin-wide
value that would let one chat see another's cards.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register
from src.core.user_config import get_current_chat
from src.integrations.vault_bridge import companion_client

# Tauri's release output layout differs per OS - check the one matching
# wherever this process is actually running (personal-key-vault is built
# per-platform, so only the matching candidate will ever exist).
if sys.platform.startswith("win"):
    _CANDIDATE_RELATIVE_PATHS = [
        "apps/desktop/src-tauri/target/release/personal-key-vault.exe",
    ]
elif sys.platform == "darwin":
    _CANDIDATE_RELATIVE_PATHS = [
        "apps/desktop/src-tauri/target/release/bundle/macos/personal-key-vault.app/Contents/MacOS/personal-key-vault",
        "apps/desktop/src-tauri/target/release/personal-key-vault",
    ]
else:  # Linux/Ubuntu
    _CANDIDATE_RELATIVE_PATHS = [
        "apps/desktop/src-tauri/target/release/personal-key-vault",
    ]


def open_key_vault_app() -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {
            "status": "no_chat_context",
            "message": "This can only be run from an active chat, so it's clear whose vault account to expect.",
        }
    settings = get_settings()
    if not settings.vault_account_email:
        return {
            "status": "not_linked",
            "message": (
                "You haven't linked a personal-key-vault account to this chat yet. "
                "Ask the admin to set VAULT_ACCOUNT_EMAIL for this chat on the admin console's Users page "
                "(the same email you use to sign in there), then try again - this prevents accidentally "
                "using someone else's saved cards."
            ),
        }
    root = Path(settings.personal_key_vault_path)
    for rel in _CANDIDATE_RELATIVE_PATHS:
        candidate = root / rel
        if candidate.is_file():
            subprocess.Popen([str(candidate)])
            return {
                "status": "opened",
                "path": str(candidate),
                "expected_account_email": settings.vault_account_email,
                "message": (
                    f"Opened Personal Key Vault - please confirm it's unlocked as {settings.vault_account_email} "
                    "before copying a card (this app can't verify that automatically)."
                ),
            }
    return {
        "status": "not_found",
        "message": (
            "Couldn't find a built personal-key-vault executable automatically. "
            "Please open Personal Key Vault yourself (tray icon, or Cmd/Ctrl+Shift+K) "
            "to complete the payment step."
        ),
    }


register(Tool(
    name="open_key_vault_app",
    description=(
        "Bring the Personal Key Vault app to the foreground so the user can manually unlock it and "
        "copy/autofill a card themselves. Never returns or guesses at real card numbers - use this only "
        "as the final manual step of an already-user-confirmed purchase. Requires the requesting chat to "
        "have linked its own vault account email first (VAULT_ACCOUNT_EMAIL) - if the result status is "
        "'not_linked', tell the user how to set that instead of retrying."
    ),
    parameters={"type": "object", "properties": {}},
    handler=open_key_vault_app,
))


# --------------------------------------------------------------------------
# Companion API (opt-in) - creating a companion-API user, reading cards/
# credentials, and category-based default-card resolution.
# --------------------------------------------------------------------------

def _require_api_ready() -> Optional[dict[str, Any]]:
    """Returns a blocking status dict if the companion API can't be used for
    the currently-active chat yet, or None if it's OK to proceed."""
    chat_id = get_current_chat()
    if chat_id is None:
        return {
            "status": "no_chat_context",
            "message": "This can only be run from an active chat, so it's clear whose vault records to use.",
        }
    settings = get_settings()
    if not settings.vault_account_email:
        return {
            "status": "not_linked",
            "message": (
                "You haven't linked a personal-key-vault account to this chat yet. "
                "Ask the admin to set VAULT_ACCOUNT_EMAIL for this chat on the admin console's Users page, "
                "then try again."
            ),
        }
    if not settings.vault_api_enabled:
        return {
            "status": "vault_api_disabled",
            "message": (
                "The personal-key-vault companion API isn't enabled for this chat yet. In personal-key-vault, "
                "sign in and enable it (Security tab -> 'Enable companion API'), then ask the admin to set "
                "VAULT_COMPANION_PORT / VAULT_COMPANION_TOKEN (from that same tab / this machine's "
                "companion.json) and enable the companion API for this chat on the admin console's Users "
                "page. Until then, use open_key_vault_app instead."
            ),
        }
    if not settings.vault_companion_port:
        return {
            "status": "not_configured",
            "message": "VAULT_API_ENABLED is on, but VAULT_COMPANION_PORT isn't set yet - see companion.json.",
        }
    return None


def _call(action: str, **params: Any) -> dict[str, Any]:
    """Companion-API call, auto-creating the companion-API user on first use
    (transparent "cross create user" - no separate signup step needed)."""
    settings = get_settings()
    user_id = settings.vault_account_email
    try:
        result = companion_client.call(action, userId=user_id, **params)
    except companion_client.CompanionApiError as exc:
        return {"status": "unreachable", "message": str(exc)}

    if result.get("error") == "user_not_found":
        try:
            created = companion_client.call("create_user", userId=user_id)
        except companion_client.CompanionApiError as exc:
            return {"status": "unreachable", "message": str(exc)}
        if not (created.get("created") or created.get("alreadyLinked")):
            return {"status": "error", "message": "Couldn't create the companion-API user record.", "detail": created}
        try:
            result = companion_client.call(action, userId=user_id, **params)
        except companion_client.CompanionApiError as exc:
            return {"status": "unreachable", "message": str(exc)}
    return result


def ensure_vault_user() -> dict[str, Any]:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("create_user")


register(Tool(
    name="ensure_vault_user",
    description=(
        "Create (or confirm) this chat's companion-API user record in personal-key-vault, keyed by its "
        "linked VAULT_ACCOUNT_EMAIL. Usually not needed directly - other vault_* tools call this "
        "automatically on first use - but useful to check/repair linkage."
    ),
    parameters={"type": "object", "properties": {}},
    handler=ensure_vault_user,
))


def get_vault_credentials(query: str = "") -> dict[str, Any]:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("get_credentials", query=query) if query else _call("get_credentials")


register(Tool(
    name="get_vault_credentials",
    description="Look up saved logins/credentials from personal-key-vault via the companion API (opt-in). Optional query filters by title/username/url.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
    handler=get_vault_credentials,
))


def get_vault_cards(query: str = "") -> dict[str, Any]:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("get_cards", query=query) if query else _call("get_cards")


register(Tool(
    name="get_vault_cards",
    description=(
        "Look up saved cards (including real card number/CVV) from personal-key-vault via the companion API "
        "(opt-in). Only use this once a purchase has already been user-confirmed and a specific card is "
        "actually needed - prefer resolve_vault_card_default when no card was specified."
    ),
    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
    handler=get_vault_cards,
))


def _create_credential_draft(title: str, username: str, password: str, url: str = "") -> Any:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return PendingConfirmation(
        action_type="vault_create_credential",
        summary=f"Save a new login '{title}' ({username}) to your Personal Key Vault?",
        payload={"title": title, "username": username, "password": password, "url": url},
    )


def _execute_create_credential(payload: dict[str, Any]) -> Any:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("create_credential", **payload)


register(Tool(
    name="create_vault_credential",
    description="Save a new login/credential to personal-key-vault via the companion API (opt-in). Requires user confirmation before it's actually stored.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "url": {"type": "string"},
        },
        "required": ["title", "username", "password"],
    },
    handler=_create_credential_draft,
    requires_confirmation=True,
    executor=_execute_create_credential,
))


def _create_card_draft(
    label: str,
    bank_name: str,
    cardholder_name: str,
    card_number: str,
    expiry_month: str,
    expiry_year: str,
    cvv: str = "",
    country: str = "",
) -> Any:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    last4 = card_number[-4:] if len(card_number) >= 4 else card_number
    return PendingConfirmation(
        action_type="vault_create_card",
        summary=f"Save a new card '{label}' ({bank_name}, ending {last4}) to your Personal Key Vault?",
        payload={
            "label": label,
            "bankName": bank_name,
            "cardholderName": cardholder_name,
            "cardNumber": card_number,
            "expiryMonth": expiry_month,
            "expiryYear": expiry_year,
            "cvv": cvv,
            "country": country,
        },
    )


def _execute_create_card(payload: dict[str, Any]) -> Any:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("create_card", **payload)


register(Tool(
    name="create_vault_card",
    description="Save a new card to personal-key-vault via the companion API (opt-in). Requires user confirmation before it's actually stored.",
    parameters={
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "bank_name": {"type": "string"},
            "cardholder_name": {"type": "string"},
            "card_number": {"type": "string"},
            "expiry_month": {"type": "string"},
            "expiry_year": {"type": "string"},
            "cvv": {"type": "string"},
            "country": {"type": "string"},
        },
        "required": ["label", "bank_name", "cardholder_name", "card_number", "expiry_month", "expiry_year"],
    },
    handler=lambda label, bank_name, cardholder_name, card_number, expiry_month, expiry_year, cvv="", country="": _create_card_draft(
        label, bank_name, cardholder_name, card_number, expiry_month, expiry_year, cvv, country
    ),
    requires_confirmation=True,
    executor=_execute_create_card,
))


# --------------------------------------------------------------------------
# Per-category default cards - "if the user doesn't specify a card, use the
# category default" - see personal-key-vault's `resolve_card_default`.
# --------------------------------------------------------------------------

def resolve_vault_card_default(category: str) -> dict[str, Any]:
    """Which card should be used for a spend category when the user didn't
    name one. Call this before a checkout/payment step whenever no specific
    card was requested."""
    blocked = _require_api_ready()
    if blocked:
        return blocked
    result = _call("resolve_card_default", category=category)
    if "error" in result or "status" in result:
        return result
    card = result.get("card") or {}
    masked_card = None
    if card:
        number = card.get("cardNumber") or ""
        masked_card = {
            "id": card.get("id"),
            "label": card.get("label"),
            "bankName": card.get("bankName"),
            "last4": number[-4:] if len(number) >= 4 else number,
        }
    return {"cardId": result.get("cardId"), "source": result.get("source"), "card": masked_card}


register(Tool(
    name="resolve_vault_card_default",
    description=(
        "Find out which card to use for a spend category (e.g. 'online shopping', 'utilities', 'rides') when "
        "the user didn't specify one for this transaction - call this before completing a purchase with no "
        "card named. Returns a masked card (label/bank/last 4 digits only); use get_vault_cards for the full "
        "card if genuinely needed."
    ),
    parameters={"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]},
    handler=resolve_vault_card_default,
))


def set_vault_card_default(category: str, card_id: str) -> dict[str, Any]:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("set_card_default", category=category, cardId=card_id)


register(Tool(
    name="set_vault_card_default",
    description="Pin a specific card as the default for a spend category (e.g. 'always use this card for utilities'), overriding usage-history-based resolution.",
    parameters={
        "type": "object",
        "properties": {"category": {"type": "string"}, "card_id": {"type": "string"}},
        "required": ["category", "card_id"],
    },
    handler=lambda category, card_id: set_vault_card_default(category, card_id),
))


def clear_vault_card_default(category: str) -> dict[str, Any]:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("clear_card_default", category=category)


register(Tool(
    name="clear_vault_card_default",
    description="Remove an explicit default-card pin for a spend category, reverting it back to usage-history/none.",
    parameters={"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]},
    handler=clear_vault_card_default,
))


def list_vault_card_defaults() -> dict[str, Any]:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("list_card_defaults")


register(Tool(
    name="list_vault_card_defaults",
    description="List every spend-category -> card default currently pinned for this chat's linked vault account.",
    parameters={"type": "object", "properties": {}},
    handler=list_vault_card_defaults,
))


def record_vault_card_usage(category: str, card_id: str) -> dict[str, Any]:
    blocked = _require_api_ready()
    if blocked:
        return blocked
    return _call("record_card_usage", category=category, cardId=card_id)


register(Tool(
    name="record_vault_card_usage",
    description=(
        "Tell the vault which card was actually used for a spend category after a transaction, so future "
        "resolve_vault_card_default usage-history fallback stays accurate. Call this after any purchase where "
        "a card was picked (whether the user named it or it came from the category default)."
    ),
    parameters={
        "type": "object",
        "properties": {"category": {"type": "string"}, "card_id": {"type": "string"}},
        "required": ["category", "card_id"],
    },
    handler=record_vault_card_usage,
))
