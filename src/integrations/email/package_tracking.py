"""Package/delivery tracking: scans your primary Gmail account for recent
shipping/delivery emails and summarizes tracking status - a lightweight
add-on over the existing Gmail search tool rather than a separate
carrier-by-carrier integration (UPS/FedEx/USPS/Amazon all have different,
inconsistent public APIs for personal use; email is the one place they all
consistently notify you).
"""
from __future__ import annotations

from typing import Any, Optional

from src.core.tool_registry import Tool, register
from src.integrations.email.gmail import search_emails
from src.integrations.email.summarizer import summarize_items

_QUERY = (
    'newer_than:14d (subject:shipped OR subject:"out for delivery" OR subject:delivered '
    "OR subject:tracking OR subject:shipment OR from:amazon OR from:ups OR from:fedex OR from:usps)"
)


def summarize_package_tracking(account: Optional[str] = None) -> dict[str, Any]:
    result = search_emails(_QUERY, account=account, max_results=25)
    emails = result.get("emails", [])
    if not emails:
        return {"summary": "No recent shipping/delivery emails found."}
    text = "\n".join(f"- From: {e['from']} | Subject: {e['subject']} | {e['snippet']}" for e in emails)
    summary = summarize_items(
        "shipping/delivery emails", text,
        instructions="Group by order/package, call out estimated delivery dates and anything that looks delayed or needs action.",
    )
    return {"summary": summary, "count": len(emails)}


register(Tool(
    name="summarize_package_tracking",
    description="Scan recent email for shipping/delivery notifications (Amazon, UPS, FedEx, USPS, etc) and summarize package status.",
    parameters={"type": "object", "properties": {"account": {"type": "string", "description": "Google account label"}}},
    handler=summarize_package_tracking,
))
