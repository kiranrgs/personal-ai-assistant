"""Nearby restaurant deal monitoring: DoorDash/GrubHub don't expose a
personal-use "current deals" feed API, so this uses web search (same pattern
as web_research/ticket_search.py) scoped to deal/promo pages for your area,
then an LLM pass to pull out anything worth acting on. Best-effort, not a
live feed - set SEARCH_API_KEY (Bing Web Search or similar) plus
FOOD_DEALS_ZIP_CODE or FOOD_DEALS_CITY.
"""
from __future__ import annotations

from typing import Any, Optional

import requests

from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.search_api_key and (s.food_deals_zip_code or s.food_deals_city))


def _bing_search(query: str, count: int = 5) -> list[dict[str, str]]:
    settings = get_settings()
    resp = requests.get(
        "https://api.bing.microsoft.com/v7.0/search",
        headers={"Ocp-Apim-Subscription-Key": settings.search_api_key},
        params={"q": query, "count": count},
        timeout=15,
    )
    resp.raise_for_status()
    pages = resp.json().get("webPages", {}).get("value", [])
    return [{"title": p["name"], "url": p["url"], "snippet": p.get("snippet", "")} for p in pages]


def search_nearby_food_deals(location: Optional[str] = None) -> dict[str, Any]:
    settings = get_settings()
    loc = location or settings.food_deals_zip_code or settings.food_deals_city
    if not settings.search_api_key or not loc:
        return {"error": "Not configured. Set SEARCH_API_KEY and FOOD_DEALS_ZIP_CODE/FOOD_DEALS_CITY in .env, or pass a location."}

    results: list[dict[str, str]] = []
    for query in (
        f"doordash deals near {loc}",
        f"grubhub promo code deals near {loc}",
        f"restaurant specials near {loc} today",
    ):
        try:
            results.extend(_bing_search(query))
        except Exception:  # noqa: BLE001
            continue

    if not results:
        return {"summary": "No deals found.", "results": []}
    text = "\n".join(f"- {r['title']} ({r['url']}): {r['snippet']}" for r in results)
    summary = summarize_items(
        "nearby restaurant deals/promos", text,
        instructions="Only call out genuinely actionable deals/discounts, ignore generic listing/directory pages.",
    )
    return {"summary": summary, "results": results}


register(Tool(
    name="search_nearby_food_deals",
    description="Search for current food delivery deals/promos at nearby restaurants (DoorDash/GrubHub/general web).",
    parameters={
        "type": "object",
        "properties": {"location": {"type": "string", "description": "ZIP code or city; defaults to FOOD_DEALS_ZIP_CODE/CITY"}},
    },
    handler=search_nearby_food_deals,
))
