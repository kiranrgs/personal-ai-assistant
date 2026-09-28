"""Apple HomeKit devices (iPhone/Home app ecosystem) via a Homebridge bridge.
Apple provides no public first-party REST API for HomeKit; Homebridge
(homebridge.io) running on this same tower/network exposes accessories over
its own REST API (config-ui-x plugin), which is what this talks to.

Setup: install Homebridge + the "Homebridge Config UI X" plugin, enable its
API, set HOMEBRIDGE_URL/USERNAME/PASSWORD in .env.
"""
from __future__ import annotations

from typing import Any

import requests

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.homebridge_url and s.homebridge_username and s.homebridge_password)


def _token() -> str:
    settings = get_settings()
    resp = requests.post(
        f"{settings.homebridge_url}/api/auth/login",
        json={"username": settings.homebridge_username, "password": settings.homebridge_password},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def list_homekit_accessories() -> dict[str, Any]:
    if not _is_configured():
        return {"error": "HomeKit/Homebridge isn't configured yet. Set HOMEBRIDGE_URL/USERNAME/PASSWORD in .env."}
    settings = get_settings()
    token = _token()
    resp = requests.get(f"{settings.homebridge_url}/api/accessories", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    resp.raise_for_status()
    accessories = [{"unique_id": a["uniqueId"], "name": a.get("serviceName", a.get("type", ""))} for a in resp.json()]
    return {"count": len(accessories), "accessories": accessories}


def _set_characteristic(unique_id: str, characteristic_type: str, value: Any) -> dict[str, Any]:
    settings = get_settings()
    token = _token()
    resp = requests.put(
        f"{settings.homebridge_url}/api/accessories/{unique_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"characteristicType": characteristic_type, "value": value},
        timeout=15,
    )
    resp.raise_for_status()
    return {"status": "sent", "unique_id": unique_id, "value": value}


def request_homekit_command(unique_id: str, accessory_label: str, characteristic_type: str, value: Any) -> Any:
    if not _is_configured():
        return {"error": "HomeKit/Homebridge isn't configured yet. Set HOMEBRIDGE_URL/USERNAME/PASSWORD in .env."}
    return PendingConfirmation(
        action_type="homekit_command",
        summary=f"Set '{accessory_label}' {characteristic_type} to {value}?",
        payload={"unique_id": unique_id, "characteristic_type": characteristic_type, "value": value},
    )


register(Tool(
    name="list_homekit_accessories",
    description="List HomeKit accessories reachable via the local Homebridge bridge.",
    parameters={"type": "object", "properties": {}},
    handler=list_homekit_accessories,
))

register(Tool(
    name="request_homekit_command",
    description="Request setting a HomeKit accessory's characteristic (e.g. On=true/false, TargetTemperature). Always requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "unique_id": {"type": "string"},
            "accessory_label": {"type": "string"},
            "characteristic_type": {"type": "string"},
            "value": {},
        },
        "required": ["unique_id", "accessory_label", "characteristic_type", "value"],
    },
    handler=request_homekit_command,
    requires_confirmation=True,
    executor=lambda payload: _set_characteristic(payload["unique_id"], payload["characteristic_type"], payload["value"]),
))
