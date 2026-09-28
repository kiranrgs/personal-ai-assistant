"""Full-text recall over past conversation history, so follow-ups like "what
did that email about the flight say last month" work without re-fetching.

Uses Postgres full-text search (`messages.content_tsv`, see migration
0002_multi_user_household_wishlist.sql) rather than true vector embeddings,
to avoid adding a heavy ML dependency (torch/sentence-transformers) to an
already dependency-heavy project. This gives good-enough keyword/phrase
recall; genuinely fuzzy semantic recall would need pgvector + an embedding
model later if this proves insufficient.
"""
from __future__ import annotations

from typing import Any

from src.core.tool_registry import Tool, register
from src.core.user_config import get_current_chat
from src.db import supabase_client as db


def search_past_conversations(query: str, limit: int = 10) -> dict[str, Any]:
    chat_id = get_current_chat()
    if chat_id is None:
        return {"error": "Couldn't determine which chat this is."}
    results = db.search_messages(chat_id, query, limit)
    return {"count": len(results), "results": results}


register(Tool(
    name="search_past_conversations",
    description=(
        "Search this chat's own past conversation history for a keyword/phrase - use this before saying "
        "you don't remember something that may have come up earlier (an email digest, a summary, an answer)."
    ),
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"],
    },
    handler=search_past_conversations,
))
