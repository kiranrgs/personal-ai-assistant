"""Samsung SmartThings integration via the official REST API. Create a
Personal Access Token at https://account.smartthings.com/tokens with scopes:
devices:read, devices:commands, and set SMARTTHINGS_PAT in .env.

Reading device state never needs confirmation; sending a command (turning
something on/off, locking/unlocking, etc) always does, since it actuates a
real device in the house.
"""
from __future__ import annotations

from typing import Any

import requests

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register

API_BASE = "https://api.smartthings.com/v1"


def _headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.smartthings_pat:
        raise RuntimeError("SMARTTHINGS_PAT is not set in .env")
    return {"Authorization": f"Bearer {settings.smartthings_pat}"}


def list_smartthings_devices() -> dict[str, Any]:
    resp = requests.get(f"{API_BASE}/devices", headers=_headers(), timeout=15)
    resp.raise_for_status()
    devices = [{"id": d["deviceId"], "label": d.get("label") or d.get("name")} for d in resp.json().get("items", [])]
    return {"count": len(devices), "devices": devices}


def _send_command(device_id: str, capability: str, command: str, args: list[Any] | None = None) -> dict[str, Any]:
    body = {"commands": [{"component": "main", "capability": capability, "command": command, "arguments": args or []}]}
    resp = requests.post(f"{API_BASE}/devices/{device_id}/commands", headers=_headers(), json=body, timeout=15)
    resp.raise_for_status()
    return {"status": "sent", "device_id": device_id, "command": command}


def request_smartthings_command(device_id: str, device_label: str, capability: str, command: str) -> Any:
    return PendingConfirmation(
        action_type="smartthings_command",
        summary=f"Send '{command}' ({capability}) to '{device_label}'?",
        payload={"device_id": device_id, "capability": capability, "command": command},
    )


register(Tool(
    name="list_smartthings_devices",
    description="List all Samsung SmartThings devices and their IDs.",
    parameters={"type": "object", "properties": {}},
    handler=list_smartthings_devices,
))

register(Tool(
    name="request_smartthings_command",
    description=(
        "Request sending a command to a SmartThings device (e.g. capability='switch', command='on'/'off'; "
        "capability='lock', command='lock'/'unlock'). Always requires confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "device_id": {"type": "string"},
            "device_label": {"type": "string", "description": "Human-readable device name, for the confirmation prompt"},
            "capability": {"type": "string", "description": "e.g. switch, lock, thermostatMode"},
            "command": {"type": "string", "description": "e.g. on, off, lock, unlock"},
        },
        "required": ["device_id", "device_label", "capability", "command"],
    },
    handler=request_smartthings_command,
    requires_confirmation=True,
    executor=lambda payload: _send_command(payload["device_id"], payload["capability"], payload["command"]),
))
