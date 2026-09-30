"""ASGI app hosting the webhooks that need a publicly reachable URL:
  - POST /whatsapp/inbound         - Twilio WhatsApp inbound message webhook
  - POST /voice/interactive        - Twilio call webhook: opening line + first <Gather>
  - POST /voice/interactive/respond - loop: user's speech -> LLM reply -> <Gather> again
  - POST /presence/{chat_id}       - geofencing presence report (iPhone Shortcuts automation)

Run with: uvicorn src.webhook_server:app --host 127.0.0.1 --port 8000
Then expose it publicly (e.g. `ngrok http 8000` or Cloudflare Tunnel) and set
PUBLIC_WEBHOOK_BASE_URL in .env to that HTTPS URL. Configure the same URL as
the WhatsApp sender's inbound webhook in the Twilio console.

This process is separate from src/bot.py (the Telegram long-polling bot) -
run both alongside each other.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

from src.core import confirmation, net_guard
from src.core.llm_router import get_llm_router
from src.core.orchestrator import handle_user_message
from src.core.settings import get_settings
from src.db import supabase_client as db

log = logging.getLogger("webhook_server")
app = FastAPI()

MAX_CALL_TURNS = 8
_call_state: dict[str, dict] = {}  # call_sid -> {"purpose": str, "turns": int, "history": [...]}


@app.middleware("http")
async def _require_https_for_remote(request: Request, call_next):
    # Expected deployment is behind ngrok/cloudflared on this host (requests
    # arrive from loopback). Direct plain-HTTP hits from elsewhere would leak
    # the presence secret header, so refuse them.
    if net_guard.is_insecure_remote_request(request):
        return PlainTextResponse("HTTPS required.", status_code=403)
    return await call_next(request)


def _require_twilio_signature(request: Request, params: dict[str, str]) -> None:
    """Reject anything not signed by Twilio with our auth token. Without this,
    anyone who finds the public URL could post as any phone number (and
    CONFIRM that number's pending actions) or burn LLM credits. Fails closed
    when the token/base URL isn't configured.
    """
    settings = get_settings()
    token = settings.twilio_auth_token
    base_url = settings.public_webhook_base_url.rstrip("/")
    signature = request.headers.get("X-Twilio-Signature", "")
    if not (token and base_url and signature):
        raise HTTPException(status_code=403, detail="Missing Twilio signature or server config")
    # Rebuild the public URL Twilio actually called (we sit behind a tunnel,
    # so request.url has the internal host/scheme).
    url = base_url + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    if not RequestValidator(token).validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


async def _signed_form(request: Request) -> dict[str, str]:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    _require_twilio_signature(request, params)
    return params


@app.post("/whatsapp/inbound")
async def whatsapp_inbound(request: Request) -> PlainTextResponse:
    form = await _signed_form(request)
    settings = get_settings()
    from_number = str(form.get("From", "")).removeprefix("whatsapp:")
    body = str(form.get("Body", ""))

    if not settings.whatsapp_enabled or from_number not in settings.whatsapp_allowed_number_list:
        log.warning("Ignoring WhatsApp message from non-allow-listed number %s", from_number)
        return PlainTextResponse(str(MessagingResponse()), media_type="application/xml")

    chat_row = db.get_or_create_chat("whatsapp", from_number)
    chat_id = chat_row["id"]

    reply = MessagingResponse()
    normalized = body.strip().upper()
    if normalized in ("CONFIRM", "CANCEL"):
        pending = db.latest_pending_action_for_chat(chat_id)
        if pending is None:
            reply.message("There's nothing waiting for confirmation right now.")
        else:
            outcome = confirmation.resolve(pending["id"], approved=(normalized == "CONFIRM"))
            reply.message(outcome["message"] if isinstance(outcome.get("message"), str) else "Done.")
        return PlainTextResponse(str(reply), media_type="application/xml")

    result = handle_user_message(chat_id, body)
    reply.message(result.reply)
    if result.pending_action:
        reply.message(f"{result.pending_action['summary']} Reply CONFIRM or CANCEL.")
    return PlainTextResponse(str(reply), media_type="application/xml")


@app.post("/voice/interactive")
async def voice_interactive_start(request: Request) -> PlainTextResponse:
    form = await _signed_form(request)
    call_sid = str(form.get("CallSid") or request.query_params.get("CallSid", ""))
    opening = str(request.query_params.get("opening", "Hello."))
    purpose = str(request.query_params.get("purpose", ""))
    _call_state[call_sid] = {"purpose": purpose, "turns": 0, "history": []}

    vr = VoiceResponse()
    vr.say(opening)
    gather = Gather(input="speech", action="/voice/interactive/respond", method="POST", speech_timeout="auto")
    vr.append(gather)
    return PlainTextResponse(str(vr), media_type="application/xml")


@app.post("/voice/interactive/respond")
async def voice_interactive_respond(request: Request) -> PlainTextResponse:
    form = await _signed_form(request)
    call_sid = str(form.get("CallSid", ""))
    speech = str(form.get("SpeechResult", ""))
    state = _call_state.get(call_sid, {"purpose": "", "turns": 0, "history": []})
    state["turns"] += 1

    vr = VoiceResponse()
    if not speech or state["turns"] >= MAX_CALL_TURNS:
        vr.say("Thanks, goodbye.")
        vr.hangup()
        _call_state.pop(call_sid, None)
        return PlainTextResponse(str(vr), media_type="application/xml")

    state["history"].append({"role": "user", "content": speech})
    router = get_llm_router()
    messages = [
        {"role": "system", "content": f"You are on a live phone call on the user's behalf. Purpose: {state['purpose']}. Keep replies short and conversational, like a real phone call."},
        *state["history"],
    ]
    response = router.chat(messages)
    state["history"].append({"role": "assistant", "content": response.content})
    _call_state[call_sid] = state

    vr.say(response.content)
    gather = Gather(input="speech", action="/voice/interactive/respond", method="POST", speech_timeout="auto")
    vr.append(gather)
    return PlainTextResponse(str(vr), media_type="application/xml")


@app.post("/presence/{chat_id}")
async def presence_report(chat_id: int, request: Request, x_presence_secret: str = Header(default="")) -> JSONResponse:
    """Called by an iPhone Shortcuts automation on entering/exiting a home
    geofence. `chat_id` is the internal `chats.id` (not the raw phone
    number) - look it up via `/whoami` in the bot first. Secured by a shared
    secret header rather than any per-user auth, since Shortcuts automations
    can't do OAuth; keep PRESENCE_WEBHOOK_SECRET private like any other
    credential.
    """
    settings = get_settings()
    if not settings.presence_webhook_secret or not secrets.compare_digest(
        x_presence_secret.encode(), settings.presence_webhook_secret.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing presence webhook secret")

    body = await request.json()
    state = str(body.get("state", "")).lower()

    from src.integrations.smart_home.household_presence import report_presence

    result = report_presence(chat_id, state)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return JSONResponse(result)
