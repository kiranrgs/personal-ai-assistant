"""Aladdin Connect (Genie/Overhead Door garage door openers).

STATUS: unlike this repo's other smart-home integrations, Aladdin Connect has
no stable public personal-use API AND no single well-established community
Python client the way Wyze has `wyze_sdk` - the mobile app talks to an
undocumented cloud API that has changed shape/auth flow more than once.
Search PyPI for a currently-maintained client (e.g. terms like "aladdin
connect") before relying on this, and adapt `_client()` below to match
whatever you land on. Treat this module as a wiring template, not a
guaranteed drop-in, more so than anything else in this repo.

Set ALADDIN_EMAIL / ALADDIN_PASSWORD in .env once you've picked a client
library and installed it manually (`pip install <that-package>` - not part
of requirements.txt, since pinning an uncertain/fast-moving package here
could break everyone else's `pip install -r requirements.txt`).

Reading door status never needs confirmation; opening/closing a garage door
always does.
"""
from __future__ import annotations

from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.aladdin_email and s.aladdin_password)


def _client():
    """ADAPT THIS: swap in whatever Aladdin Connect client package you
    installed. This assumes an interface roughly like:
        client = SomeAladdinClient(email, password)
        client.login()
        client.get_doors() -> list of {"device_id", "door_number", "name", "status"}
        client.open_door(device_id, door_number) / client.close_door(...)
    """
    raise NotImplementedError(
        "Pick and install an Aladdin Connect client package (search PyPI), then wire it up here - "
        "see this module's docstring."
    )


def list_aladdin_doors() -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Aladdin Connect isn't configured yet. Set ALADDIN_EMAIL/ALADDIN_PASSWORD in .env."}
    try:
        client = _client()
    except NotImplementedError as exc:
        return {"error": str(exc)}
    doors = client.get_doors()
    return {"count": len(doors), "doors": doors}


def _set_door(device_id: str, door_number: int, open_: bool) -> dict[str, Any]:
    client = _client()
    if open_:
        client.open_door(device_id, door_number)
    else:
        client.close_door(device_id, door_number)
    return {"status": "sent", "device_id": device_id, "open": open_}


def request_aladdin_door_command(device_id: str, door_number: int, door_label: str, open_: bool) -> Any:
    if not _is_configured():
        return {"error": "Aladdin Connect isn't configured yet. Set ALADDIN_EMAIL/ALADDIN_PASSWORD in .env."}
    return PendingConfirmation(
        action_type="aladdin_door_command",
        summary=f"{'Open' if open_ else 'Close'} the garage door '{door_label}'?",
        payload={"device_id": device_id, "door_number": door_number, "open_": open_},
    )


register(Tool(
    name="list_aladdin_doors",
    description="List Aladdin Connect (Genie) garage doors and their current status.",
    parameters={"type": "object", "properties": {}},
    handler=list_aladdin_doors,
))

register(Tool(
    name="request_aladdin_door_command",
    description="Request opening or closing an Aladdin Connect garage door. Always requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "device_id": {"type": "string"},
            "door_number": {"type": "integer"},
            "door_label": {"type": "string"},
            "open_": {"type": "boolean", "description": "true to open, false to close"},
        },
        "required": ["device_id", "door_number", "door_label", "open_"],
    },
    handler=request_aladdin_door_command,
    requires_confirmation=True,
    executor=lambda payload: _set_door(payload["device_id"], payload["door_number"], payload["open_"]),
))
