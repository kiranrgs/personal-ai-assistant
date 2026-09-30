"""Small admin-only web console for the two things that shouldn't require
hand-editing `.env` or restarting a running bot process:

  - Register Telegram bot **tenants** - their own bot token + own
    allowed-chat-id list, fully isolated from every other tenant. There is
    no .env-configured default bot; every bot, including the very first
    one, is registered here (see `src/bot.py`'s `_load_tenants()` /
    `supabase/migrations/0003_tenants.sql`).
  - View every known user (across every tenant/channel) and set a per-user
    config override on their behalf - the same whitelist as the `/set`
    Telegram command (see `src/core/user_config.py`).
  - Toggle a user's personal-key-vault companion-API integration
    (VAULT_API_ENABLED) and manage their per-spend-category default cards -
    see `src/integrations/vault_bridge/personal_key_vault_client.py`.

Run with: uvicorn src.admin_server:app --port 8090

Put this behind HTTPS (nginx/Caddy/Cloudflare Tunnel/ngrok) if it's reachable
beyond localhost - HTTP Basic Auth sends the password on every single
request and provides no protection against network eavesdropping without
TLS. Requires ADMIN_USERNAME/ADMIN_PASSWORD in `.env`; every request is
refused (fails closed) if ADMIN_PASSWORD is blank.

Adding/changing a tenant here takes effect on the *next* `python -m src.bot`
restart - tenants aren't hot-reloaded into an already-running bot process.
"""
from __future__ import annotations

import html
import logging
import secrets

from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.core import net_guard, user_config
from src.core.settings import get_settings
from src.core.user_config import set_current_chat
from src.db import supabase_client as db
from src.integrations.vault_bridge import personal_key_vault_client as vault

log = logging.getLogger("admin_server")
app = FastAPI()
security = HTTPBasic()

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def _csrf_and_framing_guard(request: Request, call_next):
    # The console holds every tenant's bot token and every user's settings -
    # only serve it to this machine unless explicitly opted in, and never
    # over plain HTTP to a remote client (Basic auth would be sent in clear).
    if not net_guard.is_local_request(request):
        if not get_settings().admin_allow_remote:
            return PlainTextResponse("Admin console is only available from localhost.", status_code=403)
        if net_guard.is_insecure_remote_request(request):
            return PlainTextResponse("HTTPS required.", status_code=403)
    # Basic-auth credentials are re-sent automatically by the browser, so any
    # other site the admin visits could otherwise auto-submit a form to this
    # console (CSRF). Require state-changing requests to come from this origin.
    if request.method not in _SAFE_METHODS:
        source = request.headers.get("origin") or request.headers.get("referer") or ""
        host = request.headers.get("host", "")
        if not source or not host or urlsplit(source).netloc != host:
            return PlainTextResponse("Cross-site request blocked.", status_code=403)
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response

_PAGE_STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}"
    "table{border-collapse:collapse;width:100%;margin-bottom:1.5rem}"
    "th,td{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.9rem}"
    "form{margin-bottom:1.5rem;padding:1rem;border:1px solid #ddd;border-radius:6px;max-width:420px}"
    "label{display:block;margin:.5rem 0 .1rem}input{width:100%;padding:.3rem;box-sizing:border-box}"
    "button{margin-top:.7rem;padding:.4rem 1rem}nav a{margin-right:1rem}"
)


def _require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    settings = get_settings()
    if not settings.admin_password:
        raise HTTPException(
            status_code=503,
            detail="Admin console disabled - set ADMIN_USERNAME/ADMIN_PASSWORD in .env to enable it.",
        )
    user_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Invalid admin credentials", headers={"WWW-Authenticate": "Basic"})


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_PAGE_STYLE}</style></head>"
        f"<body><nav><a href='/'>Tenants</a><a href='/users'>Users</a></nav>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    )


