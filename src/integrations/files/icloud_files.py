r"""iCloud Drive has no public third-party API. The practical, supported way
to reach it programmatically is via the local "iCloud Drive" sync folder
that Apple's own iCloud for Windows / macOS Finder integration keeps in sync
on disk - so this just searches/reads within that folder, same as any other
local files. Set ICLOUD_DRIVE_LOCAL_PATH in .env once you know the path
(Windows default is usually under
%USERPROFILE%\iCloudDrive; macOS is ~/Library/Mobile Documents/com~apple~CloudDocs).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items

_DEFAULT_WINDOWS_PATH = Path(os.path.expanduser("~")) / "iCloudDrive"


def _root() -> Path:
    configured = os.environ.get("ICLOUD_DRIVE_LOCAL_PATH", "")
    root = Path(configured) if configured else _DEFAULT_WINDOWS_PATH
    if not root.exists():
        raise RuntimeError(
            f"iCloud Drive folder not found at {root}. Install 'iCloud for Windows' (or use the "
            "Finder-synced path on macOS) and set ICLOUD_DRIVE_LOCAL_PATH in .env."
        )
    return root


def search_icloud_files(query: str, max_results: int = 20) -> dict[str, Any]:
    root = _root()
    matches = [str(p.relative_to(root)) for p in root.rglob(f"*{query}*") if p.is_file()][:max_results]
    return {"count": len(matches), "files": matches}


def summarize_icloud_file(relative_path: str) -> dict[str, Any]:
    root = _root()
    path = (root / relative_path).resolve()
    if root not in path.parents and path != root:
        return {"error": "Path escapes the iCloud Drive folder."}
    if not path.is_file():
        return {"error": f"File not found: {relative_path}"}
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {"summary": summarize_items(f"file '{path.name}'", text[:20000])}


register(Tool(
    name="search_icloud_files",
    description="Search files by name within the local iCloud Drive sync folder.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]},
    handler=search_icloud_files,
))

register(Tool(
    name="summarize_icloud_file",
    description="Read and LLM-summarize a text file from the local iCloud Drive folder, given its path relative to the iCloud Drive root (from search_icloud_files).",
    parameters={"type": "object", "properties": {"relative_path": {"type": "string"}}, "required": ["relative_path"]},
    handler=summarize_icloud_file,
))
