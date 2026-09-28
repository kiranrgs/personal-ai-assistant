"""Google Nest via the Smart Device Management (Device Access) API.

One-time setup (real money: $5 one-time fee to Google):
  1. Create a Device Access project: console.nest.google.com/device-access
  2. Link a Google Cloud OAuth client (type "TVs and Limited Input" or "Web"),
     enable the Smart Device Management API.
  3. Complete the OAuth consent flow once for your Nest account to get a
     refresh token (see Google's "Get Started" walkthrough); set
     NEST_PROJECT_ID, NEST_CLIENT_ID, NEST_CLIENT_SECRET, NEST_REFRESH_TOKEN.

STATUS: real request shapes below, but untestable without your Device Access
project - tools report "not configured" until the four NEST_* vars are set.
"""
from __future__ import annotations

from typing import Any

import requests

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register

SDM_BASE = "https://smartdevicemanagement.googleapis.com/v1"


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.nest_project_id and s.nest_client_id and s.nest_client_secret and s.nest_refresh_token)


def _access_token() -> str:
    settings = get_settings()
    resp = requests.post(
        "https://www.googleapis.com/oauth2/v4/token",
        data={
            "client_id": settings.nest_client_id,
            "client_secret": settings.nest_client_secret,
            "refresh_token": settings.nest_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def list_nest_devices() -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Nest isn't configured yet. Set NEST_PROJECT_ID/CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN in .env."}
    settings = get_settings()
    token = _access_token()
    resp = requests.get(
        f"{SDM_BASE}/enterprises/{settings.nest_project_id}/devices",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    devices = [{"name": d["name"], "type": d.get("type", "")} for d in resp.json().get("devices", [])]
    return {"count": len(devices), "devices": devices}


def _execute_command(device_name: str, command: str, params: dict[str, Any]) -> dict[str, Any]:
    token = _access_token()
    resp = requests.post(
        f"{SDM_BASE}/{device_name}:executeCommand",
        headers={"Authorization": f"Bearer {token}"},
        json={"command": command, "params": params},
        timeout=15,
    )
    resp.raise_for_status()
    return {"status": "sent", "device_name": device_name, "command": command}


def request_nest_command(device_name: str, device_label: str, command: str, params: dict[str, Any] | None = None) -> Any:
    if not _is_configured():
        return {"error": "Nest isn't configured yet. Set NEST_PROJECT_ID/CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN in .env."}
    return PendingConfirmation(
        action_type="nest_command",
        summary=f"Send '{command}' to Nest device '{device_label}'?",
        payload={"device_name": device_name, "command": command, "params": params or {}},
    )


register(Tool(
    name="list_nest_devices",
    description="List Google Nest devices (thermostats, cameras, doorbells) via the Device Access API.",
    parameters={"type": "object", "properties": {}},
    handler=list_nest_devices,
))

register(Tool(
    name="request_nest_command",
    description=(
        "Request sending a command to a Nest device, e.g. command='sdm.devices.commands.ThermostatTemperatureSetpoint.SetHeat' "
        "with params={'heatCelsius': 20}. Always requires confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "device_name": {"type": "string", "description": "Full SDM device name, e.g. enterprises/.../devices/..."},
            "device_label": {"type": "string"},
            "command": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["device_name", "device_label", "command"],
    },
    handler=request_nest_command,
    requires_confirmation=True,
    executor=lambda payload: _execute_command(payload["device_name"], payload["command"], payload["params"]),
))