@app.get("/", response_class=HTMLResponse)
def tenants_page(_: None = Depends(_require_admin)) -> HTMLResponse:
    rows = ["<tr><th>ID</th><th>Name</th><th>Bot token</th><th>Allowed chat IDs</th><th>Active</th></tr>"]
    try:
        tenants = db.list_tenants(active_only=False)
    except Exception as exc:  # noqa: BLE001
        tenants = []
        rows.append(f"<tr><td colspan='5'>Couldn't load tenants from Supabase: {html.escape(str(exc))}</td></tr>")
    else:
        if not tenants:
            rows.append("<tr><td colspan='5'>No bots registered yet - add your first one below.</td></tr>")
        for t in tenants:
            token = t.get("telegram_bot_token") or ""
            masked_token = ("\u2022\u2022\u2022" + token[-4:]) if token else "(not set)"
            rows.append(
                f"<tr><td>{t['id']}</td><td>{html.escape(t['name'])}</td>"
                f"<td>{html.escape(masked_token)}</td>"
                f"<td>{html.escape(t.get('telegram_allowed_chat_ids') or '(none)')}</td>"
                f"<td>{t['active']} "
                f"<form style='display:inline;border:none;padding:0;margin:0' method='post' action='/tenants/{t['id']}/toggle'>"
                "<button type='submit'>toggle</button></form></td></tr>"
            )

    body = (
        "<table>" + "".join(rows) + "</table>"
        "<form method='post' action='/tenants'>"
        "<h3>Add a tenant (own Telegram bot)</h3>"
        "<label>Name</label><input name='name' required>"
        "<label>Telegram bot token (from @BotFather)</label><input name='telegram_bot_token' required>"
        "<label>Allowed chat IDs (comma-separated)</label><input name='telegram_allowed_chat_ids' placeholder='123456789,987654321'>"
        "<button type='submit'>Add tenant</button>"
        "</form>"
        "<p>Restart <code>python -m src.bot</code> for a new/changed tenant to take effect.</p>"
    )
    return _page("Tenants", body)


@app.post("/tenants")
def create_tenant(
    name: str = Form(...),
    telegram_bot_token: str = Form(...),
    telegram_allowed_chat_ids: str = Form(""),
    _: None = Depends(_require_admin),
) -> RedirectResponse:
    db.create_tenant(name.strip(), telegram_bot_token.strip(), telegram_allowed_chat_ids.strip())
    return RedirectResponse("/", status_code=303)


@app.post("/tenants/{tenant_id}/toggle")
def toggle_tenant(tenant_id: int, _: None = Depends(_require_admin)) -> RedirectResponse:
    tenant = db.get_tenant(tenant_id)
    if tenant is not None:
        db.set_tenant_active(tenant_id, not tenant["active"])
    return RedirectResponse("/", status_code=303)


