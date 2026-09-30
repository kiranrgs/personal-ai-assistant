"""Real end-user signup/login for the desktop client, via this project's own
Supabase Auth (separate Supabase project from personal-key-vault's own Auth -
these are two independent apps/accounts, never shared).

Every function here resolves identity FRESH from a Supabase-issued JWT on
each call (`verify_token`) - nothing about "who is this" is ever trusted from
a request body/query string, so one signed-in person can never address
another person's chat/messages/settings by guessing an id. See
`src/client_api_server.py` for how this is wired into every route via a
FastAPI dependency.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.core import user_config
from src.db import supabase_client as db

log = logging.getLogger(__name__)


class AuthError(RuntimeError):
    """Signup/login/token-verification failed - message is safe to show the user."""


def _chat_for_auth_user(user_id: str, email: Optional[str]) -> dict[str, Any]:
    chat = db.get_or_create_chat("desktop", user_id, display_name=email)
    # Desktop accounts are open self-signup, so they must never inherit the
    # owner's personal credentials from the shared root .env.
    user_config.mark_isolated_chat(chat["id"])
    return chat


def sign_up(email: str, password: str) -> dict[str, Any]:
    client = db.get_auth_client()
    try:
        result = client.auth.sign_up({"email": email, "password": password})
    except Exception as exc:  # noqa: BLE001 - gotrue raises its own exception types
        # Generic message: don't reveal whether an email is already registered.
        log.info("Sign up failed: %s", exc)
        raise AuthError("Sign up failed - check the email/password and try again.") from exc
    if result.user is None:
        raise AuthError("Sign up failed - check the email/password and try again.")

    chat = _chat_for_auth_user(result.user.id, result.user.email)
    if result.session is None:
        # Email confirmation is required before a session is issued - the
        # user must confirm, then call sign_in() once they have.
        return {"status": "confirmation_required", "chat_id": chat["id"]}
    return {
        "status": "signed_in",
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "chat_id": chat["id"],
        "email": result.user.email,
    }


def sign_in(email: str, password: str) -> dict[str, Any]:
    client = db.get_auth_client()
    try:
        result = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Invalid email or password.") from exc
    if result.user is None or result.session is None:
        raise AuthError("Invalid email or password.")

    chat = _chat_for_auth_user(result.user.id, result.user.email)
    return {
        "status": "signed_in",
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "chat_id": chat["id"],
        "email": result.user.email,
    }


def refresh_session(refresh_token: str) -> dict[str, Any]:
    client = db.get_auth_client()
    try:
        result = client.auth.refresh_session(refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Session expired - please log in again.") from exc
    if result.session is None:
        raise AuthError("Session expired - please log in again.")
    return {"access_token": result.session.access_token, "refresh_token": result.session.refresh_token}


def verify_token(access_token: str) -> dict[str, Any]:
    """Returns `{chat_id, user_id, email}` for a valid, currently-active
    access token, or raises `AuthError` for a missing/expired/invalid one.
    Called on every single client-API request - see `client_api_server.py`.
    """
    if not access_token:
        raise AuthError("Missing bearer token.")
    client = db.get_auth_client()
    try:
        result = client.auth.get_user(access_token)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Invalid or expired session - please log in again.") from exc
    if result is None or result.user is None:
        raise AuthError("Invalid or expired session - please log in again.")

    chat = _chat_for_auth_user(result.user.id, result.user.email)
    return {"chat_id": chat["id"], "user_id": result.user.id, "email": result.user.email}
