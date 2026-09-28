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
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import Tool, register

_CANDIDATE_RELATIVE_PATHS = [
    r"apps\desktop\src-tauri\target\release\personal-key-vault.exe",
    r"apps\desktop\src-tauri\target\release\bundle\msi",  # installer output, not launchable directly
]


def open_key_vault_app() -> dict[str, Any]:
    settings = get_settings()
    root = Path(settings.personal_key_vault_path)
    for rel in _CANDIDATE_RELATIVE_PATHS:
        candidate = root / rel
        if candidate.is_file():
            subprocess.Popen([str(candidate)])
            return {"status": "opened", "path": str(candidate)}
    return {
        "status": "not_found",
        "message": (
            "Couldn't find a built personal-key-vault executable automatically. "
            "Please open Personal Key Vault yourself (tray icon or Ctrl+Shift+K) "
            "to complete the payment step."
        ),
    }


register(Tool(
    name="open_key_vault_app",
    description=(
        "Bring the Personal Key Vault app to the foreground so the user can manually unlock it and "
        "copy/autofill a card themselves. Never returns or guesses at real card numbers - use this only "
        "as the final manual step of an already-user-confirmed purchase."
    ),
    parameters={"type": "object", "properties": {}},
    handler=open_key_vault_app,
))
