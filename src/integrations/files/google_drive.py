"""Google Drive: search files and fetch text content for summarization.
Shares OAuth plumbing with Gmail/Calendar.
"""
from __future__ import annotations

import io
from typing import Any, Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.core.google_oauth import get_google_credentials
from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google Docs/Sheets/Slides must be exported, not downloaded raw.
_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _service(account: Optional[str]):
    settings = get_settings()
    labels = settings.google_account_labels
    label = account or (labels[0] if labels else "default")
    creds = get_google_credentials(f"drive_{label}", SCOPES)
    return build("drive", "v3", credentials=creds)


def search_drive_files(query: str, account: Optional[str] = None, max_results: int = 10) -> dict[str, Any]:
    service = _service(account)
    result = service.files().list(
        q=f"name contains '{query}' and trashed = false",
        fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        pageSize=max_results,
    ).execute()
    return {"count": len(result.get("files", [])), "files": result.get("files", [])}


def _read_text(service, file_id: str, mime_type: str) -> str:
    export_mime = _EXPORT_MIME.get(mime_type)
    request = service.files().export_media(fileId=file_id, mimeType=export_mime) if export_mime else service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8", errors="ignore")


def summarize_drive_file(file_id: str, account: Optional[str] = None) -> dict[str, Any]:
    service = _service(account)
    meta = service.files().get(fileId=file_id, fields="name, mimeType").execute()
    try:
        text = _read_text(service, file_id, meta["mimeType"])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Couldn't read '{meta.get('name')}': {exc}"}
    summary = summarize_items(f"file '{meta.get('name')}'", text[:20000])
    return {"name": meta.get("name"), "summary": summary}


register(Tool(
    name="search_drive_files",
    description="Search Google Drive for files by name.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "account": {"type": "string", "description": "Google account label"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    },
    handler=search_drive_files,
))

register(Tool(
    name="summarize_drive_file",
    description="Fetch and LLM-summarize a Google Drive file's contents by file ID (from search_drive_files).",
    parameters={
        "type": "object",
        "properties": {"file_id": {"type": "string"}, "account": {"type": "string"}},
        "required": ["file_id"],
    },
    handler=summarize_drive_file,
))
