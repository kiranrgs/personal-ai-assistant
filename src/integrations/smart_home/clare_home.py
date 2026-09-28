"""Clare Controls (ClareHome) integration. Clare doesn't publish a standard
public consumer API - access is via your installer's Clare Fusion dealer
portal, or a local ClareOne hub REST endpoint if your installation exposes
one. Set CLAREHOME_BASE_URL (e.g. your local hub's address, or your Fusion
endpoint) and CLAREHOME_API_KEY. Treat `_headers`/the endpoint paths below
as a thin, adjustable wrapper - exact paths vary by installation type/
firmware version, same "best-effort" caveat as the Wyze/Nest integrations.

Reading scenes never needs confirmation; triggering one (arming "Away" mode,
running "Good Night", etc) always does - EXCEPT for the household-geofencing
automation in household_presence.py, which calls
`trigger_scene_by_label_for_household` directly. That's a deliberate,
documented exception to the confirm-before-execute rule (see this repo's
README "Security model" section) because it must run unattended from a
trusted presence webhook, not from chat conversation.
"""
from __future__ import annotations

from typing import Any

import requests

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.clarehome_base_url and s.clarehome_api_key)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().clarehome_api_key}"}


def list_clarehome_scenes() -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Clare Home isn't configured yet. Set CLAREHOME_BASE_URL/CLAREHOME_API_KEY in .env."}
    base = get_settings().clarehome_base_url.rstrip("/")
    resp = requests.get(f"{base}/scenes", headers=_headers(), timeout=15)
    resp.raise_for_status()
    body = resp.json()
    scenes = body.get("scenes", body) if isinstance(body, dict) else body
    return {"scenes": scenes}


def _trigger_scene(scene_id: str) -> dict[str, Any]:
    base = get_settings().clarehome_base_url.rstrip("/")
    resp = requests.post(f"{base}/scenes/{scene_id}/trigger", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return {"status": "triggered", "scene_id": scene_id}


def request_clarehome_scene(scene_id: str, scene_label: str) -> Any:
    if not _is_configured():
        return {"error": "Clare Home isn't configured yet. Set CLAREHOME_BASE_URL/CLAREHOME_API_KEY in .env."}
    return PendingConfirmation(
        action_type="clarehome_scene",
        summary=f"Trigger Clare Home scene '{scene_label}'?",
        payload={"scene_id": scene_id},
    )


register(Tool(
    name="list_clarehome_scenes",
    description="List available Clare Home (ClareOne/Fusion) scenes, e.g. Home/Away/Good Night.",
    parameters={"type": "object", "properties": {}},
    handler=list_clarehome_scenes,
))

register(Tool(
    name="request_clarehome_scene",
    description="Request triggering a Clare Home scene (e.g. Away, Home, Good Night). Always requires confirmation.",
    parameters={
        "type": "object",
        "properties": {"scene_id": {"type": "string"}, "scene_label": {"type": "string"}},
        "required": ["scene_id", "scene_label"],
    },
    handler=request_clarehome_scene,
    requires_confirmation=True,
    executor=lambda payload: _trigger_scene(payload["scene_id"]),
))


def trigger_scene_by_label_for_household(scene_label: str) -> dict[str, Any]:
    """Internal helper (NOT an LLM tool) used only by household_presence.py's
    geofencing automation - see the module docstring above for why this one
    path is allowed to skip the Telegram confirm step."""
    if not _is_configured():
        return {"skipped": "clarehome_not_configured"}
    try:
        scenes = list_clarehome_scenes().get("scenes") or []
    except Exception as exc:  # noqa: BLE001
        return {"skipped": f"error_listing_scenes: {exc}"}
    match = next(
        (s for s in scenes if isinstance(s, dict) and str(s.get("name", "")).lower() == scene_label.lower()),
        None,
    )
    if match is None:
        return {"skipped": f"no_scene_named_{scene_label}"}
    scene_id = match.get("id") or match.get("scene_id")
    if not scene_id:
        return {"skipped": "scene_missing_id"}
    return _trigger_scene(scene_id)
