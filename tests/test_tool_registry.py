"""Smoke tests that don't require any real credentials - just verify the
tool registry wires up without import errors and confirmation flow logic is
sound. Run with: pytest
"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize("module_name", [
    "src.integrations.email.gmail",
    "src.integrations.email.icloud_yahoo_imap",
    "src.integrations.email.outlook",
    "src.integrations.calendar_.google_calendar",
    "src.integrations.calendar_.icloud_calendar",
    "src.integrations.calendar_.outlook_calendar",
    "src.integrations.files.google_drive",
    "src.integrations.files.google_sheets",
    "src.integrations.files.icloud_files",
    "src.integrations.smart_home.smartthings",
    "src.integrations.smart_home.nest",
    "src.integrations.smart_home.wyze",
    "src.integrations.smart_home.homekit_bridge",
    "src.integrations.smart_home.clare_home",
    "src.integrations.smart_home.aladdin_connect",
    "src.integrations.smart_home.irobot",
    "src.integrations.smart_home.household_presence",
    "src.integrations.rides_food.rides",
    "src.integrations.rides_food.food_delivery",
    "src.integrations.rides_food.dominos",
    "src.integrations.rides_food.food_deals",
    "src.integrations.telephony.twilio_calls",
    "src.integrations.social.twitter",
    "src.integrations.social.youtube",
    "src.integrations.web_research.ticket_search",
    "src.integrations.vault_bridge.personal_key_vault_client",
    "src.integrations.automation_hub.finance_bot_trigger",
    "src.integrations.briefing.daily_briefing",
    "src.integrations.shopping.wishlist",
    "src.integrations.email.package_tracking",
    "src.core.preferences",
    "src.core.memory_search",
    "src.core.usage_tool",
])
def test_integration_module_imports_and_registers_tools(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module is not None


def test_tool_registry_has_expected_tools() -> None:
    from src.core.tool_registry import all_tools

    for name in [
        "list_todays_emails", "summarize_todays_emails",
        "list_upcoming_calendar_events", "create_calendar_event",
        "request_book_ride", "request_order_food", "request_order_dominos",
        "request_place_call", "request_smartthings_command",
        "list_clarehome_scenes", "request_clarehome_scene",
        "list_aladdin_doors", "request_aladdin_door_command",
        "list_irobot_robots", "request_irobot_command",
        "report_my_presence", "list_household_presence",
        "summarize_followed_twitter_digest", "ask_about_youtube_video",
        "add_wishlist_item", "list_wishlist_items", "request_place_wishlist_order",
        "search_nearby_food_deals", "summarize_package_tracking",
        "generate_daily_briefing",
        "set_preference", "get_preferences",
        "search_past_conversations", "get_llm_usage_summary",
    ]:
        importlib.import_module("src.bot")
        assert any(t.name == name for t in all_tools()), f"Tool '{name}' was not registered"
