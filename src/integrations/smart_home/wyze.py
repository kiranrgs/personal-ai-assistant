"""Wyze devices via the unofficial `wyze_sdk` package (Wyze has no public
first-party API for personal use). Requires a Wyze developer API key/key ID
(create at developer-api-console.wyze.com) plus your normal Wyze account
email/password. This can break if Wyze changes their private API - treat it
as best-effort.
"""
from __future__ import annotations

from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.wyze_email and s.wyze_password and s.wyze_key_id and s.wyze_api_key)


def _client():
    from wyze_sdk import Client

    settings = get_settings()
    return Client(email=settings.wyze_email, password=settings.wyze_password, key_id=settings.wyze_key_id, api_key=settings.wyze_api_key)


def list_wyze_devices() -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Wyze isn't configured yet. Set WYZE_EMAIL/PASSWORD/KEY_ID/API_KEY in .env."}
    client = _client()
    devices = client.devices_list()
    return {"count": len(devices), "devices": [{"mac": d.mac, "nickname": d.nickname, "is_online": d.is_online} for d in devices]}


def _turn(device_mac: str, device_model: str, on: bool) -> dict[str, Any]:
    client = _client()
    if on:
        client.devices.turn_on(device_mac=device_mac, device_model=device_model)
    else:
        client.devices.turn_off(device_mac=device_mac, device_model=device_model)
    return {"status": "sent", "device_mac": device_mac, "on": on}


def request_wyze_toggle(device_mac: str, device_model: str, device_label: str, on: bool) -> Any:
    if not _is_configured():
        return {"error": "Wyze isn't configured yet. Set WYZE_EMAIL/PASSWORD/KEY_ID/API_KEY in .env."}
    return PendingConfirmation(
        action_type="wyze_toggle",
        summary=f"Turn {'on' if on else 'off'} Wyze device '{device_label}'?",
        payload={"device_mac": device_mac, "device_model": device_model, "on": on},
    )


register(Tool(
    name="list_wyze_devices",
    description="List Wyze smart home devices (plugs, cameras, bulbs) and their online status.",
    parameters={"type": "object", "properties": {}},
    handler=list_wyze_devices,
))

register(Tool(
    name="request_wyze_toggle",
    description="Request turning a Wyze device on or off. Always requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "device_mac": {"type": "string"},
            "device_model": {"type": "string"},
            "device_label": {"type": "string"},
            "on": {"type": "boolean"},
        },
        "required": ["device_mac", "device_model", "device_label", "on"],
    },
    handler=request_wyze_toggle,
    requires_confirmation=True,
    executor=lambda payload: _turn(payload["device_mac"], payload["device_model"], payload["on"]),
))
