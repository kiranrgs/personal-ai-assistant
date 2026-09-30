"""Server-side catalog of Groq models exposed to clients.

The model roster and tier assignment mirror the finance-bot repo's Groq tier
pools (``GROQ_SMALL_MODEL_POOL`` / ``GROQ_MEDIUM_MODEL_POOL`` /
``GROQ_HIGH_MODEL_POOL`` in ``src/config/settings.py``). Groq's free tier
currently only has three general-purpose text models, so each is exposed as
its own tier here (finance-bot lets small/medium share a roster; the desktop
dropdown needs one distinct choice per tier).

The catalog can be repointed without a code change via env vars, using the
same names and comma-separated format as finance-bot:
``GROQ_SMALL_MODEL_POOL``, ``GROQ_MEDIUM_MODEL_POOL``, ``GROQ_HIGH_MODEL_POOL``.

Rules enforced by the server (never trust the client):
- Only catalog models are accepted.
- Chat channels other than the desktop client (Telegram, WhatsApp, Discord)
  may only use small-tier models.
"""
from __future__ import annotations

import os
from typing import Optional, TypedDict

DESKTOP_CHANNEL = "desktop"


class GroqModelInfo(TypedDict):
    id: str
    label: str
    tier: str
    token_profile: str


_TIER_TOKEN_PROFILE = {"small": "low", "medium": "medium", "high": "high"}
_TIER_ORDER = ("small", "medium", "high")

# tier -> (env var, default pool). Same defaults as finance-bot.
_TIER_POOLS: dict[str, tuple[str, str]] = {
    "small": ("GROQ_SMALL_MODEL_POOL", "qwen/qwen3.8-27b"),
    "medium": ("GROQ_MEDIUM_MODEL_POOL", "openai/gpt-oss-20b"),
    "high": ("GROQ_HIGH_MODEL_POOL", "openai/gpt-oss-120b"),
}

_LABELS: dict[str, str] = {
    "qwen/qwen3.8-27b": "Qwen 3.8 27B",
    "openai/gpt-oss-20b": "GPT-OSS 20B",
    "openai/gpt-oss-120b": "GPT-OSS 120B",
}

# Keep the default small and low-cost for day-to-day assistant usage.
DEFAULT_GROQ_MODEL = _TIER_POOLS["small"][1]


def _label_for(model_id: str) -> str:
    return _LABELS.get(model_id) or model_id.split("/")[-1]


def _pool(tier: str) -> list[str]:
    env_name, default = _TIER_POOLS[tier]
    raw = os.getenv(env_name) or default
    return [m.strip() for m in raw.split(",") if m.strip()]


def list_groq_models() -> list[GroqModelInfo]:
    """All selectable models, ordered small -> medium -> high, de-duplicated.

    If a model appears in several tier pools it is listed once, at its
    smallest tier.
    """
    seen: set[str] = set()
    models: list[GroqModelInfo] = []
    for tier in _TIER_ORDER:
        for model_id in _pool(tier):
            if model_id in seen:
                continue
            seen.add(model_id)
            models.append(
                {
                    "id": model_id,
                    "label": _label_for(model_id),
                    "tier": tier,
                    "token_profile": _TIER_TOKEN_PROFILE[tier],
                }
            )
    return models


def default_model() -> str:
    """First small-tier model (the safe default for every channel)."""
    small = [m for m in list_groq_models() if m["tier"] == "small"]
    return small[0]["id"] if small else DEFAULT_GROQ_MODEL


def is_allowed_groq_model(model_id: str) -> bool:
    return any(m["id"] == model_id for m in list_groq_models())


def list_models_for_channel(channel: Optional[str]) -> list[GroqModelInfo]:
    """Models a given chat channel may use (desktop: all; others: small only)."""
    models = list_groq_models()
    if channel == DESKTOP_CHANNEL:
        return models
    return [m for m in models if m["tier"] == "small"]


def is_allowed_for_channel(model_id: Optional[str], channel: Optional[str]) -> bool:
    if not model_id:
        return False
    return any(m["id"] == model_id for m in list_models_for_channel(channel))


def resolve_model(
    channel: Optional[str],
    requested: Optional[str] = None,
    user_preferred: Optional[str] = None,
) -> str:
    """Pick the model to actually use.

    Order: explicit per-request choice, then the user's saved preference, then
    the small default. Anything not permitted for the channel is skipped.
    """
    for candidate in (requested, user_preferred):
        if candidate and is_allowed_for_channel(candidate, channel):
            return candidate
    return default_model()
