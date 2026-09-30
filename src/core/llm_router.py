"""Unified LLM router: Groq (default, free tier) with a configurable local
Ollama fallback/alternative. Both are exposed through the same
`chat(messages, tools)` interface so the orchestrator doesn't care which one
is active.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.core.settings import get_settings

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMRouter:
    """Call `.chat()` with OpenAI-style messages and an optional list of
    tool schemas (OpenAI/Groq function-calling format). Provider is chosen
    from LLM_DEFAULT_PROVIDER but can be overridden per-call, e.g. to force
    the local model for privacy-sensitive requests.
    """

    def __init__(self) -> None:
        self._groq_client = None
        self._ollama_client = None

    def _groq(self):
        if self._groq_client is None:
            from groq import Groq
            settings = get_settings()

            if not settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY is not set in .env")
            self._groq_client = Groq(api_key=settings.groq_api_key)
        return self._groq_client

    def _ollama(self):
        settings = get_settings()
        if self._ollama_client is None:
            import ollama

            self._ollama_client = ollama.Client(host=settings.ollama_host)
        return self._ollama_client

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        settings = get_settings()
        provider = provider or settings.llm_default_provider
        if provider == "groq":
            return self._chat_groq(messages, tools, model=model)
        if provider == "ollama":
            return self._chat_ollama(messages, tools, model=model)
        raise ValueError(f"Unknown LLM provider: {provider}")

    def _chat_groq(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        model: Optional[str] = None,
    ) -> LLMResponse:
        settings = get_settings()
        model_name = model or settings.groq_model
        client = self._groq()
        kwargs: dict[str, Any] = {"model": model_name, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        completion = client.chat.completions.create(**kwargs)
        choice = completion.choices[0].message
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}"))
            for tc in (choice.tool_calls or [])
        ]
        self._log_usage("groq", model_name, completion)
        return LLMResponse(content=choice.content or "", tool_calls=tool_calls)

    def _log_usage(self, provider: str, model: str, completion: Any) -> None:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return
        try:
            from src.core.user_config import get_current_chat
            from src.db import supabase_client as db

            db.log_llm_usage(
                get_current_chat(), provider, model,
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )
        except Exception:  # noqa: BLE001 - usage tracking must never break a chat reply
            log.exception("Failed to log LLM usage")

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        """Transcribe a voice note (e.g. a Telegram voice message) using
        Groq's hosted Whisper endpoint - used by bot.py's voice-message
        handler so users can talk to the assistant instead of typing."""
        client = self._groq()
        result = client.audio.transcriptions.create(file=(filename, audio_bytes), model="whisper-large-v3")
        return result.text

    def _chat_ollama(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        model: Optional[str] = None,
    ) -> LLMResponse:
        settings = get_settings()
        model_name = model or settings.ollama_model
        client = self._ollama()
        kwargs: dict[str, Any] = {"model": model_name, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = client.chat(**kwargs)
        message = response["message"]
        tool_calls = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            fn = tc["function"]
            args = fn["arguments"]
            if isinstance(args, str):
                args = json.loads(args or "{}")
            tool_calls.append(ToolCall(id=str(i), name=fn["name"], arguments=args))
        return LLMResponse(content=message.get("content", ""), tool_calls=tool_calls)


_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    return get_llm_router().transcribe_audio(audio_bytes, filename)
