"""Bridge to the sibling `personal-key-vault` app for payment/checkout flows.

SECURITY DESIGN (do not change without re-reading personal-key-vault's
README): that app is zero-knowledge encrypted - card numbers only ever exist
in plaintext momentarily inside its own unlocked UI, in memory, after the
user authenticates (password/PIN/biometric). There is deliberately no
network or IPC path that hands plaintext secrets to another process; the
only existing bridge (browser-extension autofill) is scoped to the vault's
own popup filling a page the user is actively looking at.

This assistant NEVER attempts to read, decrypt, or auto-paste real card
numbers/CVVs. Instead, when a purchase needs payment info, it:
  1. Prepares/fills everything else on the order (drafted by the calling
     integration - rides/food/tickets).
  2. Asks the user, via the normal confirm/reject Telegram prompt, whether to
     proceed.
  3. On confirm, calls `open_key_vault_app()` to bring the vault to the
     foreground so the user manually unlocks it and copies/autofills the
     card themselves - the human stays in the loop for the one step that
     actually moves money.

CROSS-USER SAFETY: in a multi-user/multi-tenant deployment, this machine's
single installed personal-key-vault app could in principle be signed in as
*anyone's* account when a purchase prompt fires for a *different* chat.
Blindly foregrounding it would risk one person completing a purchase using
another person's saved cards. To prevent that, every chat must first link
its own vault account's email (the same email it signed up with in
personal-key-vault) via `/set VAULT_ACCOUNT_EMAIL you@example.com` (or the
admin console's Users page) - `open_key_vault_app()` refuses to run until
that's set for the requesting chat, and echoes back the linked email so the
user can visually confirm the unlocked vault matches before they copy a
card. personal-key-vault's zero-knowledge design has no IPC surface today
for this app to *cryptographically* verify which account is actually
unlocked - that would require an additive change on personal-key-vault's
side (e.g. a local "whoami" status query); until then this is a
belt-and-suspenders reminder, not a hard guarantee, so review the linked
email shown before using a saved card.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.core.user_config import get_current_chat

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
                "Send `/set VAULT_ACCOUNT_EMAIL you@example.com` (the same email you use to sign in "
                "there) once, then try again - this prevents accidentally using someone else's saved cards."
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
