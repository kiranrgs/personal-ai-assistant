"""Google Sheets: read a range and produce an LLM summary of its contents."""
from __future__ import annotations

from typing import Any, Optional

from googleapiclient.discovery import build

from src.core.google_oauth import get_google_credentials
from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _service(account: Optional[str]):
    settings = get_settings()
    labels = settings.google_account_labels
    label = account or (labels[0] if labels else "default")
    creds = get_google_credentials(f"sheets_{label}", SCOPES)
    return build("sheets", "v4", credentials=creds)


def read_sheet_range(spreadsheet_id: str, range_a1: str = "A1:Z100", account: Optional[str] = None) -> dict[str, Any]:
    service = _service(account)
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_a1).execute()
    return {"values": result.get("values", [])}


def summarize_sheet(spreadsheet_id: str, range_a1: str = "A1:Z100", account: Optional[str] = None) -> dict[str, Any]:
    data = read_sheet_range(spreadsheet_id, range_a1, account)
    rows = data["values"]
    if not rows:
        return {"summary": "That range is empty."}
    text = "\n".join(", ".join(row) for row in rows[:500])
    return {"summary": summarize_items("spreadsheet data", text)}


register(Tool(
    name="read_sheet_range",
    description="Read a cell range from a Google Sheet by spreadsheet ID (default A1:Z100).",
    parameters={
        "type": "object",
        "properties": {"spreadsheet_id": {"type": "string"}, "range_a1": {"type": "string"}, "account": {"type": "string"}},
        "required": ["spreadsheet_id"],
    },
    handler=read_sheet_range,
))

register(Tool(
    name="summarize_sheet",
    description="Read and LLM-summarize a Google Sheet range.",
    parameters={
        "type": "object",
        "properties": {"spreadsheet_id": {"type": "string"}, "range_a1": {"type": "string"}, "account": {"type": "string"}},
        "required": ["spreadsheet_id"],
    },
    handler=summarize_sheet,
))
