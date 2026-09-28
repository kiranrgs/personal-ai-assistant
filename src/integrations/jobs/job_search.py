"""Job search across multiple job portals, matched against a saved profile
(desired role titles + location + remote preference, stored via the
existing `preferences` table - no new schema needed).

Like `web_research/ticket_search.py` and `rides_food/food_deals.py`, none
of LinkedIn, Indeed, Glassdoor, or ZipRecruiter offer a personal-use "search
jobs" API, so this uses web search (SEARCH_API_KEY, Bing Web Search) scoped
to each portal's job-listing URL pattern via `site:`, then an LLM pass to
group/summarize genuinely matching openings. Best-effort, not a live ATS
feed - same honesty tradeoff as those other integrations.
"""
from __future__ import annotations

from typing import Any, Optional

import requests

from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.core.user_config import get_current_chat
from src.db import supabase_client as db
from src.integrations.email.summarizer import summarize_items

_ROLES_KEY = "job_search_roles"
_LOCATION_KEY = "job_search_location"
_REMOTE_KEY = "job_search_remote_only"


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


def set_job_search_profile(roles: str, location: Optional[str] = None, remote_only: bool = False) -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "No active chat context - this can only be called from a live conversation."}
    db.set_preference(chat_id, _ROLES_KEY, roles)
    if location is not None:
        db.set_preference(chat_id, _LOCATION_KEY, location)
    db.set_preference(chat_id, _REMOTE_KEY, "true" if remote_only else "false")
    return {"status": "saved", "roles": roles, "location": location, "remote_only": remote_only}


def _load_profile() -> tuple[list[str], str, bool]:
    chat_id = get_current_chat()
    prefs = db.get_preferences(chat_id) if chat_id is not None else {}
    roles = [r.strip() for r in prefs.get(_ROLES_KEY, "").split(",") if r.strip()]
    location = prefs.get(_LOCATION_KEY, "")
    remote_only = prefs.get(_REMOTE_KEY, "false").lower() == "true"
    return roles, location, remote_only


def search_jobs(
    roles: Optional[str] = None, location: Optional[str] = None, remote_only: Optional[bool] = None
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.search_api_key:
        return {"error": "Not configured. Set SEARCH_API_KEY in .env (or your own /set SEARCH_API_KEY override)."}

    saved_roles, saved_location, saved_remote = _load_profile()
    role_list = [r.strip() for r in roles.split(",")] if roles else saved_roles
    role_list = [r for r in role_list if r]
    loc = location or saved_location or settings.job_search_default_location
    remote = saved_remote if remote_only is None else remote_only

    if not role_list:
        return {
            "error": "No job roles to search for. Call set_job_search_profile first (or pass 'roles' directly), "
            "e.g. roles='senior backend engineer, staff software engineer'."
        }

    portals = settings.job_search_portal_list
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for role in role_list:
        for portal in portals:
            query_parts = [f'"{role}" jobs site:{portal}']
            if loc:
                query_parts.append(loc)
            if remote:
                query_parts.append("remote")
            try:
                for r in _bing_search(" ".join(query_parts), count=5):
                    if r["url"] not in seen_urls:
                        seen_urls.add(r["url"])
                        results.append({**r, "role": role, "portal": portal})
            except Exception:  # noqa: BLE001
                continue

    if not results:
        return {"summary": "No matching job postings found.", "results": [], "roles_searched": role_list}
    text = "\n".join(f"- [{r['role']} / {r['portal']}] {r['title']} ({r['url']}): {r['snippet']}" for r in results)
    summary = summarize_items(
        "job openings across multiple portals", text,
        instructions=(
            "Group by role. Only call out postings that genuinely look like a match for the role title "
            "given - ignore generic career-page/directory links and obviously unrelated roles."
        ),
    )
    return {"summary": summary, "results": results, "roles_searched": role_list, "location": loc, "remote_only": remote}


register(Tool(
    name="set_job_search_profile",
    description="Save the user's job search profile (desired role titles, location, remote preference) for later job searches.",
    parameters={
        "type": "object",
        "properties": {
            "roles": {"type": "string", "description": "Comma-separated job title keywords, e.g. 'senior backend engineer, staff software engineer'"},
            "location": {"type": "string", "description": "City/region, or leave blank for remote-agnostic"},
            "remote_only": {"type": "boolean", "description": "Only look for remote roles"},
        },
        "required": ["roles"],
    },
    handler=set_job_search_profile,
))

register(Tool(
    name="search_jobs",
    description="Search multiple job portals (LinkedIn, Indeed, Glassdoor, ZipRecruiter) for openings matching the user's saved (or given) job profile, across multiple role titles.",
    parameters={
        "type": "object",
        "properties": {
            "roles": {"type": "string", "description": "Comma-separated role titles; defaults to the saved profile"},
            "location": {"type": "string", "description": "Overrides the saved location for this search"},
            "remote_only": {"type": "boolean", "description": "Overrides the saved remote preference for this search"},
        },
    },
    handler=search_jobs,
))
