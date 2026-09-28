"""Outbound phone calls via Twilio. Two modes:

  1. Simple announcement call (`request_place_call`): dials a number and
     reads a scripted message via Twilio's TTS (<Say>). Good for reminders,
     confirmations, or leaving a message.
  2. Interactive call (`request_place_interactive_call`): dials a number and
     hands the call off to `src/webhook_server.py`'s /voice/interactive
     webhook, which loops speech-to-text -> LLM -> text-to-speech so the
     assistant can actually converse with whoever picks up (e.g. customer
     care). This requires PUBLIC_WEBHOOK_BASE_URL to point at a publicly
     reachable HTTPS URL for this machine (e.g. via ngrok/cloudflared) and
     the webhook server process to be running.

Both always require Telegram confirmation before dialing.
"""
from __future__ import annotations

from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number)


def _client():
    from twilio.rest import Client

    settings = get_settings()
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def _place_announcement_call(to_number: str, message: str) -> dict[str, Any]:
    settings = get_settings()
    twiml = f"<Response><Say>{message}</Say></Response>"
    call = _client().calls.create(to=to_number, from_=settings.twilio_from_number, twiml=twiml)
    return {"status": "dialing", "call_sid": call.sid}


def _place_interactive_call(to_number: str, opening_message: str, purpose: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.public_webhook_base_url:
        return {"error": "PUBLIC_WEBHOOK_BASE_URL is not set - interactive calls need a public webhook URL. Run src/webhook_server.py behind ngrok/cloudflared first."}
    call = _client().calls.create(
        to=to_number,
        from_=settings.twilio_from_number,
        url=f"{settings.public_webhook_base_url}/voice/interactive?opening={opening_message}&purpose={purpose}",
    )
    return {"status": "dialing", "call_sid": call.sid}


def request_place_call(to_number: str, message: str, reason: str) -> Any:
    if not _is_configured():
        return {"error": "Twilio isn't configured yet. Set TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER in .env."}
    return PendingConfirmation(
        action_type="place_announcement_call",
        summary=f"Call {to_number} to say: \"{message}\" ({reason})?",
        payload={"to_number": to_number, "message": message},
    )


def request_place_interactive_call(to_number: str, opening_message: str, purpose: str) -> Any:
    if not _is_configured():
        return {"error": "Twilio isn't configured yet. Set TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER in .env."}
    return PendingConfirmation(
        action_type="place_interactive_call",
        summary=f"Place a live conversational call to {to_number} for: {purpose}? I'll open with: \"{opening_message}\"",
        payload={"to_number": to_number, "opening_message": opening_message, "purpose": purpose},
    )


register(Tool(
    name="request_place_call",
    description="Request placing a one-way announcement phone call that reads a scripted message aloud. Always requires confirmation.",
    parameters={
        "type": "object",
        "properties": {"to_number": {"type": "string"}, "message": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["to_number", "message", "reason"],
    },
    handler=request_place_call,
    requires_confirmation=True,
    executor=lambda payload: _place_announcement_call(payload["to_number"], payload["message"]),
))

register(Tool(
    name="request_place_interactive_call",
    description=(
        "Request placing a live conversational phone call (e.g. to a customer-care line) where the assistant "
        "listens and responds dynamically. Requires the webhook server running with a public URL. Always requires confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {"to_number": {"type": "string"}, "opening_message": {"type": "string"}, "purpose": {"type": "string"}},
        "required": ["to_number", "opening_message", "purpose"],
    },
    handler=request_place_interactive_call,
    requires_confirmation=True,
    executor=lambda payload: _place_interactive_call(payload["to_number"], payload["opening_message"], payload["purpose"]),
))
