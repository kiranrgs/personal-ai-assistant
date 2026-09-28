"""Food-order drafts for DoorDash and GrubHub, and Domino's separately since
it has its own ordering flow. Same "draft + open for one-tap confirm" design
as rides.py - none of these offer a personal consumer ordering API.
"""
from __future__ import annotations

from typing import Any

from src.core.tool_registry import PendingConfirmation, Tool, register
from src.integrations.rides_food.common import open_url, q


def request_order_food(provider: str, restaurant_or_search: str) -> Any:
    if provider not in ("doordash", "grubhub"):
        return {"error": "provider must be 'doordash' or 'grubhub'"}
    if provider == "doordash":
        url = f"https://www.doordash.com/search/store/{q(restaurant_or_search)}"
    else:
        url = f"https://www.grubhub.com/search?queryText={q(restaurant_or_search)}"
    return PendingConfirmation(
        action_type=f"order_food_{provider}",
        summary=f"Open {provider.title()} search for '{restaurant_or_search}' so you can place the order?",
        payload={"url": url},
    )


register(Tool(
    name="request_order_food",
    description="Draft a food order (DoorDash or GrubHub) and, on confirmation, open the search results for the user to pick items and pay.",
    parameters={
        "type": "object",
        "properties": {"provider": {"type": "string", "enum": ["doordash", "grubhub"]}, "restaurant_or_search": {"type": "string"}},
        "required": ["provider", "restaurant_or_search"],
    },
    handler=request_order_food,
    requires_confirmation=True,
    executor=lambda payload: open_url(payload["url"]),
))