@app.get("/users", response_class=HTMLResponse)
def users_page(_: None = Depends(_require_admin)) -> HTMLResponse:
    try:
        chats = db.list_chats()
    except Exception as exc:  # noqa: BLE001
        return _page("Users", f"<p>Couldn't load users from Supabase: {html.escape(str(exc))}</p>")

    rows = [
        "<tr><th>Internal chat id</th><th>Tenant</th><th>Channel</th><th>External id</th><th>Household</th>"
        "<th>Overrides (masked)</th><th>Vault companion API</th><th></th></tr>"
    ]
    for c in chats:
        chat_id = c["id"]
        overrides = user_config.list_user_overrides_masked(chat_id)
        raw_overrides = user_config.load_user_overrides(chat_id)
        user_row = db.get_user(chat_id) or {}
        overrides_str = ", ".join(f"{k}={v}" for k, v in overrides.items()) or "(none)"
        vault_enabled = raw_overrides.get("VAULT_API_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
        toggle_label = "disable" if vault_enabled else "enable"
        toggle_value = "false" if vault_enabled else "true"
        rows.append(
            f"<tr><td>{chat_id}</td><td>{c.get('tenant_id', 0)}</td><td>{html.escape(c['channel'])}</td>"
            f"<td>{html.escape(c['external_chat_id'])}</td><td>{html.escape(user_row.get('household') or '')}</td>"
            f"<td>{html.escape(overrides_str)}</td>"
            f"<td>{'on' if vault_enabled else 'off'} "
            f"<form style='display:inline;border:none;padding:0;margin:0' method='post' action='/users/{chat_id}/vault-api/toggle'>"
            f"<input type='hidden' name='enable' value='{toggle_value}'>"
            f"<button type='submit'>{toggle_label}</button></form></td>"
            f"<td><a href='/users/{chat_id}/vault-card-defaults'>Card defaults</a></td></tr>"
        )

    body = (
        "<table>" + "".join(rows) + "</table>"
        "<form method='post' action='/users/set'>"
        "<h3>Set a per-user override on someone's behalf</h3>"
        "<label>Internal chat id</label><input name='chat_id' type='number' required>"
        "<label>Key</label><input name='key' required placeholder='e.g. GOOGLE_ACCOUNTS'>"
        "<label>Value</label><input name='value' required>"
        "<button type='submit'>Save</button>"
        "</form>"
        "<p>Accepts every per-user key, including admin-only ones users can't /set themselves "
        "(vault account/companion settings, account labels, local paths). Shared bot settings "
        "(bot tokens, Supabase key, allow-lists) can't be set here.</p>"
    )
    return _page("Users", body)


@app.post("/users/set")
def set_user_override_route(
    chat_id: int = Form(...),
    key: str = Form(...),
    value: str = Form(...),
    _: None = Depends(_require_admin),
) -> RedirectResponse:
    try:
        user_config.set_user_override(chat_id, key, value, admin=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/users", status_code=303)


@app.post("/users/{chat_id}/vault-api/toggle")
def toggle_vault_api(
    chat_id: int,
    enable: str = Form(...),
    _: None = Depends(_require_admin),
) -> RedirectResponse:
    user_config.set_user_override(chat_id, "VAULT_API_ENABLED", enable, admin=True)
    return RedirectResponse("/users", status_code=303)


@app.get("/users/{chat_id}/vault-card-defaults", response_class=HTMLResponse)
def vault_card_defaults_page(chat_id: int, _: None = Depends(_require_admin)) -> HTMLResponse:
    with set_current_chat(chat_id):
        defaults_result = vault.list_vault_card_defaults()
        cards_result = vault.get_vault_cards()

    if defaults_result.get("status") or defaults_result.get("error"):
        message = defaults_result.get("message") or defaults_result.get("error")
        body = (
            f"<p>Can't manage card defaults for chat {chat_id} yet: {html.escape(str(message))}</p>"
            "<p><a href='/users'>&larr; Back to Users</a></p>"
        )
        return _page(f"Card defaults - chat {chat_id}", body)

    defaults = defaults_result.get("defaults", [])
    cards = cards_result.get("cards", []) if not (cards_result.get("status") or cards_result.get("error")) else []

    rows = ["<tr><th>Category</th><th>Card</th><th></th></tr>"]
    for d in defaults:
        category = d.get("category", "")
        card_id = d.get("card_id", "")
        card_label = next(
            (f"{c.get('label')} ({c.get('bankName')})" for c in cards if c.get("id") == card_id), card_id
        )
        rows.append(
            f"<tr><td>{html.escape(category)}</td><td>{html.escape(str(card_label))}</td>"
            f"<td><form style='display:inline;border:none;padding:0;margin:0' method='post' "
            f"action='/users/{chat_id}/vault-card-defaults/clear'>"
            f"<input type='hidden' name='category' value='{html.escape(category)}'>"
            "<button type='submit'>clear</button></form></td></tr>"
        )
    if not defaults:
        rows.append(
            "<tr><td colspan='3'>No explicit category defaults pinned yet - unpinned categories fall back "
            "to usage history.</td></tr>"
        )

    card_options = "".join(
        f"<option value='{html.escape(str(c.get('id')))}'>{html.escape(str(c.get('label')))} "
        f"({html.escape(str(c.get('bankName')))})</option>"
        for c in cards
    )
    if not card_options:
        card_options = "<option value=''>(no cards saved yet)</option>"

    body = (
        "<p><a href='/users'>&larr; Back to Users</a></p>"
        "<table>" + "".join(rows) + "</table>"
        f"<form method='post' action='/users/{chat_id}/vault-card-defaults/set'>"
        "<h3>Set a category default</h3>"
        "<label>Category</label><input name='category' required placeholder='e.g. utilities'>"
        "<label>Card</label><select name='card_id' required>" + card_options + "</select>"
        "<button type='submit'>Save</button>"
        "</form>"
    )
    return _page(f"Card defaults - chat {chat_id}", body)


@app.post("/users/{chat_id}/vault-card-defaults/set")
def set_vault_card_default_route(
    chat_id: int,
    category: str = Form(...),
    card_id: str = Form(...),
    _: None = Depends(_require_admin),
) -> RedirectResponse:
    with set_current_chat(chat_id):
        vault.set_vault_card_default(category, card_id)
    return RedirectResponse(f"/users/{chat_id}/vault-card-defaults", status_code=303)


@app.post("/users/{chat_id}/vault-card-defaults/clear")
def clear_vault_card_default_route(
    chat_id: int,
    category: str = Form(...),
    _: None = Depends(_require_admin),
) -> RedirectResponse:
    with set_current_chat(chat_id):
        vault.clear_vault_card_default(category)
    return RedirectResponse(f"/users/{chat_id}/vault-card-defaults", status_code=303)
