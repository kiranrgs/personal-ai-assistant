"""Wishlist price monitoring: track items you're interested in, get notified
when the price drops to your target, and place the order yourself via a
Telegram-confirmed one-tap open of the product page (same "no auto-checkout"
pattern as rides/food/tickets - no retailer offers a personal-use purchase
API, and auto-filling payment would be unsafe/ToS-violating).

Price detection is best-effort web scraping (Open Graph / product price meta
tags, falling back to a plain-text currency regex) - it won't work on every
site. If it can't detect a price, tell the assistant the price directly
(`known_current_price`) and it'll still track the item using what you told
it.

The actual periodic re-check (`check_all_wishlist_prices`) is called by a
scheduled job in bot.py, not by the LLM - it scans every user's active
wishlist items and returns any that hit their target price so the bot can
push a Telegram alert with a Confirm-to-order button.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

from src.core.tool_registry import PendingConfirmation, Tool, register
from src.core.user_config import get_current_chat
from src.db import supabase_client as db
from src.integrations.rides_food.common import open_url

_PRICE_RE = re.compile(r"[$£€]\s?(\d{1,6}(?:[.,]\d{2})?)")


def _fetch_price_and_title(url: str) -> tuple[Optional[float], Optional[str]]:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    title = None
    if title_tag is not None:
        title = title_tag.get("content") if title_tag.has_attr("content") else title_tag.text

    for prop in ("product:price:amount", "og:price:amount"):
        price_tag = soup.find("meta", property=prop)
        if price_tag is not None and price_tag.has_attr("content"):
            try:
                return float(price_tag["content"]), title
            except ValueError:
                pass

    match = _PRICE_RE.search(resp.text[:200_000])
    if match:
        try:
            return float(match.group(1).replace(",", "")), title
        except ValueError:
            pass
    return None, title


def add_wishlist_item(
    url: str, target_price: float, title: Optional[str] = None, known_current_price: Optional[float] = None
) -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "Couldn't determine which chat this is."}
    detected_price, detected_title = _fetch_price_and_title(url)
    current_price = known_current_price if known_current_price is not None else detected_price
    final_title = title or detected_title or url
    item = db.add_wishlist_item(chat_id, final_title, url, target_price, current_price)
    result: dict[str, Any] = {"item": item}
    if current_price is None:
        result["note"] = "Couldn't auto-detect the price on that page - tracking it anyway; tell me the price if you know it."
    return result


def list_wishlist_items() -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "Couldn't determine which chat this is."}
    items = db.list_wishlist_items(chat_id)
    return {"count": len(items), "items": items}


def remove_wishlist_item(item_id: int) -> dict[str, Any]:
    db.set_wishlist_status(item_id, "removed")
    return {"status": "removed", "item_id": item_id}


def request_place_wishlist_order(item_id: int) -> Any:
    item = db.get_wishlist_item(item_id)
    if item is None:
        return {"error": f"No wishlist item with id {item_id}"}
    price_txt = f"${item['current_price']}" if item.get("current_price") is not None else "unknown price"
    return PendingConfirmation(
        action_type="place_wishlist_order",
        summary=f"Open '{item['title']}' ({price_txt}) so you can complete the purchase?",
        payload={"url": item["url"], "item_id": item_id},
    )


def _execute_wishlist_order(payload: dict[str, Any]) -> dict[str, Any]:
    db.set_wishlist_status(payload["item_id"], "ordered")
    return open_url(payload["url"])


register(Tool(
    name="add_wishlist_item",
    description="Add a product URL to your wishlist with a target price; the assistant monitors it and alerts you on a good deal.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "target_price": {"type": "number"},
            "title": {"type": "string"},
            "known_current_price": {"type": "number", "description": "Give this if you already know the price and auto-detection might fail"},
        },
        "required": ["url", "target_price"],
    },
    handler=add_wishlist_item,
))

register(Tool(
    name="list_wishlist_items",
    description="List your tracked wishlist items and their last known prices.",
    parameters={"type": "object", "properties": {}},
    handler=list_wishlist_items,
))

register(Tool(
    name="remove_wishlist_item",
    description="Stop tracking a wishlist item.",
    parameters={"type": "object", "properties": {"item_id": {"type": "integer"}}, "required": ["item_id"]},
    handler=remove_wishlist_item,
))

register(Tool(
    name="request_place_wishlist_order",
    description="Request opening a wishlist item's product page to complete the purchase yourself. Always requires confirmation.",
    parameters={"type": "object", "properties": {"item_id": {"type": "integer"}}, "required": ["item_id"]},
    handler=request_place_wishlist_order,
    requires_confirmation=True,
    executor=_execute_wishlist_order,
))


def check_all_wishlist_prices() -> list[dict[str, Any]]:
    """Called by the scheduled job in bot.py, not an LLM tool - see module
    docstring."""
    alerts = []
    for item in db.list_all_active_wishlist_items():
        price, _ = _fetch_price_and_title(item["url"])
        if price is None:
            continue
        db.update_wishlist_price(item["id"], price)
        target = item.get("target_price")
        if target is not None and price <= target:
            alerts.append({**item, "current_price": price})
    return alerts
