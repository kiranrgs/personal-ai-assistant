"""Web research for ticket prices (concerts, flights, events, etc) using a
generic search API, then an LLM pass to extract/compare prices from the
snippets. Actual purchase automation isn't safe or ToS-compliant to fully
automate (no public purchase APIs for Ticketmaster/StubHub/airlines for
personal use) - so "booking" here means: after the user picks an option and
confirms, open that exact page in their browser for one-tap checkout, never
auto-fill payment.
"""
from __future__ import annotations

import webbrowser
from typing import Any

import requests

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register
from src.integrations.email.summarizer import summarize_items


def _is_configured() -> bool:
    return bool(get_settings().search_api_key)


def _bing_search(query: str, count: int) -> list[dict[str, str]]:
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


def search_ticket_prices(event_query: str, max_results: int = 8) -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Web search isn't configured yet. Set SEARCH_API_KEY (and SEARCH_PROVIDER) in .env."}
    results = _bing_search(f"{event_query} tickets price", max_results)
    if not results:
        return {"summary": "No results found.", "results": []}
    text = "\n".join(f"- {r['title']} ({r['url']}): {r['snippet']}" for r in results)
    summary = summarize_items("ticket search results", text, instructions="Call out approximate prices and sources found; note this is not a guaranteed live price.")
    return {"summary": summary, "results": results}


def request_open_ticket_page(url: str, event_label: str) -> Any:
    return PendingConfirmation(
        action_type="open_ticket_page",
        summary=f"Open the ticket page for '{event_label}' so you can complete the purchase yourself?",
        payload={"url": url},
    )


register(Tool(
    name="search_ticket_prices",
    description="Search the web for ticket prices/availability for an event (concert, flight, sports, etc) and summarize the findings.",
    parameters={
        "type": "object",
        "properties": {"event_query": {"type": "string"}, "max_results": {"type": "integer"}},
        "required": ["event_query"],
    },
    handler=search_ticket_prices,
))

register(Tool(
    name="request_open_ticket_page",
    description=(
        "Request opening a specific ticket purchase page in the browser so the user can complete checkout "
        "themselves (no public API exists to fully automate ticket purchases safely). Always requires confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}, "event_label": {"type": "string"}},
        "required": ["url", "event_label"],
    },
    handler=request_open_ticket_page,
    requires_confirmation=True,
    executor=lambda payload: (webbrowser.open(payload["url"]), {"status": "opened", "url": payload["url"]})[1],
))
