"""HTTP API for the downloadable desktop client (Windows/macOS) - see
`apps/desktop` for the Tauri + React client that talks to this server.

Every route resolves "who is calling" fresh from a Supabase Auth bearer
token via `core.client_auth.verify_token()` - the client NEVER sends a
chat_id/user_id itself, and no route accepts one as an argument, so one
signed-in person can't address another person's chat history, bookmarks,
settings, or vault data by guessing an id. Any object looked up by its own
id (a bookmark, a pending confirmation) is additionally checked to actually
belong to the caller's own chat_id before it's returned or acted on.

Run with: uvicorn src.client_api_server:app --port 8092

This is a separate process from src/bot.py (Telegram polling),
src/webhook_server.py (WhatsApp/voice/presence webhooks), and
src/admin_server.py (admin-only Basic-Auth console) - run whichever of
these you need alongside each other. Put this behind HTTPS for anything
beyond localhost, same as the admin console.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.core import client_auth, confirmation, llm_models, net_guard, telegram_link, user_config
from src.core.orchestrator import handle_user_message
from src.core.rate_limit import SlidingWindowLimiter
from src.core.settings import get_settings
from src.core.user_config import set_current_chat
from src.db import supabase_client as db
from src.integrations.vault_bridge import personal_key_vault_client as vault

log = logging.getLogger("client_api_server")
app = FastAPI(title="personal-ai-assistant client API")

# The Tauri desktop client's webview calls this like a normal web app would
# (fetch with an Authorization header, no cookies). Only the Tauri webview
# origins (and the Vite dev server) are allowed, so a random website a
# signed-in user visits can't script calls against this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost:1420",
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def _require_https_for_remote(request: Request, call_next):
    # Passwords and bearer tokens must never cross the network in clear text.
    # Local clients and a TLS-terminating proxy/tunnel on this host are fine.
    if net_guard.is_insecure_remote_request(request):
        return PlainTextResponse("HTTPS required.", status_code=403)
    return await call_next(request)


def _bearer_token(authorization: str = Header(default="")) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return authorization[len("Bearer "):].strip()


def current_identity(token: str = Depends(_bearer_token)) -> dict[str, Any]:
    try:
        return client_auth.verify_token(token)
    except client_auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# Brute-force / abuse limits. Keyed by client IP - when running behind a
# reverse proxy, start uvicorn with --proxy-headers --forwarded-allow-ips=<proxy ip>
# so request.client.host is the real caller, not the proxy.
_auth_ip_limiter = SlidingWindowLimiter(max_events=20, window_seconds=300)
_signup_ip_limiter = SlidingWindowLimiter(max_events=5, window_seconds=3600)
_login_email_limiter = SlidingWindowLimiter(max_events=10, window_seconds=900)
_refresh_ip_limiter = SlidingWindowLimiter(max_events=60, window_seconds=300)
_chat_limiter = SlidingWindowLimiter(max_events=30, window_seconds=60)
_link_code_limiter = SlidingWindowLimiter(max_events=5, window_seconds=600)


def _enforce(limiter: SlidingWindowLimiter, key: str) -> None:
    if not limiter.hit(key):
        raise HTTPException(status_code=429, detail="Too many requests - please wait a bit and try again.")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class SignUpBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=256)


class LoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class RefreshBody(BaseModel):
    refresh_token: str = Field(max_length=4096)


@app.post("/auth/signup")
def signup(body: SignUpBody, request: Request) -> dict[str, Any]:
    ip = _client_ip(request)
    _enforce(_auth_ip_limiter, ip)
    _enforce(_signup_ip_limiter, ip)
    try:
        return client_auth.sign_up(body.email, body.password)
    except client_auth.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/auth/login")
def login(body: LoginBody, request: Request) -> dict[str, Any]:
    _enforce(_auth_ip_limiter, _client_ip(request))
    _enforce(_login_email_limiter, body.email.strip().lower())
    try:
        return client_auth.sign_in(body.email, body.password)
    except client_auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/auth/refresh")
def refresh(body: RefreshBody, request: Request) -> dict[str, Any]:
    _enforce(_refresh_ip_limiter, _client_ip(request))
    try:
        return client_auth.refresh_session(body.refresh_token)
    except client_auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/me")
def me(identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    chat_id = identity["chat_id"]
    return {
        "chat_id": chat_id,
        "email": identity["email"],
        "settings": user_config.list_user_overrides_for_display(chat_id),
    }


class ChatMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    model_id: Optional[str] = Field(default=None, max_length=200)


def _validate_allowed_model(model_id: str) -> str:
    normalized = model_id.strip()
    if not llm_models.is_allowed_groq_model(normalized):
        raise HTTPException(status_code=400, detail="Unsupported model id for this server.")
    return normalized


@app.get("/llm/models")
def list_llm_models(identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    models = llm_models.list_groq_models()
    with set_current_chat(identity["chat_id"]):
        selected = get_settings().groq_model
    selected = llm_models.resolve_model(llm_models.DESKTOP_CHANNEL, user_preferred=selected)
    return {
        "provider": "groq",
        "default_model": llm_models.default_model(),
        "selected_model": selected,
        "models": models,
    }


@app.post("/chat")
def send_chat_message(body: ChatMessageBody, identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    _enforce(_chat_limiter, str(identity["chat_id"]))
    model_override = _validate_allowed_model(body.model_id) if body.model_id else None
    result = handle_user_message(identity["chat_id"], body.message, model_override=model_override)
    pending_action = None
    if result.pending_action:
        pending_action = {
            "action_id": result.pending_action["id"],
            "summary": result.pending_action["summary"],
        }
    return {"reply": result.reply, "pending_action": pending_action}


@app.get("/chat/history")
def chat_history(limit: int = 50, identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    return {"messages": db.recent_messages(identity["chat_id"], limit=limit)}


class ConfirmBody(BaseModel):
    action_id: str
    approved: bool


@app.post("/chat/confirm")
def confirm_action(body: ConfirmBody, identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    action = db.get_pending_action(body.action_id)
    if action is None or action["chat_id"] != identity["chat_id"]:
        # Deliberately the same 404 whether it doesn't exist or belongs to
        # someone else - never confirm/reveal which is the case.
        raise HTTPException(status_code=404, detail="No such pending confirmation.")
    return confirmation.resolve(body.action_id, approved=body.approved)


class BookmarkBody(BaseModel):
    message_id: int
    note: Optional[str] = Field(default=None, max_length=1000)


@app.get("/bookmarks")
def list_bookmarks(identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    return {"bookmarks": db.list_bookmarks(identity["chat_id"])}


@app.post("/bookmarks")
def add_bookmark(body: BookmarkBody, identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    message = db.get_message(body.message_id)
    if message is None or message["chat_id"] != identity["chat_id"]:
        raise HTTPException(status_code=404, detail="No such message.")
    return db.add_bookmark(identity["chat_id"], body.message_id, body.note)


@app.delete("/bookmarks/{bookmark_id}")
def remove_bookmark(bookmark_id: int, identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    bookmark = db.get_bookmark(bookmark_id)
    if bookmark is None or bookmark["chat_id"] != identity["chat_id"]:
        raise HTTPException(status_code=404, detail="No such bookmark.")
    db.remove_bookmark(bookmark_id)
    return {"ok": True}


class SettingBody(BaseModel):
    key: str = Field(max_length=100)
    value: str = Field(max_length=2000)


@app.get("/settings")
def get_settings_route(identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    return {"settings": user_config.list_user_overrides_for_display(identity["chat_id"])}


@app.post("/settings")
def set_setting(body: SettingBody, identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    key = body.key.strip().upper()
    value = body.value.strip()
    if key == "GROQ_MODEL":
        value = _validate_allowed_model(value)
    try:
        user_config.set_user_override(identity["chat_id"], key, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/settings/{key}")
def delete_setting(key: str, identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    try:
        user_config.unset_user_override(identity["chat_id"], key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# --- Verified Telegram notification link (see core/telegram_link.py) ---
@app.post("/telegram-link")
def start_telegram_link(identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    _enforce(_link_code_limiter, str(identity["chat_id"]))
    code = telegram_link.create_link_code(identity["chat_id"])
    return {"code": code, "expires_in_seconds": telegram_link.CODE_TTL_SECONDS}


@app.delete("/telegram-link")
def remove_telegram_link(identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    telegram_link.unlink(identity["chat_id"])
    return {"ok": True}


# --- Personal-key-vault companion API passthrough (cards/category defaults) ---
#
# vault.* calls return a plain dict with a "status"/"error" key (not an
# exception) whenever the companion API isn't ready for this user (not
# linked, opted out, unreachable, etc.) - see _require_api_ready() in
# personal_key_vault_client.py. Convert that into a normal HTTP error here so
# the desktop client's fetch wrapper can just use try/catch like every other
# route instead of special-casing 200-with-error-body responses.
def _unwrap_vault_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") or result.get("error"):
        message = result.get("message") or result.get("error") or "Vault companion API is unavailable."
        raise HTTPException(status_code=409, detail=message)
    return result


@app.get("/vault/cards")
def vault_cards(query: str = "", identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    with set_current_chat(identity["chat_id"]):
        result = _unwrap_vault_result(vault.get_vault_cards(query))
    return {"cards": result.get("cards", [])}


@app.get("/vault/card-defaults")
def vault_card_defaults(identity: dict[str, Any] = Depends(current_identity)) -> dict[str, Any]:
    with set_current_chat(identity["chat_id"]):
        defaults_result = _unwrap_vault_result(vault.list_vault_card_defaults())
        cards_result = vault.get_vault_cards()

    cards = cards_result.get("cards", []) if not (cards_result.get("status") or cards_result.get("error")) else []
    cards_by_id = {card["id"]: card for card in cards}
    defaults = {
        entry["category"]: cards_by_id.get(
            entry["card_id"],
            {"id": entry["card_id"], "label": entry["card_id"], "bankName": "", "last4": ""},
        )
        for entry in defaults_result.get("defaults", [])
    }
    return {"defaults": defaults}


class CardDefaultBody(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    card_id: str = Field(min_length=1, max_length=100)


@app.post("/vault/card-defaults")
def set_vault_card_default_route(
    body: CardDefaultBody, identity: dict[str, Any] = Depends(current_identity)
) -> dict[str, Any]:
    with set_current_chat(identity["chat_id"]):
        _unwrap_vault_result(vault.set_vault_card_default(body.category, body.card_id))
    return {"ok": True}


@app.delete("/vault/card-defaults/{category}")
def clear_vault_card_default_route(
    category: str, identity: dict[str, Any] = Depends(current_identity)
) -> dict[str, Any]:
    with set_current_chat(identity["chat_id"]):
        _unwrap_vault_result(vault.clear_vault_card_default(category))
    return {"ok": True}

