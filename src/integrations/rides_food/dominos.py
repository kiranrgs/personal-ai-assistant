"""Domino's pizza order drafts. Domino's has no public personal-ordering API
either; opens their order-tracker/menu site pre-filled with a store search
for the user to build the actual order and pay.
"""
from __future__ import annotations

from typing import Any

from src.core.tool_registry import PendingConfirmation, Tool, register
from src.integrations.rides_food.common import open_url, q


def request_order_dominos(zip_or_address: str) -> Any:
    url = f"https://order.dominos.com/en/pages/order/#!/locations/search/?address={q(zip_or_address)}"
    return PendingConfirmation(
        action_type="order_dominos",
        summary=f"Open Domino's ordering for '{zip_or_address}' so you can build the order and pay?",
        payload={"url": url},
    )


register(Tool(
    name="request_order_dominos",
    description="Draft a Domino's pizza order and, on confirmation, open Domino's ordering site near the given address/zip for the user to finish.",
    parameters={"type": "object", "properties": {"zip_or_address": {"type": "string"}}, "required": ["zip_or_address"]},
    handler=request_order_dominos,
    requires_confirmation=True,
    executor=lambda payload: open_url(payload["url"]),
))
