"""Ride booking drafts for Uber and Lyft. See `common.py` for why this opens
the app/site for the user to tap-confirm rather than fully automating
checkout - neither company offers a personal-use booking API.
"""
from __future__ import annotations

from typing import Any

from src.core.tool_registry import PendingConfirmation, Tool, register
from src.integrations.rides_food.common import open_url, q


def request_book_ride(provider: str, pickup: str, destination: str) -> Any:
    if provider not in ("uber", "lyft"):
        return {"error": "provider must be 'uber' or 'lyft'"}
    if provider == "uber":
        url = f"https://m.uber.com/looking?pickup=%5B{q(pickup)}%5D&dropoff=%5B{q(destination)}%5D"
    else:
        url = f"https://ride.lyft.com/?pickup={q(pickup)}&destination={q(destination)}"
    return PendingConfirmation(
        action_type=f"book_ride_{provider}",
        summary=f"Open {provider.title()} to book a ride from '{pickup}' to '{destination}'? You'll confirm and pay in the app.",
        payload={"url": url},
    )


register(Tool(
    name="request_book_ride",
    description="Draft a ride booking (Uber or Lyft) and, on confirmation, open the app/site pre-filled with pickup/destination for the user to finish booking.",
    parameters={
        "type": "object",
        "properties": {
            "provider": {"type": "string", "enum": ["uber", "lyft"]},
            "pickup": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["provider", "pickup", "destination"],
    },
    handler=request_book_ride,
    requires_confirmation=True,
    executor=lambda payload: open_url(payload["url"]),
))
