"""Shared helper for the rides/food-delivery integrations: none of
Uber/Lyft/DoorDash/GrubHub/Domino's offer a public API for a regular person
to place consumer orders programmatically (their public APIs are for
merchants/enterprise partners, not "book me a ride" style personal
automation). So the honest, safe approach is: draft the order/ride details,
get Telegram confirmation, then open the right app/website (deep link if
installed, web fallback otherwise) pre-filled as much as the URL scheme
allows, so completing it is one tap - never simulate raw checkout automation
against these sites' web UIs, which would violate their Terms of Service and
is fragile besides.
"""
from __future__ import annotations

import webbrowser
from typing import Any
from urllib.parse import quote


def open_url(url: str) -> dict[str, Any]:
    webbrowser.open(url)
    return {"status": "opened", "url": url}


def q(value: str) -> str:
    return quote(value, safe="")
