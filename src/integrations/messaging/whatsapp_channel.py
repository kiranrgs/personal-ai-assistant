"""Send outbound WhatsApp messages via Twilio's WhatsApp API. The inbound
side (receiving WhatsApp messages) is handled by `src/webhook_server.py`.
"""
from __future__ import annotations

from src.core.settings import get_settings


def send_whatsapp_message(to_number: str, text: str) -> None:
    from twilio.rest import Client

    settings = get_settings()
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_from):
        raise RuntimeError("WhatsApp isn't configured. Set TWILIO_ACCOUNT_SID/AUTH_TOKEN/WHATSAPP_FROM in .env.")
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(from_=settings.twilio_whatsapp_from, to=f"whatsapp:{to_number}", body=text)
