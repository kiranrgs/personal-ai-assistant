"""IMAP-based mail for providers without a modern OAuth API convenient for
personal/desktop use: iCloud Mail and Yahoo Mail. Both work the same way -
an app-specific password (NOT your normal account password):
  - iCloud: appleid.apple.com -> Sign-In and Security -> App-Specific Passwords
  - Yahoo: account.yahoo.com/myaccount/security -> Generate app password

Configure via .env:
  ICLOUD_ACCOUNTS=home            ICLOUD_HOME_EMAIL=... ICLOUD_HOME_APP_PASSWORD=...
  YAHOO_ACCOUNTS=personal         YAHOO_PERSONAL_EMAIL=... YAHOO_PERSONAL_APP_PASSWORD=...
"""
from __future__ import annotations

import datetime as dt
import os
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from imapclient import IMAPClient

from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items

_PROVIDERS = {
    "icloud": {"host": "imap.mail.me.com", "env_prefix": "ICLOUD"},
    "yahoo": {"host": "imap.mail.yahoo.com", "env_prefix": "YAHOO"},
}


def _decode(value: bytes | str) -> str:
    if isinstance(value, bytes):
        parts = decode_header(value.decode("utf-8", errors="ignore"))
    else:
        parts = decode_header(value)
    return "".join(p.decode(enc or "utf-8", errors="ignore") if isinstance(p, bytes) else p for p, enc in parts)


def _credentials(provider: str, label: str) -> tuple[str, str]:
    prefix = _PROVIDERS[provider]["env_prefix"]
    email_var = f"{prefix}_{label.upper()}_EMAIL"
    password_var = f"{prefix}_{label.upper()}_APP_PASSWORD"
    email_addr = os.environ.get(email_var, "")
    password = os.environ.get(password_var, "")
    if not email_addr or not password:
        raise RuntimeError(f"Missing {email_var}/{password_var} in .env for {provider} account '{label}'")
    return email_addr, password


def _fetch_today(provider: str, label: str) -> list[dict[str, str]]:
    host = _PROVIDERS[provider]["host"]
    email_addr, password = _credentials(provider, label)
    today = dt.date.today()

    with IMAPClient(host, use_uid=True) as client:
        client.login(email_addr, password)
        client.select_folder("INBOX", readonly=True)
        message_ids = client.search(["SINCE", today.strftime("%d-%b-%Y")])
        results = []
        for msg_id, data in client.fetch(message_ids, ["ENVELOPE"]).items():
            env = data[b"ENVELOPE"]
            sender = f"{env.from_[0].mailbox.decode()}@{env.from_[0].host.decode()}" if env.from_ else "unknown"
            results.append({
                "from": sender,
                "subject": _decode(env.subject) if env.subject else "(no subject)",
                "date": env.date.isoformat() if isinstance(env.date, dt.datetime) else str(env.date),
            })
        return results


def list_todays_imap_emails(provider: str, account: str) -> dict[str, Any]:
    if provider not in _PROVIDERS:
        return {"error": f"Unknown provider '{provider}', expected 'icloud' or 'yahoo'"}
    emails = _fetch_today(provider, account)
    return {"count": len(emails), "emails": emails}


def summarize_todays_imap_emails(provider: str, account: str) -> dict[str, Any]:
    if provider not in _PROVIDERS:
        return {"error": f"Unknown provider '{provider}', expected 'icloud' or 'yahoo'"}
    emails = _fetch_today(provider, account)
    if not emails:
        return {"summary": f"No {provider} emails today for account '{account}'."}
    items_text = "\n".join(f"- From: {e['from']} | Subject: {e['subject']}" for e in emails)
    summary = summarize_items(f"{provider} emails", items_text)
    return {"summary": summary, "count": len(emails)}


register(Tool(
    name="list_todays_imap_emails",
    description="List today's messages from an iCloud or Yahoo Mail account configured via IMAP app password.",
    parameters={
        "type": "object",
        "properties": {
            "provider": {"type": "string", "enum": ["icloud", "yahoo"]},
            "account": {"type": "string", "description": "The account label from ICLOUD_ACCOUNTS/YAHOO_ACCOUNTS"},
        },
        "required": ["provider", "account"],
    },
    handler=list_todays_imap_emails,
))

register(Tool(
    name="summarize_todays_imap_emails",
    description="LLM-summarize today's messages from an iCloud or Yahoo Mail account.",
    parameters={
        "type": "object",
        "properties": {
            "provider": {"type": "string", "enum": ["icloud", "yahoo"]},
            "account": {"type": "string", "description": "The account label from ICLOUD_ACCOUNTS/YAHOO_ACCOUNTS"},
        },
        "required": ["provider", "account"],
    },
    handler=summarize_todays_imap_emails,
))
