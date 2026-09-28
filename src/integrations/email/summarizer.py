"""Small helper the email/calendar/social/file integrations share: ask the
LLM to summarize a batch of items into a Telegram-friendly digest.
"""
from __future__ import annotations

from src.core.llm_router import get_llm_router


def summarize_items(kind: str, items_text: str, instructions: str = "") -> str:
    """`items_text` should already be a plain-text rendering of the items
    (subjects/snippets, tweets, transcript, etc). Keeps this decoupled from
    any single provider's response shape.
    """
    router = get_llm_router()
    prompt = (
        f"Summarize the following {kind} for a busy person reading this on their "
        f"phone via Telegram. Use short bullet points, group related items, and "
        f"call out anything time-sensitive or requiring action. "
        f"{instructions}\n\n---\n{items_text}\n---"
    )
    response = router.chat([
        {"role": "system", "content": "You write concise, skimmable summaries for a Telegram bot."},
        {"role": "user", "content": prompt},
    ])
    return response.content
